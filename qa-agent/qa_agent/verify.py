"""Testing the built application.

The report on disk is the record, and it is written after every layer rather than
once at the end — a run that is interrupted still leaves what it proved. The
studio's Testing screen reads that file directly, so a partial report is a
partial screen, not an empty one.
"""
from __future__ import annotations

import json
import re
import time
import threading
from typing import Any

from server_modules import bus, config, prompts, reference_staging, store
from server_modules.qa_report import summary_counts
from server_modules.session import ProjectSession, RunCancelled, session_for

QA_DIR = "qa"
REPORT = (QA_DIR, "report.json")


def provenance_text(value: Any) -> str:
    """How the results were produced, as the sentence the pages show.

    The agent that writes the report sometimes records it as an object (the method and the runner files); a page that
    shows it as it is cannot draw an object, and the whole testing view fails.
    """
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        method = str(value.get("method") or "").strip()
        files = value.get("runner_files")
        listed = ", ".join(str(item) for item in files) if isinstance(files, list) else ""
        text = " ".join(part for part in (method, f"Runner files: {listed}." if listed else "") if part)
        return text or json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value) if value else ""


def report(project: str) -> dict[str, Any]:
    session = session_for(project)
    saved = session.read_record(*REPORT, fallback=None)
    if not isinstance(saved, dict):
        # No Testing run yet — the build's own artifacts are still evidence.
        saved = {}
    # The id is the project's; the studio matches a report to the project open by it. An agent that writes the report
    # often puts the app's name there instead, and the results then never show.
    saved["project"] = project
    from .evidence import collect
    result = collect(session.workspace, saved)
    result["project"] = project
    result.setdefault("complete", False)
    result["provenance"] = provenance_text(result.get("provenance")) or "no verification has run for this project yet"
    return result


def _publish(session: ProjectSession, project: str, previous_rows: int) -> int:
    """Turn whatever the agent has written so far into studio test events."""
    current = report(project)
    # Rows derived from the build's own record are not live test results.
    # This file is updated live by an agent. Ignore a partial/malformed row
    # until it becomes a complete object instead of taking down the watcher.
    rows = [r for r in (current.get("timeline") or [])
            if isinstance(r, dict) and not r.get("derived")]
    for row in rows[previous_rows:]:
        bus.test_result(project,
                        status=str(row.get("status") or "run"),
                        msg=str(row.get("msg") or row.get("stage") or "check"),
                        detail=str(row.get("detail") or ""))
    return len(rows)


_RERUN = re.compile(r"\b(re-?run|run|test|check)\b.{0,40}\b(journeys?|e2e|end-to-end)\b.{0,30}\b(again|anew|fresh)\b"
                    r"|\bre-?run\b.{0,30}\b(journeys?|e2e|end-to-end)\b", re.I | re.S)


def rerun_asked(direction: str) -> bool:
    """Whether the person asked for the end-to-end journeys to run again even though the app has not changed."""
    return bool(_RERUN.search(str(direction or "")))


def run(project: str, direction: str = "") -> dict[str, Any]:
    """Verify the application, layer by layer, and publish as it goes."""
    from builder_agent import build as builder

    if not builder.built(project):
        raise ValueError("build the application before testing it")

    session = session_for(project)
    session.begin("test", role=bus.DEVELOPER)
    # Runner outputs have fixed filenames. Keep their previous state before a
    # new test run can replace it, including a run started after a chat repair.
    from .evidence import archive_results
    archive_results(session.workspace, "Before this Testing run", "before-test-run")
    bus.test_start(project)
    # The optional browser_inspect tool reads this managed preview page by page;
    # it never owns a second server or sends data outside the local machine.
    from server_modules import preview_runtime
    preview = preview_runtime.open_preview(project)
    if preview.get("status") not in {"starting", "running"}:
        bus.log(project, "WARN", f"Local preview is unavailable for browser inspection: {preview.get('detail') or 'unknown reason'}")
    started = time.time()
    published = [0]
    stop_feed = threading.Event()

    def feed() -> None:
        while not stop_feed.wait(1):
            published[0] = _publish(session, project, published[0])

    watcher = threading.Thread(target=feed, name=f"qa-feed:{project}", daemon=True)
    watcher.start()

    try:
        bus.phase(project, "qa:verify", "Verifying the application",
                  detail="Build, runtime, units, routes, journeys, accessibility and load.")
        from builder_agent.scaffold import guide_files
        stack = str(store.require(project).get("stack") or "nextjs-supabase")
        from server_modules.validation import build_report
        request = prompts.load("testing/run", project=project,
                               report_template=build_report.stage_template(session.workspace))
        guide_paths = reference_staging.stage(session.workspace, f"{config.RECORD_DIR}/{QA_DIR}/guides",
                                              guide_files(stack))
        request += ("\n\n## Selected scaffold and test guides\n\nRead these yourself before planning:\n"
                   + reference_staging.as_bullets(guide_paths))
        if direction.strip():
            request += f"\n\n## What the customer asked you to check\n\n{direction.strip()}"
        # The end-to-end journeys are the Studio's to run (`e2e_run.py`), once: reused while the app is what they last ran on,
        # run again only when the person asks for it.
        from . import e2e_run
        rerun = rerun_asked(direction)
        request += "\n\n" + prompts.load(
            "testing/journeys-reused" if e2e_run.current(session.workspace) and not rerun else "testing/journeys-studio").strip()

        # The plan already runs and records every requested layer. A second
        # agent audit repeats expensive builds/browser runs without adding UI
        # evidence, so finish from the runner-owned JSON instead.
        # The journeys' screenshots are copied as the tests take them: the next test run empties Playwright's output folder.
        from .screen_keeper import Keeper
        with Keeper(session.workspace):
            result = session.run_task(request, audit=False)
        stop_feed.set()
        watcher.join(timeout=2)
        _publish(session, project, published[0])

        # The journeys, run by the Studio: not again when this exact app already ran them, unless the person asked.
        with Keeper(session.workspace):
            ran = e2e_run.run(project, session, reason="test", force=rerun)
        if session.cancelled:
            raise RunCancelled(project)
        # A model that can look at pictures looks at the screenshots of a run that really happened (a reused one was looked
        # at when it ran), round by round, asking before each round after the first.
        from . import e2e_review
        if ran.get("status") in {"passed", "failed"}:
            e2e_review.run(project, session)
        if session.cancelled:
            raise RunCancelled(project)

        builder.settled_qa_report(project, session)
        final = report(project)
        journey_coverage = (((final.get("report") or {}).get("e2e") or {})
                            .get("journeyCoverage") or {})
        # Journeys that fail are a result of this run, never a reason to fail it or to run it again by itself.
        journeys_failed = bool(journey_coverage.get("required")) and journey_coverage.get("status") != "passed"
        summary = summary_counts(final)
        failed = summary["fail"]
        store.update(project, status="tested" if not failed and not journeys_failed else "tested-with-failures")
        store.advance(project, "test")
        bus.phase(project, "qa:verify", "Verifying the application",
                  status="complete" if not failed else "failed")

        bus.test_done(project)
        elapsed = int(time.time() - started)
        bus.agent_msg(
            project,
            f"Verification finished in {elapsed}s — {summary.get('pass', 0)} passed, "
            f"{failed} failed, {summary.get('warn', 0)} warned.",
            title="Testing complete")
        session.note(
            f"Verification finished: {summary.get('pass', 0)} passed, {failed} "
            f"failed, {summary.get('warn', 0)} warned. The evidence is at "
            f".agentforge/qa/report.json."
            + ("" if not failed else " The failures are recorded there and are "
               "the first thing to repair."))
        if journeys_failed:
            bus.agent_msg(project, builder.journey_failures_message(journey_coverage), title="Journeys that failed",
                          actions=[{"label": "Fix the failing journeys", "prompt": builder.FIX_JOURNEYS}])
        session.finish(result.get("text", "") or "Verification complete.")
        archive_results(session.workspace, "Testing run completed", "testing-run")
        return final
    except RunCancelled:
        stop_feed.set()
        watcher.join(timeout=2)
        archive_results(session.workspace, "Testing run cancelled", "testing-run")
        bus.test_done(project)
        session.stage = "idle"
        session.save_context()
        raise
    except Exception as exc:  # noqa: BLE001
        stop_feed.set()
        watcher.join(timeout=2)
        _publish(session, project, published[0])
        archive_results(session.workspace, "Testing run stopped with an error", "testing-run")
        bus.test_done(project)
        session.fail(str(exc))
        raise


def screenshot(project: str, path: str) -> tuple[bytes, str]:
    session = session_for(project)
    target = (session.workspace / path).resolve()
    if not target.is_relative_to(session.workspace.resolve()) or not target.is_file():
        raise FileNotFoundError(path)
    kind = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
    return target.read_bytes(), kind.get(target.suffix.lower(), "application/octet-stream")
