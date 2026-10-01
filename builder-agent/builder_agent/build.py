"""Building the application."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from server_modules import bus, changes, deploy_vars, plugins, prompts, reference_staging, store, supabase_connect
from server_modules.qa_report import summary_counts
from server_modules.session import RunCancelled, session_for
from server_modules.validation import build_report

BUILD_DIR = "build"
REPORT = (BUILD_DIR, "report.json")
QUESTION = (BUILD_DIR, "question.json")
PENDING = (BUILD_DIR, "pending.json")
ASKED = (BUILD_DIR, "asked.json")
GAP_REVIEW = (BUILD_DIR, "gap-review.json")
REPORT_REPAIR_ROUNDS = 2
GAP_REVIEW_ROUNDS = 2
ASKED_KEPT = 60


def report(project: str) -> dict[str, Any]:
    saved = session_for(project).read_record(*REPORT, fallback=None)
    return saved if isinstance(saved, dict) else {}


def built(project: str) -> bool:
    return bool(report(project))


def pending_question(project: str) -> dict[str, Any] | None:
    saved = session_for(project).read_record(*QUESTION, fallback=None)
    return saved if isinstance(saved, dict) and saved.get("question") else None


def waiting(project: str) -> dict[str, Any] | None:
    """A build or update paused mid-run, waiting on the customer's answer."""
    saved = session_for(project).read_record(*PENDING, fallback=None)
    return saved if isinstance(saved, dict) and saved.get("question") else None


def _ask(project: str, question: dict[str, Any]) -> None:
    bus.ask(project, "question", question["question"], options=question["options"],
           agent=bus.DEVELOPER, why=question["why"], assumption=question["assumption"],
           flow="build", variable=question.get("variable", ""),
           secret=question.get("secret", False), check=question.get("check", ""))


_SECRET_WORDS = re.compile(r"\b(passwords?|passcodes?|passphrases?|api[ _-]?keys?|access keys?|secret keys?|client secrets?"
                           r"|private keys?|secrets?|tokens?|credentials?|connection strings?)\b", re.IGNORECASE)
_ASKS_FOR_VALUE = re.compile(r"\b(what (?:is|are|should|will|would)|what(?:\s+\w+){0,2}?\s+(?:password|passcode|passphrase|key|secret"
                             r"|token|credential|connection string)s?|enter|provide|give|share|paste|type|send|set|choose)\b",
                             re.IGNORECASE)
_FILLER = {"what", "which", "is", "are", "the", "a", "an", "your", "you", "my", "our", "their", "should", "would",
           "will", "can", "could", "please", "enter", "provide", "give", "share", "paste", "type", "send", "set",
           "choose", "use", "for", "of", "to", "me", "we", "i", "do", "does", "want", "need", "new", "be", "this",
           "that", "it", "in", "on", "with", "and", "or", "here", "now", "real"}


def _private_value(question: dict[str, Any]) -> dict[str, Any]:
    """A question that asks the customer to give a password, key, token or other secret always gets the private box.

    The prompt tells the model to name a `variable` for such a value; when it did not, one is named here from the
    question's own words (`ADMIN_PASSWORD`, `STRIPE_SECRET_KEY`), so the value is typed into a box that hides it and is
    saved on this computer, never into the open chat. A question that only mentions a password while asking for a
    choice ("sign in with a password or with Google?") is left as it is.
    """
    text = str(question.get("question") or "")
    found = _SECRET_WORDS.search(text)
    if question.get("variable") or not found or not _ASKS_FOR_VALUE.search(text):
        return question
    words = lambda part: [w for w in re.findall(r"[A-Za-z0-9]+", part) if w.lower() not in _FILLER]
    around = words(text[:found.start()])[-2:] or words(text[found.end():])[:2]
    keyword = re.sub(r"S$", "", "_".join(re.findall(r"[A-Za-z0-9]+", found.group(1))).upper())
    name = re.sub(r"^[^A-Z]+", "", "_".join([w.upper() for w in around] + [keyword]))
    try:
        deploy_vars.valid_name(name)
    except ValueError:
        name = "BUILD_SECRET"
    return {**question, "variable": name, "secret": True}


_SUPABASE_VALUE = re.compile(r"\b(url|keys?|password|anon|service[ _-]?role|credentials?|project ref|ref|connection"
                             r"|token|secret)\b", re.IGNORECASE)
AUTO_ANSWERS = 2


def _asks_for_supabase(question: dict[str, Any]) -> bool:
    """Whether a question asks the customer for a Supabase value — never needed: the project is connected before a build."""
    if str(question.get("variable") or "").upper().startswith("SUPABASE"):
        return True
    text = str(question.get("question") or "")
    # Asking the customer to give a value ("what is…", "paste…", "enter…"), not a choice such as
    # "keep the images in Supabase Storage?" - that one is the customer's to answer.
    return bool(re.search(r"supabase", text, re.IGNORECASE) and _SUPABASE_VALUE.search(text)
                and _ASKS_FOR_VALUE.search(text))


def _settle(project: str, session: Any, mode: str, request: str, plan: str,
           result: dict[str, Any], auto_answered: int = 0) -> dict[str, Any]:
    """A `run_task`/`execute_approved` outcome: pass a real result through unchanged, or turn a
    genuine question the model raised into a paused, resumable wait instead of a hard failure.

    A value only the customer has - a provider credential, a real password, a business decision
    with no safe default - cannot be guessed or hardcoded, so the model is told to write
    `.agentforge/build/question.json` and stop rather than invent one. There is deliberately no
    cap on how many times a build may ask: a build has no plan card to fall back to the way a
    revised chat request does, so refusing a real question here would only leave it stuck.
    """
    if result.get("status") != "blocked":
        session.write_record(*PENDING, data={})
        return result
    question = pending_question(project)
    session.write_record(*QUESTION, data={})
    if not question:
        raise ValueError(result.get("text") or "the build was blocked")
    if _asks_for_supabase(question) and supabase_connect.record(project) and auto_answered < AUTO_ANSWERS:
        # The customer is never asked for Supabase values: the project was connected before the build started and
        # every value is already in the environment. Answer for them and carry straight on.
        bus.log(project, "INFO", "The build asked for Supabase values; this project's Supabase is already connected, "
                                 "so it was answered automatically and the build continues.")
        resume = request + "\n" + prompts.load("builder/resume", question=question.get("question", ""),
                                                answer=prompts.load("builder/supabase-connected").strip())
        return _settle(project, session, mode, request, plan, session.execute_approved(resume, plan, model=""),
                       auto_answered + 1)
    asked = changes.check_question({"kind": "question", **_private_value(question)}, True)
    session.write_record(*PENDING, data={"mode": mode, "request": request, "plan": plan, "question": asked})
    _ask(project, asked)
    session.finish("Waiting for your answer.")
    return {"status": "asking", "question": asked}


def _key(text: Any) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text or "").lower()))


def _asked(session: Any) -> list[dict[str, str]]:
    """Every question the builds of this project really asked the customer, with the answer given."""
    saved = session.read_record(*ASKED, fallback=None)
    return [row for row in saved if isinstance(row, dict)] if isinstance(saved, list) else []


def _remember(session: Any, question: dict[str, Any], answer: str) -> None:
    rows = [*_asked(session), {"question": str(question.get("question") or ""), "answer": answer}]
    session.write_record(*ASKED, data=rows[-ASKED_KEPT:])


def _review_state(session: Any) -> dict[str, Any]:
    saved = session.read_record(*GAP_REVIEW, fallback=None)
    saved = saved if isinstance(saved, dict) else {}
    reviewed, rounds = saved.get("reviewed"), saved.get("rounds")
    return {"reviewed": [str(key) for key in reviewed] if isinstance(reviewed, list) else [],
            "rounds": rounds if isinstance(rounds, int) else 0}


def _gap_key(gap: dict[str, Any]) -> str:
    return _key(gap.get("item") or gap.get("area"))


def _was_asked(gap: dict[str, Any], questions: set[str]) -> bool:
    said = _key(gap.get("asked"))
    return bool(said) and any(said == q or (min(len(said), len(q)) >= 24 and (said in q or q in said))
                              for q in questions)


def open_gaps(session: Any) -> list[dict[str, Any]]:
    """The gaps in the build report the customer has not been asked about yet.

    A gap counts as asked only when its `asked` names a question the customer really saw, or when it already
    went through a gap review in this build. A gap's own wording ("the customer was asked") is not taken on trust.
    """
    built_report = session.read_record(*REPORT, fallback=None)
    gaps = built_report.get("gaps") if isinstance(built_report, dict) else None
    if not isinstance(gaps, list):
        return []
    questions = {_key(row.get("question")) for row in _asked(session)} - {""}
    reviewed = set(_review_state(session)["reviewed"])
    return [gap for gap in gaps if isinstance(gap, dict) and _gap_key(gap)
            and _gap_key(gap) not in reviewed and not _was_asked(gap, questions)]


def _review_gaps(project: str, session: Any, mode: str, plan: str) -> dict[str, Any] | None:
    """Go through every gap the build recorded with the customer before the build is called finished.

    What each gap needs and what to ask about it is the model's to work out from the gap itself: nothing here
    knows about payments, sign-in or any other kind of gap. This only makes sure no recorded gap is left without
    the customer being asked, a bounded number of times. Returns the paused state while a question waits.
    """
    state = _review_state(session)
    while state["rounds"] < GAP_REVIEW_ROUNDS:
        gaps = open_gaps(session)
        if not gaps:
            return None
        state = {"reviewed": [*state["reviewed"], *(_gap_key(gap) for gap in gaps)], "rounds": state["rounds"] + 1}
        session.write_record(*GAP_REVIEW, data=state)
        bus.agent_msg(project, f"{len(gaps)} thing(s) are recorded as not done or not proven. Going through them "
                               "with you before the build finishes.", title="Recorded gaps")
        answers = "\n".join(f"- Q: {row.get('question', '')}\n  A: {row.get('answer', '')}"
                            for row in _asked(session)) or "- nothing yet"
        request = prompts.load("builder/gaps", gaps=json.dumps(gaps, ensure_ascii=False, indent=2),
                               answers=answers, report_template=build_report.stage_template(session.workspace))
        try:
            settled = _settle(project, session, mode, request, plan, session.execute_approved(request, plan, model=""))
        except RunCancelled:
            raise
        except Exception as exc:  # noqa: BLE001 - a finished build is never failed over its gap review
            bus.log(project, "WARN", f"Going through the recorded gaps stopped: {exc}")
            return None
        if settled.get("status") == "asking":
            return settled
    return None


def _done(project: str, session: Any, mode: str, plan: str, result: dict[str, Any]) -> dict[str, Any]:
    """The build's own work is finished: settle its recorded gaps with the customer, then finish."""
    asking = _review_gaps(project, session, mode, plan)
    if asking:
        return asking
    return _finish_run(project, session, result, plan) if mode == "run" else _finish_update(project, session, result)


def answer(project: str, reply: str) -> dict[str, Any]:
    """Continue a build or update that paused to ask the customer something.

    Resumes the same agent conversation with the answer folded in - never a fresh separate
    request - so work already finished is not redone and the plan already approved still holds.
    """
    pending = waiting(project)
    if not pending:
        raise ValueError("this project has no build or update waiting on a question")
    session = session_for(project)
    text = reply.strip() or prompts.load("changes/unanswered").strip()
    request = pending.get("request") or ""
    plan = pending.get("plan") or ""
    mode = pending.get("mode") or "run"
    question = pending.get("question") or {}
    _remember(session, question, reply.strip() or f"left it to the build: {question.get('assumption') or 'its recommendation'}")
    resume_request = request + "\n" + prompts.load(
        "builder/resume", question=question.get("question", ""), answer=text)
    session.begin("build" if mode == "run" else "build-edit", role=bus.DEVELOPER)
    try:
        result = session.execute_approved(resume_request, plan, model="")
        settled = _settle(project, session, mode, request, plan, result)
        if settled.get("status") == "asking":
            return settled
        return _done(project, session, mode, plan, settled)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise


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


def run(project: str, direction: str = "") -> dict[str, Any]:
    """Build the application from everything the project already settled."""
    from srs_agent import document as srs_document

    if not srs_document.has_document(project):
        raise ValueError("write the specification before building")
    if waiting(project):
        raise ValueError("this project already has a build waiting on an earlier question - "
                         "answer it before starting another")

    record = store.require(project)
    session = session_for(project)
    from . import scaffold
    stack = str(record.get("stack") or "nextjs-supabase")
    session.begin("build", role=bus.DEVELOPER)
    session.write_record(*GAP_REVIEW, data={})  # this build's own gaps all go to the customer again

    try:
        # Every stack here is Supabase-backed: the one real project this AgentForge project gets
        # is created now, the first time it actually builds (signing in to the Supabase account
        # itself already happened from the stack picker - see supabase_connect.py's OAuth flow). A
        # later build of the same project finds the record already there and does nothing.
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
        guide_paths = reference_staging.stage(session.workspace, "build/guides",
                                              scaffold.build_guide_files(stack))
        request += ("\n\n## Stack build guides\n\nRead these yourself before planning:\n"
                   + reference_staging.as_bullets(guide_paths))
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
        if direction.strip():
            request += f"\n\n## What the customer asked for on top of that\n\n{direction.strip()}"

        build_result = session.run_task(request, plan_directory="plan", audit=False)
        settled = _settle(project, session, "run", request, build_result.get("plan") or "", build_result)
        if settled.get("status") == "asking":
            return settled
        return _done(project, session, "run", build_result.get("plan") or "", settled)
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
    if waiting(project):
        raise ValueError("this project already has a change waiting on an earlier question - "
                         "answer it before starting another")

    session = session_for(project)
    session.begin("build-edit", role=bus.DEVELOPER)
    # Only gaps this change adds are new to the customer; those already gone through stay settled.
    session.write_record(*GAP_REVIEW, data={**_review_state(session), "rounds": 0})
    try:
        bus.user_msg(project, request)
        full_request = prompts.load("builder/update", request=request)
        result = session.run_task(full_request, audit=False)
        settled = _settle(project, session, "update", full_request, result.get("plan") or "", result)
        if settled.get("status") == "asking":
            return settled
        return _done(project, session, "update", result.get("plan") or "", settled)
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
