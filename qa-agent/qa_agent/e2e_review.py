"""After the end-to-end tests finish, a model that can look at pictures reviews their screenshots, and what it finds is fixed.

Playwright keeps a screenshot of the screen each test ended on, at desktop and at mobile width. Those pictures are shown to the
model, test by test, journeys first: it says what is visibly wrong with the real application (an error shown to the person,
cut-off or overlapping text, a broken layout, an image that did not load, a screen with no styling). The problems that matter
are given to the agent to fix in the application's source, and told to run the journey suite again, so every journey's
evidence is current. The tests whose screens had problems are then looked at once more, from their new screenshots, and what
is still wrong is reported as it is. All of it is in the chat stream, with the pictures.

The pictures are kept while the tests run (`screen_keeper.py`): Playwright empties its output folder at the start of every run,
so without that a later run (the accessibility check, a re-run of one test) would take the journeys' screens away before they
are looked at.

A model that cannot look at pictures (Ollama says so: `server_modules/vision.py`, and the model picker marks the ones that can)
does not review, but the screens are still shown in the chat, with a line saying they were not checked. A review that is turned
off, and a run that left no screenshots, say so in the chat too, with what the test runs on disk show: the person is never
left wondering why the screens were not looked at. None of this is an error, and nothing here ever fails the testing: it is a
review, not a gate.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from server_modules import bus, config, llm, prompts, screen_review
from server_modules.session import RunCancelled

from . import build_evidence

PHASE = "qa:review"
REPORT = ".agentforge/qa/visual-review.json"
MAX_TESTS = 18
# Playwright's projects, and the width each is shown to the model as.
VIEWPORT_OF = {"desktop": "desktop", "mobile": "mobile"}
_JOURNEY = re.compile(r"^\s*\[UJ-", re.I)
_SKIP_SPECS = re.compile(r"a11y|axe|accessib", re.I)


def enabled() -> bool:
    return bool(config.setting("e2e_visual_review", True))


def screens(workspace: Path) -> list[dict[str, Any]]:
    """The newest screenshot of every end-to-end test, as one entry per test with a picture per browser:
    {"file", "title", "status", "pictures": {"desktop": path, "mobile": path}}, user journeys first.

    Playwright overwrites its results on every run and a re-run may cover only a few tests, so each test's newest run
    speaks for it, whichever run that was."""
    latest: dict[tuple[str, str, str], dict[str, Any]] = {}
    for run in sorted(build_evidence._runs_found(workspace), key=lambda r: (str(r.get("at") or ""), r.get("rank", 0))):  # noqa: SLF001
        for test in run.get("tests") or []:
            project = str(test.get("project") or "")
            if test.get("screenshot") and project in VIEWPORT_OF and not _SKIP_SPECS.search(str(test.get("file") or "")):
                latest[(str(test.get("file") or ""), str(test.get("title") or ""), project)] = test
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for (file, title, project), test in latest.items():
        group = groups.setdefault((file, title), {"file": file, "title": title, "status": "passed", "pictures": {}})
        group["pictures"][VIEWPORT_OF[project]] = str(test["screenshot"])
        if test.get("status") in {"failed", "flaky"}:
            group["status"] = test["status"]
    ordered = sorted(groups.values(), key=lambda g: (0 if _JOURNEY.match(g["title"]) else 1, g["file"], g["title"]))
    return ordered[:MAX_TESTS]


def _digest(workspace: Path, group: dict[str, Any]) -> str:
    """What the pictures of one test are now, to know after the fix whether the test ran again."""
    parts = []
    for viewport in sorted(group["pictures"]):
        try:
            parts.append(hashlib.sha256((workspace / group["pictures"][viewport]).read_bytes()).hexdigest())
        except OSError:
            parts.append("")
    return "|".join(parts)


def _pictures(workspace: Path, group: dict[str, Any]) -> tuple[list[bytes], list[dict[str, str]], list[str]]:
    """The pictures of one test: their bytes, the chat's thumbnails and which widths they are, desktop first."""
    names = [v for v in ("desktop", "mobile") if v in group["pictures"]]
    return ([(workspace / group["pictures"][v]).read_bytes() for v in names],
            [{"path": group["pictures"][v], "label": f"{group['title']} · {v}"} for v in names], names)


def _review_group(project: str, model: str, workspace: Path, group: dict[str, Any]) -> dict[str, Any] | None:
    data, thumbs, widths = _pictures(workspace, group)
    if not data:
        return None
    spec = group["file"] if "/" in group["file"] else f"e2e/{group['file']}"      # the report names the file, not its folder
    request = prompts.load(
        "testing/visual-review", test=group["title"], spec=spec,
        pictures=" and ".join(f"picture {i + 1} is the {name} browser" for i, name in enumerate(widths)) + ".",
        status=" — this test FAILED, so the screen shows where it stopped" if group["status"] == "failed"
        else (" — this test was flaky (it passed only on a retry)" if group["status"] == "flaky" else " — this test passed"))
    answer = llm.complete_json(screen_review.SYSTEM, request, screen_review.clean, label="visual review", model=model,
                               images=data, project=project, role=bus.DEVELOPER)
    return {"file": group["file"], "title": group["title"], "name": group["title"], **answer, "thumbs": thumbs,
            "heading": f"### {group['title']} — `{spec}` ({' and '.join(widths)})"}


def _why_none(workspace: Path) -> str:
    """What the test runs on disk say about why there is not one screenshot to look at."""
    runs = build_evidence._runs_found(workspace)  # noqa: SLF001
    if not runs:
        return ("no end-to-end test run was recorded (there is no test-results/results.json, and no run was kept in "
                ".agentforge/qa/runs)")
    tests = [t for run in runs for t in run.get("tests") or []]
    seen = sorted({str(t.get("project") or "?") for t in tests})
    if not any(t.get("screenshot") for t in tests):
        return (f"{len(runs)} test run(s) with {len(tests)} test(s) ({', '.join(seen)}) were recorded, but none of them has a "
                "screenshot file left")
    return ("the only screenshots left are the accessibility checks' and other browsers', and only the desktop and mobile "
            "ones of the journeys and pages are reviewed")


def _show(project: str, workspace: Path, groups: list[dict[str, Any]], why: str) -> None:
    """The screenshots in the chat without a verdict, for when nothing can look at them: the person still sees what the tests saw."""
    plural = screen_review.plural
    bus.agent_msg(project, f"Showing the screens of {plural(len(groups), 'end-to-end test')} below, but they were not checked "
                           f"by looking at them: {why}.", title="Screenshot review skipped", kind="narration", agent=bus.DEVELOPER)
    for group in groups:
        try:
            _data, thumbs, widths = _pictures(workspace, group)
        except OSError:
            continue
        outcome = {"failed": "this test FAILED, so the screen shows where it stopped", "flaky": "this test was flaky"}.get(
            group["status"], "this test passed")
        bus.agent_msg(project, f"{outcome.capitalize()} ({' and '.join(widths)}). Not checked by looking.",
                      title=f"{group['title']} · {group['status']}", kind="visual_review", agent=bus.DEVELOPER, images=thumbs)


def run(project: str, session: Any, fix: bool = True, model: str = "", force: bool = False) -> dict[str, Any]:
    """Review the end-to-end screenshots with a vision model and fix what it finds (`fix`: false only looks and reports).
    `model` is the one this run chose, else the project's; `force` runs it even when the setting turns it off, because it
    was asked for. Always returns a result, never raises, and never ends without saying in the chat why it did not look."""
    if not enabled() and not force:
        bus.agent_msg(project, "The end-to-end screenshots were not looked at: the screenshot review is turned off "
                               "(the e2e_visual_review setting).", title="Screenshot review skipped", kind="narration",
                      agent=bus.DEVELOPER)
        return {"status": "off"}
    try:
        groups = screens(session.workspace)
        if not groups:
            bus.agent_msg(project, f"There are no end-to-end screenshots to look at: {_why_none(session.workspace)}. "
                                   "Run the end-to-end tests (`npm run qa:e2e`), then ask for this review again.",
                          title="Screenshot review skipped", kind="narration", agent=bus.DEVELOPER)
            return {"status": "skipped", "reason": "the end-to-end tests left no screenshots"}
        model = str(session.agent(model).model)
        ok, why = screen_review.can_review(model)
        if not ok:
            _show(project, session.workspace, groups, why)
            return {"status": "skipped", "reason": why}
        return _review(project, session, model, groups, fix)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - a review is never a reason to fail the testing
        bus.phase(project, PHASE, "Checking the test screenshots with a vision model", status="failed",
                  detail=str(exc)[:300], agent=bus.DEVELOPER)
        bus.log(project, "WARN", f"The screenshot review stopped: {str(exc)[:300]}", agent=bus.DEVELOPER)
        return {"status": "failed", "reason": str(exc)[:300]}


def _review(project: str, session: Any, model: str, groups: list[dict[str, Any]], fix: bool = True) -> dict[str, Any]:
    workspace = session.workspace
    plural = screen_review.plural
    bus.phase(project, PHASE, "Checking the test screenshots with a vision model",
              detail=f"{model} looks at the screen each end-to-end test ended on.", agent=bus.DEVELOPER)
    bus.agent_msg(project, f"Looking at the screenshots of {plural(len(groups), 'end-to-end test')} with {model}.",
                  title="Screenshot review", kind="narration", agent=bus.DEVELOPER)

    def look(items: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
        counted = [0]

        def one(group: dict[str, Any]) -> dict[str, Any] | None:
            if session.cancelled:
                raise RunCancelled(project)
            result = _review_group(project, model, workspace, group)
            counted[0] += 1
            bus.progress(project, label, counted[0] * 100 / len(items), agent=bus.DEVELOPER)
            if result:
                screen_review.tell(project, result, bus.DEVELOPER)
            return result

        found = llm.in_lanes(items, one, on_error=lambda group, exc: {
            "file": group["file"], "title": group["title"], "name": group["title"], "looks_ok": False, "summary": "",
            "defects": [], "error": str(exc)[:200], "thumbs": [], "heading": ""})
        if session.cancelled:
            raise RunCancelled(project)
        return [f for f in found if f]

    first = look(groups, "Looking at the test screenshots")
    problems = sum(len(f["defects"]) for f in first)
    unreviewed = [f["name"] for f in first if f.get("error")]

    request, count = screen_review.fix_request(first)
    second: list[dict[str, Any]] = []
    rechecked: list[str] = []
    not_rerun: list[str] = []
    fix_stopped = ""
    if count and fix:
        if session.cancelled:
            raise RunCancelled(project)
        bad = {(f["file"], f["title"]) for f in first if any(d["severity"] in screen_review.FIX_SEVERITIES for d in f["defects"])}
        bus.agent_msg(project, f"{plural(count, 'problem')} worth fixing found on {plural(len(bad), 'test screen')}. "
                               "Fixing them in the application, then running the journeys again.",
                      title="Screenshot review", kind="narration", agent=bus.DEVELOPER)
        before = {(g["file"], g["title"]): _digest(workspace, g) for g in groups}
        fix_stopped = screen_review.run_fix(project, session, prompts.load("testing/visual-fix", defects=request), model,
                                            bus.DEVELOPER, "Screenshot review")
        now = {(g["file"], g["title"]): g for g in screens(workspace)}
        # Only the tests that had problems, and whose screenshots are new, are looked at again.
        again = [now[key] for key in sorted(bad) if key in now and _digest(workspace, now[key]) != before.get(key)]
        not_rerun = [title for (_file, title) in sorted(bad) if (_file, title) not in {(g["file"], g["title"]) for g in again}]
        rechecked = [g["title"] for g in again]
        if again:
            bus.agent_msg(project, f"Looking again at {plural(len(again), 'test screen')} that ran again.",
                          title="Screenshot review", kind="narration", agent=bus.DEVELOPER)
            second = look(again, "Looking at the new test screenshots")
    bus.progress(project, "Looking at the test screenshots", 100, agent=bus.DEVELOPER)

    final = {(f["file"], f["title"]): f for f in first}
    final.update({(f["file"], f["title"]): f for f in second if not f.get("error")})
    remaining = [(f, d) for f in final.values() for d in f["defects"] if d["severity"] in screen_review.FIX_SEVERITIES]
    report = {"model": model, "tests": len(groups), "problems_found": problems, "rechecked": rechecked,
              "not_rechecked": not_rerun, "fix_stopped": fix_stopped, "tests_not_reviewed": unreviewed,
              "remaining": [{"test": f["title"], "file": f["file"], **d} for f, d in remaining]}
    try:
        target = workspace / REPORT
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    summary = f"Looked at the screenshots of {plural(len(groups), 'end-to-end test')} with {model}: "
    if not problems:
        summary += "no problems found."
    elif not fix:
        summary += f"{plural(problems, 'problem')} found; nothing was changed, this was a review only."
    else:
        summary += f"{plural(problems, 'problem')} found"
        if count:
            summary += (f"; {plural(len(rechecked), 'test screen')} looked at again after the fix"
                        + (f", {plural(len(remaining), 'problem')} still visible." if remaining else ", none left that matters."))
            if not_rerun:
                summary += (f" {plural(len(not_rerun), 'test')} did not run again, so "
                            f"{'its' if len(not_rerun) == 1 else 'their'} fix was not checked by looking: {', '.join(not_rerun[:6])}.")
        else:
            summary += "; none that needed fixing."
    if fix_stopped:
        summary += f" The fix stopped before it was finished ({fix_stopped})."
    if unreviewed:
        summary += f" Could not be reviewed: {', '.join(unreviewed)}."
    bus.agent_msg(project, summary, title="Screenshot review", kind="narration", agent=bus.DEVELOPER)
    bus.phase(project, PHASE, "Checking the test screenshots with a vision model", status="complete", agent=bus.DEVELOPER)
    return {"status": "done", **report}
