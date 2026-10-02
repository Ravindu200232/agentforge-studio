"""Building the application."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server_modules import (auth_guide, bus, changes, config, plugins, prompts, reference_staging, store,
                            supabase_connect)
from server_modules.qa_report import summary_counts
from server_modules.session import RunCancelled, session_for
from server_modules.validation import build_report

BUILD_DIR = "build"
REPORT = (BUILD_DIR, "report.json")
DECISIONS = (BUILD_DIR, "decisions.json")
# The most the customer is asked before one build is planned - a bound, not a list: what is asked is the model's call.
QUESTIONS = 5
REPORT_REPAIR_ROUNDS = 2
# The stack's build guides, staged where the agent reads them - inside the record folder, never the app root: a
# folder there would make `scaffold.install` take a fresh workspace for an existing app and copy no template.
GUIDES_DIR = f"{config.RECORD_DIR}/{BUILD_DIR}/guides"


def report(project: str) -> dict[str, Any]:
    saved = session_for(project).read_record(*REPORT, fallback=None)
    return saved if isinstance(saved, dict) else {}


def built(project: str) -> bool:
    return bool(report(project))


def _recoverably_incomplete(qa_report: Any) -> bool:
    """A `qa/report.json` missing its `complete` flag that is safe to backfill
    rather than fail the build over.

    Found live: a run interrupted after the real testing work finished but
    before that one flag was written left every layer's evidence genuinely
    passing on disk, yet resuming kept re-deriving "nothing left to do" from
    that same evidence without ever writing the flag itself - failing this
    exact check, forever, on every resume. A report that already holds real
    recorded evidence (a summary, more than a bare placeholder) and was never
    explicitly marked incomplete by the model itself only needs that one
    field backfilled, not the whole run failed - `complete: False` set on
    purpose is left alone; that is a real, honest gap, not this bug.
    """
    return (isinstance(qa_report, dict) and qa_report.get("complete") is not False
           and bool(qa_report.get("summary")) and len(qa_report) > 2)


def show_preview(project: str) -> None:
    """The build is done: serve what it left on disk and bring the preview up on it.

    Never fails the build. An app that will not start says so in the preview and in
    `.agentforge/preview.log`; that is not a reason to call the build failed.
    """
    try:
        from server_modules import preview_runtime

        preview_runtime.reopen(project)
        bus.transient({"type": "show_preview", "project": project})
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        bus.log(project, "WARN", f"The preview could not be started: {exc}")


def _prototype_context_block(workspace: Path) -> str:
    """Point the builder at the prototype it must read, map and reproduce.

    `builder/generate.md` already tells the model to open `routes.json` and
    read every prototype HTML file and shared asset in full; this only says
    whether there is a prototype to read at all, rather than pasting its
    routes or file lists in (the model lists the folder itself).
    """
    if not (workspace / ".agentforge" / "prototype" / "routes.json").is_file():
        return ""
    return (
        "\n\n## Mandatory prototype parity inventory\n\n"
        "There is an approved prototype at `.agentforge/prototype/`. Before planning, "
        "list it (`list_files`) and read every HTML file and shared asset it contains "
        "in full. In the plan, map each route to its exact prototype HTML, destination "
        "application files and reused image sources. Before implementing each route, "
        "reopen that HTML file. The real app must preserve 100% of its approved "
        "frontend design, exact images, controls, destinations and navigation flow "
        "while connecting real data. Never guess from memory or replace prototype "
        "imagery."
    )


def _report_problems(session: Any) -> list[str]:
    """What keeps either report file from the Testing views' template. A file that is missing
    altogether is not listed: the gates in `_finish_run` already say so plainly."""
    found = []
    for section, (folder, name) in build_report.SECTIONS.items():
        saved = session.read_record(folder, name, fallback=None)
        if isinstance(saved, dict):
            found += [f"{folder}/{name}: {issue}" for issue in build_report.problems(saved, section)]
    return found


def _conform_reports(project: str, session: Any, plan: str) -> None:
    """Hold both report files to the template the Testing views read (`build_report.py`).

    The same conversation continues, so nothing finished is redone - only the two report
    files are rewritten. A build whose app and checks are done is never failed over its
    report's shape: what is still off is logged, and the Testing views show what they can read.
    """
    for _ in range(REPORT_REPAIR_ROUNDS):
        found = _report_problems(session)
        if not found:
            return
        bus.log(project, "INFO", f"The report files miss the Testing screen's template in {len(found)} "
                                 "place(s); asking for them to be rewritten.")
        try:
            request = prompts.load("builder/report-repair",
                                   template=build_report.stage_template(session.workspace),
                                   problems="\n".join(f"- {issue}" for issue in found))
            session.execute_approved(request, plan)
        except RunCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - a report rewrite never undoes a finished build
            bus.log(project, "WARN", f"The report rewrite stopped: {exc}")
            return
    found = _report_problems(session)
    if found:
        bus.log(project, "WARN", "The report files still miss the Testing screen's template: "
                                 + "; ".join(found[:5]))


def _finish_run(project: str, session: Any, build_result: dict[str, Any], plan: str = "") -> dict[str, Any]:
    _conform_reports(project, session, plan)
    bus.phase(project, "build:write", "Building the application", status="complete")

    built_report = report(project)
    qa_report = session.read_record("qa", "report.json", fallback=None)
    if not (session.workspace / "package.json").is_file() or not built_report:
        raise ValueError("builder finished without a runnable app and build/report.json")
    if not isinstance(qa_report, dict) or not qa_report.get("complete"):
        if not _recoverably_incomplete(qa_report):
            raise ValueError("the single build plan ended without a complete qa/report.json")
        qa_report["complete"] = True
        session.write_record("qa", "report.json", data=qa_report)
        bus.log(project, "WARN",
               "qa/report.json had real recorded evidence but its `complete` flag was "
               "never written (likely an interrupted earlier run) - set it rather than "
               "fail a build whose testing genuinely finished.")
    # The SRS emits one stable UJ id per business journey. Derive coverage
    # from Playwright's actual result JSON rather than accepting a generic
    # E2E count or an agent-authored success sentence.
    from qa_agent import build_evidence
    derived = build_evidence.derive(session.workspace, qa_report)
    journey_coverage = (((derived.get("report") or {}).get("e2e") or {})
                        .get("journeyCoverage") or {})
    if journey_coverage.get("required") and journey_coverage.get("status") != "passed":
        missing = [*journey_coverage.get("missing", []), *journey_coverage.get("failed", [])]
        qa_report["complete"] = False
        session.write_record("qa", "report.json", data=qa_report)
        raise ValueError("E2E user-journey coverage is incomplete: "
                         + ", ".join(missing or ["no passing journey tests recorded"]))
    gaps = built_report.get("gaps") or []
    # The report is agent-authored.  A prose ``summary`` remains valid
    # evidence when its layer rows are structured, so normalize it rather
    # than crashing after all verification completed.
    summary = summary_counts(qa_report)
    failed = summary["fail"]
    store.update(project, spec_only=False, prototype_only=False,
                 build_available=True,
                 status="tested-with-failures" if failed else "tested")
    store.advance(project, "test")
    bus.agent_msg(project, "The single build plan is complete: app, focused unit tests and final checks."
                  + (f" {len(gaps)} disclosed gap(s) remain." if gaps else "")
                  + (f" {failed} test failure(s) are recorded." if failed else ""),
                  title="Build and testing complete")
    session.note(
        "The single sequential plan completed the application, focused business "
        "unit tests and final product checks. Routes delivered: "
        + ", ".join(str(r) for r in (built_report.get("routes") or []))
        + ".")
    session.finish("Single build, unit and final-check plan complete.")
    plugins.consume_handoff(project)
    show_preview(project)
    return {"report": report(project), "status": build_result.get("status", "complete"),
            "plans": [build_result.get("plan_file")]}


def _check_decision(data: Any, may_ask: bool) -> dict[str, Any]:
    """The model's turn before the plan: ready, or one question asked the way every flow asks one."""
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind == "ready":
        return {"kind": "ready"}
    if kind != "question":
        raise ValueError('"kind" must be "ready" or "question"')
    return changes.check_question(data, may_ask)


def _qa_rows(rows: list[dict[str, str]]) -> str:
    return "\n".join(f"- Q: {row.get('question', '')}\n  A: {row.get('answer', '')}" for row in rows)


def _decide(project: str, session: Any, stack: str, direction: str) -> list[dict[str, str]]:
    """Before the build is planned, the model may ask the customer what it cannot settle itself.

    Once, up front, in its own words: nothing here lists what to ask, only the prompt tells the model when to. The
    build runs straight through afterwards. A turn that does not work is skipped - a question step never fails a build.
    Returns everything decided with the customer so far, earlier builds' answers included, for the plan to build on.
    """
    from . import scaffold

    saved = session.read_record(*DECISIONS, fallback=None)
    earlier = [row for row in saved if isinstance(row, dict)] if isinstance(saved, list) else []
    answers: list[dict[str, str]] = []
    try:
        agent = session.agent("")
        while True:
            left = QUESTIONS - len(answers)
            prompt = prompts.load(
                "builder/decide", stack=stack,
                supabase=("Never ask for anything Supabase: this project's Supabase project is already connected."
                          if scaffold.uses_supabase(stack) else
                          "This stack has no Supabase: never ask for anything Supabase, and never add it."),
                direction=("The customer asked for this on top of the specification:\n\n" + direction.strip())
                if direction.strip() else "",
                earlier=("Already decided in an earlier build of this project, so not asked again:\n\n"
                         + _qa_rows(earlier) + "\n\n") if earlier else "",
                answers=("Asked and answered just now:\n\n" + _qa_rows(answers) + "\n\n") if answers else "",
                questions_left=(prompts.load("changes/questions-left", count=left).strip() if left > 0
                                else prompts.load("changes/no-questions").strip()))
            with session.lock:
                agent.set_mode("plan")
            try:
                reply = session.ask_json(prompt, validator=lambda data: _check_decision(data, left > 0))
            finally:
                with session.lock:
                    agent.set_mode("act")
            if reply["kind"] == "ready":
                break
            bus.phase(project, "build:decide", "Asking you before the build is planned", detail=reply["question"])
            given = bus.ask_and_wait(project, "question", reply["question"], options=reply["options"],
                                     agent=bus.DEVELOPER, cancelled=lambda: session.cancelled,
                                     why=reply["why"], assumption=reply["assumption"],
                                     variable=reply.get("variable", ""), secret=reply.get("secret", False),
                                     check=reply.get("check", ""))
            if given is None:
                raise RunCancelled(project)
            answers.append({"question": reply["question"],
                            "answer": given.strip() or prompts.load("changes/unanswered").strip()})
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - what was answered so far still counts; the build goes on without more
        bus.log(project, "WARN", f"The questions before the plan stopped, so the build goes on without them: {exc}")
    if answers:
        session.write_record(*DECISIONS, data=earlier + answers)
        bus.phase(project, "build:decide", "Decided with you", status="complete",
                  detail="; ".join(row["answer"] for row in answers[:6]))
    return earlier + answers


def _decided_block(answers: list[dict[str, str]]) -> str:
    if not answers:
        return ""
    return ("\n\n## Decided with the customer before this plan\n\nThese were asked and answered. Build on them "
            "and do not ask any of them again:\n\n" + _qa_rows(answers))


def run(project: str, direction: str = "") -> dict[str, Any]:
    """Build the application from everything the project already settled.

    The model may ask the customer what it cannot settle itself, once, before it plans (`_decide`). After that the
    build never stops to ask: it builds straight through, and whatever it could not settle is recorded as a gap in
    `build/report.json`.
    """
    from srs_agent import document as srs_document

    from . import scaffold

    if not srs_document.has_document(project):
        raise ValueError("write the specification before building")

    record = store.require(project)
    stack = str(record.get("stack") or "nextjs-supabase")
    session = session_for(project)
    session.begin("build", role=bus.DEVELOPER)
    try:
        # The stack's guides are staged first: the model reads them to judge whether anything needs the customer.
        reference_staging.stage(session.workspace, GUIDES_DIR, scaffold.build_guide_files(stack))
        decided = _decide(project, session, stack, direction)
        # A stack that uses Supabase (the Supabase-database ones, and the MongoDB ones that keep uploads in a bucket) gets
        # this project's own Supabase project: kept if it is already linked, otherwise created now. A later build finds the
        # record there and does nothing. A MongoDB-only stack has no Supabase and needs no Supabase account.
        if scaffold.uses_supabase(stack):
            supabase_connect.ensure_project(project, name=str(record.get("name") or project),
                                            log=lambda line: bus.agent_msg(project, line, title="Supabase"))
        installed = scaffold.install(session.workspace, stack)
        bus.agent_msg(project,
                      f"{stack} scaffold copied ({len(installed['files'])} files)."
                      if installed["scaffolded"] else "Existing application preserved; building on its files.",
                      title="Builder scaffold")
        bus.phase(project, "build:write", "Building and checking the application",
                  detail="One sequential plan: complete the app, focused business units, then final product checks.")
        request = prompts.load("builder/generate", stack=stack,
                               report_template=build_report.stage_template(session.workspace))
        request += _prototype_context_block(session.workspace)
        request += "\n\n## Scaffold installation\n" + json.dumps(installed, indent=2)
        guide_paths = reference_staging.stage(session.workspace, GUIDES_DIR,
                                              scaffold.build_guide_files(stack))
        request += ("\n\n## Stack build guides\n\nRead these yourself before planning:\n"
                    + reference_staging.as_bullets(guide_paths))
        auth = auth_guide.staged_for(session.workspace, srs_document.document(project).get("srs_document", {}))
        if auth:
            request += ("\n\n## Authentication, roles and navigation\n\n"
                        f"Read `{auth}` yourself before planning. It is the standard this app's sign-up, sign-in, cookie "
                        "sessions, role-based access, role dashboards and signed-in and signed-out navigation are built and "
                        "tested to (its section 7 is for the real application). The specification decides which roles and "
                        "pages exist; this file decides how they behave.")
        from prototype_agent import design as design_stage
        customization = design_stage.approved_customization(project)
        if customization:
            request += ("\n\n## Approved design customization\n"
                        + json.dumps({"selected_design_path": customization.get("design_md_path"),
                                      "customizer_prompt": customization.get("customizer_prompt"),
                                      "customizer_spec": customization.get("customizer_spec")},
                                     ensure_ascii=False, indent=2))
            if customization.get("design_md_workspace_path"):
                request += (f"\n\nRead `{customization['design_md_workspace_path']}` yourself for "
                            f"the selected theme's own guidance.")
        request += _decided_block(decided)
        if direction.strip():
            request += f"\n\n## What the customer asked for on top of that\n\n{direction.strip()}"

        build_result = session.run_task(request, plan_directory="plan", audit=False)
        if build_result.get("status") == "blocked":
            raise ValueError(build_result.get("text") or "the build was blocked")
        return _finish_run(project, session, build_result, build_result.get("plan") or "")
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise


def _finish_update(project: str, session: Any, result: dict[str, Any]) -> dict[str, Any]:
    session.finish(result.get("text", "") or "Change applied.")
    if result.get("status") == "complete":
        plugins.consume_handoff(project)
    show_preview(project)
    return {"status": result.get("status", "complete"), "text": result.get("text", "")}


def update(project: str, request: str) -> dict[str, Any]:
    """Change the built application from a message typed into the chat stream."""
    if not built(project):
        raise ValueError("there is nothing built to change yet")

    session = session_for(project)
    session.begin("build-edit", role=bus.DEVELOPER)
    try:
        bus.user_msg(project, request)
        full_request = prompts.load("builder/update", request=request)
        result = session.run_task(full_request, audit=False)
        return _finish_update(project, session, result)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise


def files(project: str, limit: int = 400) -> dict[str, str]:
    """The workspace as the studio's code pane reads it."""
    session = session_for(project)
    skip = {".git", "node_modules", "__pycache__", ".next", ".venv", "dist", "build", ".agentforge"}
    out: dict[str, str] = {}
    for path in sorted(session.workspace.rglob("*")):
        if len(out) >= limit:
            break
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.name in {".env", ".env.local", ".env.production"} or path.name.endswith(".secret"):
            continue
        if path.stat().st_size > 400_000:
            continue
        try:
            out[path.relative_to(session.workspace).as_posix()] = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
    return out


def save_file(project: str, path: str, content: str, note: str = "") -> dict[str, Any]:
    """A file edited in the studio's own code pane."""
    session = session_for(project)
    target = (session.workspace / path).resolve()
    if not target.is_relative_to(session.workspace.resolve()):
        raise ValueError("that path is outside the project")
    previous = target.read_text(encoding="utf-8") if target.is_file() else ""
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    bus.file_written(project, path, content, old=previous, note=note or "edited in studio")
    return {"ok": True, "path": path}
