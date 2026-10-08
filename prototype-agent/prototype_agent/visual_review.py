"""A model that can look at pictures reviews every prototype page, and what it finds is fixed.

After the prototype is made, every page is photographed in a browser that is already on the computer (`screens.py`, silent:
no window, nothing the person is signed in to touched) at desktop and mobile width, and the pictures go to the model. It says
what is visibly wrong with each page (cut-off text, broken layout, a missing image, unreadable contrast); the problems that
matter are given to the agent to fix in the prototype app's source, which is then built again; the pages that had problems
are photographed and looked at once more, and what is still wrong is reported as it is. All of it is in the chat stream, with
the pictures.

A model that cannot look at pictures (Ollama says so: `server_modules/vision.py`, and the model picker marks the ones that
can) skips all of this, with one line saying why. So does a computer with no browser to take the pictures with. Neither is an
error, and nothing here ever fails the prototype: it is a review, not a gate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from server_modules import bus, config, llm, prompts, screen_review, web_app
from server_modules.session import RunCancelled

from . import screens

PHASE = "prototype:review"
REPORT = "report.json"
SYSTEM = screen_review.SYSTEM
MAX_DEFECTS = screen_review.MAX_DEFECTS
FIX_SEVERITIES = screen_review.FIX_SEVERITIES
_ORDER = screen_review.ORDER
_clean = screen_review.clean


def enabled() -> bool:
    return bool(config.setting("prototype_visual_review", True))


def can_review(model: str, cancelled=None) -> tuple[bool, str]:
    """Whether `model` can be shown screenshots and there is a browser to take them: (ok, why not)."""
    try:
        return screen_review.can_review(model, need_browser=True, cancelled=cancelled)
    except InterruptedError as exc:
        raise RunCancelled("prototype") from exc


def _images(root: Path, shots: list[dict[str, Any]], route: str) -> tuple[list[bytes], list[dict[str, str]], list[str]]:
    """The pictures of one page: their bytes, the chat's thumbnails, and which viewports they are, desktop first."""
    mine = sorted((s for s in shots if s["route"] == route and s["path"]),
                  key=lambda s: list(screens.VIEWPORTS).index(s["viewport"]))
    return ([(root / s["path"]).read_bytes() for s in mine],
            [{"path": f"{config.RECORD_DIR}/prototype/{s['path']}", "label": f"{route} · {s['viewport']}"} for s in mine],
            [s["viewport"] for s in mine])


def _review_page(project: str, model: str, root: Path, row: dict[str, Any], shots: list[dict[str, Any]]) -> dict[str, Any] | None:
    data, thumbs, viewports = _images(root, shots, str(row["route"]))
    if not data:
        return None
    name = row.get("name") or row["route"]
    request = prompts.load(
        "prototype/visual-review", page=name, route=row["route"],
        pictures=" and ".join(f"picture {i + 1} is the {width} width" for i, width in enumerate(viewports)) + ".")
    answer = llm.complete_json(SYSTEM, request, _clean, label="visual review", model=model, images=data,
                               project=project, role=bus.DESIGNER)
    return {"route": row["route"], "name": name, **answer, "thumbs": thumbs,
            "heading": f"### {name} (route `{row['route']}`)"}


def _tell(project: str, result: dict[str, Any]) -> None:
    screen_review.tell(project, result, bus.DESIGNER)


def run(project: str, session: Any, rows: list[dict[str, Any]],
        fix: bool = True, model: str = "", force: bool = False) -> dict[str, Any]:
    """Review the prototype's pages with a vision model and fix what it finds (`fix`: false only looks and reports).
    `model` is the one this run chose, else the project's; `force` runs it even when the setting turns it off, because it
    was asked for. Always returns a result, never raises."""
    if not enabled() and not force:
        return {"status": "off"}
    try:
        model = str(session.agent(model).model)
        ok, why = can_review(model, cancelled=lambda: bool(session.cancelled))
        if not ok:
            bus.agent_msg(project, f"The screens were not checked by looking at them: {why}.",
                          title="Visual review skipped", kind="narration", agent=bus.DESIGNER)
            return {"status": "skipped", "reason": why}
        return _review(project, session, model, rows, fix)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - a review is never a reason to fail the prototype
        bus.phase(project, PHASE, "Checking the screens with a vision model", status="failed", detail=str(exc)[:300],
                  agent=bus.DESIGNER)
        bus.log(project, "WARN", f"The visual review stopped: {str(exc)[:300]}", agent=bus.DESIGNER)
        return {"status": "failed", "reason": str(exc)[:300]}


def _review(project: str, session: Any, model: str, rows: list[dict[str, Any]], fix: bool = True) -> dict[str, Any]:
    root = session.record / "prototype"
    bus.phase(project, PHASE, "Checking the screens with a vision model",
              detail=f"{model} looks at every screen at desktop and mobile width.", agent=bus.DESIGNER)
    bus.agent_msg(project, f"Taking a silent screenshot of each of the {len(rows)} screens, at desktop and mobile width, "
                           f"for {model} to look at.", title="Visual review", kind="narration", agent=bus.DESIGNER)

    def photograph(pages: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
        return screens.capture_all(root, pages, on_done=lambda done, total: bus.progress(
            project, label, done * 100 / total, agent=bus.DESIGNER),
            cancelled=lambda: bool(session.cancelled))

    def look(pages: list[dict[str, Any]], shots: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
        counted = [0]

        def one(row: dict[str, Any]) -> dict[str, Any] | None:
            if session.cancelled:
                raise RunCancelled(project)
            result = _review_page(project, model, root, row, shots)
            counted[0] += 1
            bus.progress(project, label, counted[0] * 100 / len(pages), agent=bus.DESIGNER)
            if result:
                _tell(project, result)
            return result

        found = llm.in_lanes(pages, one, on_error=lambda row, exc: {
            "route": row["route"], "name": row.get("name") or row["route"], "looks_ok": False,
            "summary": "", "defects": [], "error": str(exc)[:200], "thumbs": []})
        if session.cancelled:
            raise RunCancelled(project)
        return [f for f in found if f]

    shots = photograph(rows, "Taking screenshots")
    failed = [s for s in shots if not s["path"]]
    if len(failed) == len(shots):
        raise ValueError("the browser could not draw any screen: " + (failed[0]["error"] if failed else "no screens"))
    first = look(rows, shots, "Looking at the screens")
    problems = sum(len(f["defects"]) for f in first)
    unreviewed = [f["name"] for f in first if f.get("error")]

    fixed_pages: list[str] = []
    fix_stopped = ""
    second: list[dict[str, Any]] = []
    request, count = screen_review.fix_request(first)
    if count and fix:
        if session.cancelled:
            raise RunCancelled(project)
        worth = [f for f in first if any(d["severity"] in FIX_SEVERITIES for d in f["defects"])]
        bus.agent_msg(project, f"{count} problem{'s' if count != 1 else ''} worth fixing found on {len(worth)} "
                               "screen(s). Fixing them in the prototype app.", title="Visual review",
                      kind="narration", agent=bus.DESIGNER)
        app = root / "app"
        before = web_app.fingerprint(app)
        fix_stopped = screen_review.run_fix(
            project, session, prompts.load("prototype/visual-fix", defects=request,
                                           skill=web_app.stage_skill(project),
                                           app=app.relative_to(session.workspace).as_posix()),
            model, bus.DESIGNER, "Visual review")
        if web_app.fingerprint(app) != before:
            web_app.ensure_built(session, project, "prototype", agent=bus.DESIGNER)
            bus.prototype_changed(project)
            # One app: what changed may be shared by every page, so the pages that had problems are looked at again.
            again = [r for r in rows if r["route"] in {f["route"] for f in worth}]
            fixed_pages = [str(r["route"]) for r in again]
            bus.agent_msg(project, f"Looking again at the {len(again)} screen{'s' if len(again) != 1 else ''} that had problems.",
                          title="Visual review", kind="narration", agent=bus.DESIGNER)
            second = look(again, photograph(again, "Taking screenshots again"), "Looking at the changed screens")
    bus.progress(project, "Looking at the screens", 100, agent=bus.DESIGNER)

    final = {f["route"]: f for f in first}
    final.update({f["route"]: f for f in second if not f.get("error")})
    remaining = [(f, d) for f in final.values() for d in f["defects"] if d["severity"] in FIX_SEVERITIES]
    report = {"model": model, "pages": len(rows), "problems_found": problems, "fixed_pages": fixed_pages,
              "fix_stopped": fix_stopped,
              "remaining": [{"route": f["route"], **d} for f, d in remaining],
              "pages_not_reviewed": unreviewed, "screens_without_picture": [s["route"] + " " + s["viewport"] for s in failed]}
    try:
        (root / screens.REVIEW_DIR).mkdir(parents=True, exist_ok=True)
        (root / screens.REVIEW_DIR / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    summary = (f"Looked at {len(rows)} screen{'s' if len(rows) != 1 else ''} with {model}: "
               + ("no problems found." if not problems else
                  f"{problems} problem{'s' if problems != 1 else ''} found; nothing was changed, this was a review only." if not fix else
                  f"{problems} problem{'s' if problems != 1 else ''} found"
                  + (f", {len(fixed_pages)} screen{'s' if len(fixed_pages) != 1 else ''} looked at again after the fix" if fixed_pages else "")
                  + (f"; {len(remaining)} still visible after the fix." if remaining else "; none left that matters.")))
    if fix_stopped:
        summary += f" The fix stopped before it was finished ({fix_stopped})."
    if unreviewed:
        summary += f" Could not be reviewed: {', '.join(unreviewed)}."
    bus.agent_msg(project, summary, title="Visual review", kind="narration", agent=bus.DESIGNER)
    bus.phase(project, PHASE, "Checking the screens with a vision model", status="complete", agent=bus.DESIGNER)
    return {"status": "done", **report}
