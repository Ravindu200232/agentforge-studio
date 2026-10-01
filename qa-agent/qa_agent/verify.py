"""Testing the built application.

The report on disk is the record, and it is written after every layer rather than
once at the end — a run that is interrupted still leaves what it proved. The
studio's Testing screen reads that file directly, so a partial report is a
partial screen, not an empty one.
"""
from __future__ import annotations

import time
import threading
from typing import Any

from server_modules import bus, config, prompts, reference_staging, store
from server_modules.qa_report import summary_counts
from server_modules.session import ProjectSession, RunCancelled, session_for

QA_DIR = "qa"
REPORT = (QA_DIR, "report.json")


def report(project: str) -> dict[str, Any]:
    session = session_for(project)
    saved = session.read_record(*REPORT, fallback=None)
    if not isinstance(saved, dict):
        # No Testing run yet — the build's own artifacts are still evidence.
        saved = {}
    saved.setdefault("project", project)
    from .evidence import collect
    result = collect(session.workspace, saved)
    result.setdefault("complete", False)
    result.setdefault("provenance", "no verification has run for this project yet")
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

        # The plan already runs and records every requested layer. A second
        # agent audit repeats expensive builds/browser runs without adding UI
        # evidence, so finish from the runner-owned JSON instead.
        result = session.run_task(request, audit=False)
        stop_feed.set()
        watcher.join(timeout=2)
        _publish(session, project, published[0])

        final = report(project)
        if not final.get("complete"):
            raise ValueError("testing ended without a complete QA report")
        journey_coverage = (((final.get("report") or {}).get("e2e") or {})
                            .get("journeyCoverage") or {})
        if journey_coverage.get("required") and journey_coverage.get("status") != "passed":
            missing = [*journey_coverage.get("missing", []), *journey_coverage.get("failed", [])]
            saved = session.read_record(*REPORT, fallback={})
            if isinstance(saved, dict):
                saved["complete"] = False
                session.write_record(*REPORT, data=saved)
            raise ValueError("E2E user-journey coverage is incomplete: "
                             + ", ".join(missing or ["no passing journey tests recorded"]))
        summary = summary_counts(final)
        failed = summary["fail"]
        store.update(project, status="tested" if not failed else "tested-with-failures")
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
