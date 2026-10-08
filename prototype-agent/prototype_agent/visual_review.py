"""A model that can look at pictures reviews every prototype page, and what it finds is fixed.

After the prototype is bundled, every page is photographed in a browser that is already on the computer (`screens.py`, silent:
no window, nothing the person is signed in to touched) at desktop and mobile width, and the pictures go to the model. It says
what is visibly wrong with each page (cut-off text, broken layout, a missing image, unreadable contrast, a signed-out header
on a signed-in page); the problems that matter are given to the agent to fix in the prototype's files; the app is bundled again, the pages that
changed are photographed and looked at once more, and what is still wrong is reported as it is. All of it is in the chat stream, with
the pictures.

A model that cannot look at pictures (Ollama says so: `server_modules/vision.py`, and the model picker marks the ones that
can) skips all of this, with one line saying why. So does a computer with no browser to take the pictures with. Neither is an
error, and nothing here ever fails the prototype: it is a review, not a gate.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from server_modules import bus, config, llm, prompts, screen_review
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


def _images(root: Path, shots: list[dict[str, Any]], file: str) -> tuple[list[bytes], list[dict[str, str]], list[str]]:
    """The pictures of one page: their bytes, the chat's thumbnails, and which viewports they are, desktop first."""
    mine = sorted((s for s in shots if s["file"] == file and s["path"]),
                  key=lambda s: list(screens.VIEWPORTS).index(s["viewport"]))
    return ([(root / s["path"]).read_bytes() for s in mine],
            [{"path": f"{config.RECORD_DIR}/prototype/{s['path']}", "label": f"{file} · {s['viewport']}"} for s in mine],
            [s["viewport"] for s in mine])


def _review_page(project: str, model: str, root: Path, row: dict[str, Any], shots: list[dict[str, Any]],
                 email: str) -> dict[str, Any] | None:
    data, thumbs, viewports = _images(root, shots, str(row["file"]))
    if not data:
        return None
    request = prompts.load(
        "prototype/visual-review", page=row.get("name") or row["route"], route=row["route"], file=row["file"],
        pictures=" and ".join(f"picture {i + 1} is the {name} width" for i, name in enumerate(viewports)) + ".",
        signed_in=f", shown signed in as the demo account {email}" if email else ", shown signed out")
    answer = llm.complete_json(SYSTEM, request, _clean, label="visual review", model=model, images=data,
                               project=project, role=bus.DESIGNER)
    name = row.get("name") or row["route"]
    return {"route": row["route"], "file": row["file"], "name": name, **answer, "thumbs": thumbs,
            "heading": f"### `{row['file']}` — {name} (route `{row['route']}`)"}


def _tell(project: str, result: dict[str, Any]) -> None:
    screen_review.tell(project, result, bus.DESIGNER)


SHARED = "shared"


def _fingerprint(root: Path, rows: list[dict[str, Any]]) -> dict[str, str]:
    """What each page, and everything the pages share (the stylesheet, the components, the data), say now, to know after the fix
    which pages changed."""
    pages = {str(r["file"]) for r in rows}
    state = {}
    shared = hashlib.sha256()
    source = root / "app" / "src"
    for path in sorted(source.rglob("*")) if source.is_dir() else []:
        if not path.is_file() or path.suffix.lower() not in {".tsx", ".ts", ".jsx", ".js", ".css", ".json"}:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = "app/src/" + path.relative_to(source).as_posix()
        if relative in pages:
            state[relative] = digest
        else:
            shared.update(relative.encode() + digest.encode())
    for name in pages:
        state.setdefault(name, "")
    state[SHARED] = shared.hexdigest()
    return state


def _fix_request(findings: list[dict[str, Any]], accounts: list[dict[str, Any]]) -> tuple[str, int]:
    """The problems worth fixing, written out page by page for the agent."""
    return screen_review.fix_request(findings)


def run(project: str, session: Any, rows: list[dict[str, Any]], accounts: list[dict[str, Any]],
        fix: bool = True, model: str = "", force: bool = False, rebuild: Any = None) -> dict[str, Any]:
    """Review the prototype's pages with a vision model and fix what it finds (`fix`: false only looks and reports).
    `model` is the one this run chose, else the project's; `force` runs it even when the setting turns it off, because it
    was asked for; `rebuild` bundles the app again after the fix, so that the pages are photographed as they are now.
    Always returns a result, never raises."""
    if not enabled() and not force:
        return {"status": "off"}
    try:
        model = str(session.agent(model).model)
        ok, why = can_review(model, cancelled=lambda: bool(session.cancelled))
        if not ok:
            bus.agent_msg(project, f"The screens were not checked by looking at them: {why}.",
                          title="Visual review skipped", kind="narration", agent=bus.DESIGNER)
            return {"status": "skipped", "reason": why}
        return _review(project, session, model, rows, accounts, fix, rebuild)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - a review is never a reason to fail the prototype
        bus.phase(project, PHASE, "Checking the screens with a vision model", status="failed", detail=str(exc)[:300],
                  agent=bus.DESIGNER)
        bus.log(project, "WARN", f"The visual review stopped: {str(exc)[:300]}", agent=bus.DESIGNER)
        return {"status": "failed", "reason": str(exc)[:300]}


def _review(project: str, session: Any, model: str, rows: list[dict[str, Any]], accounts: list[dict[str, Any]],
            fix: bool = True, rebuild: Any = None) -> dict[str, Any]:
    root = session.record / "prototype"
    emails = {str(r["file"]): screens.role_for(r, accounts) for r in rows}
    bus.phase(project, PHASE, "Checking the screens with a vision model",
              detail=f"{model} looks at every screen at desktop and mobile width.", agent=bus.DESIGNER)
    bus.agent_msg(project, f"Taking a silent screenshot of each of the {len(rows)} screens, at desktop and mobile width, "
                           f"for {model} to look at.", title="Visual review", kind="narration", agent=bus.DESIGNER)

    def photograph(pages: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
        return screens.capture_all(root, pages, accounts, on_done=lambda done, total: bus.progress(
            project, label, done * 100 / total, agent=bus.DESIGNER),
            cancelled=lambda: bool(session.cancelled))

    def look(pages: list[dict[str, Any]], shots: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
        counted = [0]

        def one(row: dict[str, Any]) -> dict[str, Any] | None:
            if session.cancelled:
                raise RunCancelled(project)
            result = _review_page(project, model, root, row, shots, emails.get(str(row["file"]), ""))
            counted[0] += 1
            bus.progress(project, label, counted[0] * 100 / len(pages), agent=bus.DESIGNER)
            if result:
                _tell(project, result)
            return result

        found = llm.in_lanes(pages, one, on_error=lambda row, exc: {
            "route": row["route"], "file": row["file"], "name": row.get("name") or row["route"], "looks_ok": False,
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
    request, count = _fix_request(first, accounts)
    if count and fix:
        if session.cancelled:
            raise RunCancelled(project)
        bus.agent_msg(project, f"{count} problem{'s' if count != 1 else ''} worth fixing found on "
                               f"{len({f['file'] for f in first if any(d['severity'] in FIX_SEVERITIES for d in f['defects'])})} "
                               "screen(s). Fixing them in the prototype's files.", title="Visual review",
                      kind="narration", agent=bus.DESIGNER)
        before = _fingerprint(root, rows)
        fix_stopped = screen_review.run_fix(project, session, prompts.load("prototype/visual-fix", defects=request), model,
                                            bus.DESIGNER, "Visual review")
        after = _fingerprint(root, rows)
        shared = before.get(SHARED) != after.get(SHARED)
        # A changed shared file (the stylesheet, a component) can change every page; otherwise only the pages whose own file changed.
        again = [r for r in rows if shared or before.get(str(r["file"])) != after.get(str(r["file"]))]
        fixed_pages = [str(r["file"]) for r in again]
        if again and rebuild:
            rebuild()
        if again:
            bus.agent_msg(project, f"Looking again at the {len(again)} screen{'s' if len(again) != 1 else ''} that changed.",
                          title="Visual review", kind="narration", agent=bus.DESIGNER)
            second = look(again, photograph(again, "Taking screenshots again"), "Looking at the changed screens")
    bus.progress(project, "Looking at the screens", 100, agent=bus.DESIGNER)

    final = {f["file"]: f for f in first}
    final.update({f["file"]: f for f in second if not f.get("error")})
    remaining = [(f, d) for f in final.values() for d in f["defects"] if d["severity"] in FIX_SEVERITIES]
    report = {"model": model, "pages": len(rows), "problems_found": problems, "fixed_pages": fixed_pages,
              "fix_stopped": fix_stopped,
              "remaining": [{"file": f["file"], **d} for f, d in remaining],
              "pages_not_reviewed": unreviewed, "screens_without_picture": [s["file"] + " " + s["viewport"] for s in failed]}
    try:
        (root / screens.REVIEW_DIR).mkdir(parents=True, exist_ok=True)
        (root / screens.REVIEW_DIR / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    summary = (f"Looked at {len(rows)} screen{'s' if len(rows) != 1 else ''} with {model}: "
               + ("no problems found." if not problems else
                  f"{problems} problem{'s' if problems != 1 else ''} found; nothing was changed, this was a review only." if not fix else
                  f"{problems} problem{'s' if problems != 1 else ''} found"
                  + (f", {len(fixed_pages)} screen{'s' if len(fixed_pages) != 1 else ''} changed to fix them" if fixed_pages else "")
                  + (f"; {len(remaining)} still visible after the fix." if remaining else "; none left that matters.")))
    if fix_stopped:
        summary += f" The fix stopped before it was finished ({fix_stopped})."
    if unreviewed:
        summary += f" Could not be reviewed: {', '.join(unreviewed)}."
    bus.agent_msg(project, summary, title="Visual review", kind="narration", agent=bus.DESIGNER)
    bus.phase(project, PHASE, "Checking the screens with a vision model", status="complete", agent=bus.DESIGNER)
    return {"status": "done", **report}
