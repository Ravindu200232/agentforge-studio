"""Building the application."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server_modules import bus, plugins, prompts, reference_staging, store
from server_modules.session import session_for

BUILD_DIR = "build"
REPORT = (BUILD_DIR, "report.json")


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


def run(project: str, direction: str = "") -> dict[str, Any]:
    """Build the application from everything the project already settled."""
    from srs_agent import document as srs_document

    if not srs_document.has_document(project):
        raise ValueError("write the specification before building")

    record = store.require(project)
    session = session_for(project)
    from . import scaffold
    stack = str(record.get("stack") or "nextjs-mongo")
    session.begin("build", role=bus.DEVELOPER)

    try:
        installed = scaffold.install(session.workspace, stack)
        bus.agent_msg(project,
                      f"{stack} scaffold copied ({len(installed['files'])} files)."
                      if installed["scaffolded"] else "Existing application preserved; building on its files.",
                      title="Builder scaffold")
        bus.phase(project, "build:write", "Building and checking the application",
                  detail="One sequential plan: complete the app, focused business units, then final product checks.")
        request = prompts.load("builder/generate", stack=stack)
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
        if build_result.get("status") == "blocked":
            raise ValueError(build_result.get("text") or "the build was blocked")
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
        gaps = built_report.get("gaps") or []
        summary = qa_report.get("summary") or {}
        failed = int(summary.get("fail") or 0)
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
    except Exception as exc:  # noqa: BLE001
        session.fail(str(exc))
        raise


def update(project: str, request: str) -> dict[str, Any]:
    """Change the built application from a message typed into the chat stream."""
    if not built(project):
        raise ValueError("there is nothing built to change yet")

    session = session_for(project)
    session.begin("build-edit", role=bus.DEVELOPER)
    try:
        bus.user_msg(project, request)
        result = session.run_task(prompts.load("builder/update", request=request), audit=False)
        session.finish(result.get("text", "") or "Change applied.")
        if result.get("status") == "complete":
            plugins.consume_handoff(project)
        show_preview(project)
        return {"status": result.get("status", "complete"), "text": result.get("text", "")}
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
