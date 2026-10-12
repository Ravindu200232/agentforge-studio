"""The specification's diagrams, looked at: a model that can see pictures checks how each one is drawn, and what it finds is fixed.

Mermaid draws every diagram to an SVG. That the source parsed does not say the picture is readable: labels run out of their
shapes, a line goes through a box, a diagram is drawn so wide that its text is tiny. So each SVG is photographed in a browser
that is already on the computer (silent: no window opens, nothing the person is signed in to is touched) and the picture goes to
a vision model, which says what is visibly wrong with it.

At most two rounds, never more:

1. round 1 looks at every diagram; the ones with a problem that matters are drawn again from a corrected source, and the
   corrected diagram has to render;
2. round 2 looks once more at only the diagrams that were drawn again. Whatever is still wrong is reported as it is, and a
   diagram that came out worse than it was is put back as it was.

A model that cannot look at pictures (`server_modules/vision.py`), or a computer with no browser, skips all of this with one
line saying why. Neither is an error, and nothing here ever fails the specification: it is a review, not a gate.
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from ollama_terminal import screenshot
from server_modules import bus, config, llm, mermaid, prompts, screen_review
from server_modules.session import RunCancelled

SRS_DIR = "srs"
REVIEW_DIR = "review"
REPORT = "report.json"
PHASE = "srs:diagram-look"
MAX_ROUNDS = 2
SOURCE_LIMIT = 6000                       # of a diagram's source, shown to the reviewer
SYSTEM = ("You are a meticulous reviewer of technical diagrams. You are shown a screenshot of one diagram and you report only "
          "what is visibly wrong with how it is drawn, as the JSON object you are asked for. You never invent a problem you "
          "cannot see.")
FIX_SYSTEM = "You correct Mermaid diagram sources. You reply with the corrected source and nothing else."
_FIX = screen_review.FIX_SEVERITIES
_PAGE = (
    "<!doctype html><html><head><meta charset=\"utf-8\"><title>@@TITLE@@</title><style>"
    "html,body{margin:0;background:#fff}body{padding:24px;font-family:Arial,sans-serif}"
    "h1{font-size:16px;margin:0 0 12px;color:#111827}svg{max-width:100%;height:auto}</style></head><body>"
    "<h1>@@TITLE@@</h1>@@SVG@@" + screenshot.MEASURE + "</body></html>")


def enabled() -> bool:
    return bool(config.setting("diagram_visual_review", True))


def can_review(model: str, cancelled: Any = None) -> tuple[bool, str]:
    """Whether `model` can be shown screenshots and there is a browser to take them: (ok, why not)."""
    try:
        return screen_review.can_review(model, need_browser=True, cancelled=cancelled)
    except InterruptedError as exc:
        raise RunCancelled("diagram") from exc


def _worth_fixing(result: dict[str, Any]) -> list[dict[str, Any]]:
    return [d for d in result["defects"] if d["severity"] in _FIX]


def _svg_of(entry: dict[str, Any]) -> str:
    return str(entry.get("svg") or "")


def _photograph(session: Any, entry: dict[str, Any], number: int) -> tuple[Path, str]:
    """The picture of one diagram for this round: (the file, its workspace-relative path)."""
    kind = str(entry["kind"])
    page = session.record_path(SRS_DIR, "diagrams", REVIEW_DIR, f"{kind}-round{number}.html")
    picture = page.with_suffix(".png")
    title = str(entry.get("title") or kind.replace("_", " ").title())
    page.write_text(_PAGE.replace("@@TITLE@@", html.escape(title)).replace("@@SVG@@", _svg_of(entry)), encoding="utf-8")
    screenshot.shoot(page, picture, "desktop", cancelled=lambda: bool(session.cancelled))
    page.unlink(missing_ok=True)
    return picture, picture.relative_to(session.workspace).as_posix()


def _look(project: str, session: Any, model: str, entry: dict[str, Any], number: int) -> dict[str, Any]:
    """One diagram, photographed and looked at: the review the model gave, with its picture."""
    kind = str(entry["kind"])
    title = str(entry.get("title") or kind.replace("_", " ").title())
    picture, relative = _photograph(session, entry, number)
    request = prompts.load("srs/diagram-look", title=title, kind=kind.replace("_", " "),
                           source=str(entry.get("source") or "")[:SOURCE_LIMIT])
    answer = llm.complete_json(SYSTEM, request, screen_review.clean, label="diagram look", model=model,
                               images=[picture.read_bytes()], project=project, role=bus.DEVELOPER)
    return {"kind": kind, "name": title, **answer, "picture": picture,
            "thumbs": [{"path": relative, "label": f"{title} · round {number}"}]}


def _problems_text(defects: list[dict[str, Any]]) -> str:
    return "\n".join(f"{n}. [{d['severity']}] {d['where'] or 'the diagram'}: {d['problem']}"
                     + (f" Suggested: {d['fix']}" if d["fix"] else "") for n, d in enumerate(defects, start=1))


def _redraw(project: str, session: Any, model: str, entry: dict[str, Any], review: dict[str, Any]) -> dict[str, Any] | None:
    """The diagram drawn again from a corrected source. Returns what the entry was before (to put it back), or None when the
    corrected source did not make a diagram that Mermaid draws: the diagram then stays as it was."""
    kind = str(entry["kind"])
    old_source = str(entry.get("source") or "")
    request = prompts.load("srs/diagram-look-fix", kind=kind.replace("_", " "), source=old_source[:SOURCE_LIMIT],
                           defects=_problems_text(_worth_fixing(review)), declaration=mermaid.declaration_for(kind))
    source = mermaid.clean(llm.complete(system=FIX_SYSTEM, user=request, model=model, project=project, think=False,
                                        images=[review["picture"].read_bytes()], thinking_fallback=False, role=bus.DEVELOPER))
    if not source or source == mermaid.clean(old_source) or not mermaid.has_diagram(kind, source):
        return None
    trial = session.record_path(SRS_DIR, "diagrams", REVIEW_DIR, f"{kind}-redrawn.svg")
    rendered, _why = mermaid.render_diagram(kind, source, trial)
    if not rendered:
        trial.unlink(missing_ok=True)
        return None
    before = {key: entry.get(key) for key in ("source", "svg")}
    _store(project, session, entry, source, trial.read_text(encoding="utf-8", errors="replace"), "redrawn")
    trial.unlink(missing_ok=True)
    return before


def _store(project: str, session: Any, entry: dict[str, Any], source: str, svg: str, note: str) -> None:
    """Make `source` and its picture the diagram: in the entry and in the files beside the specification."""
    kind = str(entry["kind"])
    mmd = session.record_path(SRS_DIR, "diagrams", f"{kind}.mmd")
    drawing = session.record_path(SRS_DIR, "diagrams", f"{kind}.svg")
    mmd.write_text(source, encoding="utf-8")
    drawing.write_text(svg, encoding="utf-8")
    entry["source"], entry["svg"] = source, svg
    bus.file_written(project, mmd.relative_to(session.workspace).as_posix(), source, note=note)


def _save_report(session: Any, report: dict[str, Any]) -> None:
    try:
        folder = session.record_path(SRS_DIR, "diagrams", REVIEW_DIR)
        (folder / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except (OSError, RunCancelled):
        pass


def run(project: str, session: Any, diagrams: list[dict[str, Any]], fix: bool = True, model: str = "",
        force: bool = False) -> dict[str, Any]:
    """Look at the drawn diagrams and fix what is wrong with how they are drawn (`fix`: false only looks and reports).

    `diagrams` are the specification's diagram entries; a corrected one is changed in place, so the caller saves the document
    afterwards. `force` runs it even when the setting turns it off, because it was asked for. Always returns a result, never
    raises (except for Stop)."""
    if not enabled() and not force:
        return {"status": "off"}
    rows = [d for d in diagrams if isinstance(d, dict) and d.get("kind") and _svg_of(d) and d.get("source")
            and d.get("applicable") is not False]
    if not rows:
        return {"status": "nothing"}
    try:
        model = str(session.agent(model).model)
        ok, why = can_review(model, cancelled=lambda: bool(session.cancelled))
        if not ok:
            bus.agent_msg(project, f"The diagrams were not checked by looking at them: {why}.",
                          title="Diagram check skipped", kind="narration")
            return {"status": "skipped", "reason": why}
        return _review(project, session, model, rows, fix)
    except RunCancelled:
        raise
    except Exception as exc:  # noqa: BLE001 - a review is never a reason to fail the specification
        bus.phase(project, PHASE, "Checking the diagrams with a vision model", status="failed", detail=str(exc)[:300])
        bus.log(project, "WARN", f"The diagram check stopped: {str(exc)[:300]}")
        return {"status": "failed", "reason": str(exc)[:300]}


def _review(project: str, session: Any, model: str, rows: list[dict[str, Any]], fix: bool) -> dict[str, Any]:
    plural = screen_review.plural
    bus.phase(project, PHASE, "Checking the diagrams with a vision model",
              detail=f"{model} looks at a picture of each diagram, at most {MAX_ROUNDS} rounds.")

    def look_at(pending: list[dict[str, Any]], number: int) -> dict[str, dict[str, Any]]:
        bus.agent_msg(project, f"Round {number} of {MAX_ROUNDS}: taking a silent screenshot of {plural(len(pending), 'diagram')} "
                               f"for {model} to look at.", title="Diagram check", kind="narration")
        done = [0]

        def one(entry: dict[str, Any]) -> dict[str, Any]:
            if session.cancelled:
                raise RunCancelled(project)
            result = _look(project, session, model, entry, number)
            done[0] += 1
            bus.progress(project, "Looking at the diagrams", done[0] * 100 / len(pending))
            screen_review.tell(project, result, bus.DEVELOPER, kind="diagram_review")
            return result

        found = llm.in_lanes(pending, one, on_error=lambda entry, exc: {
            "kind": entry["kind"], "name": str(entry.get("title") or entry["kind"]), "looks_ok": False, "summary": "",
            "defects": [], "error": str(exc)[:200], "thumbs": [], "picture": None})
        if session.cancelled:
            raise RunCancelled(project)
        return {str(r["kind"]): r for r in found if r}

    first = look_at(rows, 1)
    by_kind = {str(d["kind"]): d for d in rows}
    problems = sum(len(r["defects"]) for r in first.values())
    unreviewed = [r["name"] for r in first.values() if r.get("error")]

    redrawn: list[str] = []
    kept_as_was: list[str] = []
    before: dict[str, dict[str, Any]] = {}
    second: dict[str, dict[str, Any]] = {}
    broken = [r for r in first.values() if _worth_fixing(r) and r.get("picture")]
    if broken and fix and MAX_ROUNDS > 1:
        bus.agent_msg(project, f"{plural(sum(len(_worth_fixing(r)) for r in broken), 'problem')} worth fixing found in "
                               f"{plural(len(broken), 'diagram')}. Drawing them again from a corrected source.",
                      title="Diagram check", kind="narration")

        def mend(review: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
            if session.cancelled:
                raise RunCancelled(project)
            return str(review["kind"]), _redraw(project, session, model, by_kind[str(review["kind"])], review)

        for kind, was in llm.in_lanes(broken, mend, on_error=lambda review, exc: (str(review["kind"]), None)):
            if was is not None:
                before[kind] = was
                redrawn.append(kind)
        if redrawn:
            second = look_at([by_kind[k] for k in redrawn], 2)
        else:
            bus.agent_msg(project, "None of the corrected sources made a diagram that could be drawn, so the diagrams stay "
                                   "as they were.", title="Diagram check", kind="narration")

    # A diagram that came out with more problems than it had is put back as it was.
    for kind in redrawn:
        after = second.get(kind)
        if after is None or after.get("error"):
            continue
        if len(_worth_fixing(after)) > len(_worth_fixing(first[kind])):
            _store(project, session, by_kind[kind], str(before[kind]["source"]), str(before[kind]["svg"]), "put back")
            kept_as_was.append(kind)
    final = {**first, **{k: v for k, v in second.items() if not v.get("error") and k not in kept_as_was}}
    remaining = [{"kind": k, **d} for k, r in final.items() for d in _worth_fixing(r)]
    report = {"model": model, "diagrams": len(rows), "rounds": 2 if second else 1, "problems_found": problems,
              "redrawn": redrawn, "put_back": kept_as_was, "remaining": remaining, "not_reviewed": unreviewed}
    _save_report(session, report)
    bus.progress(project, "Looking at the diagrams", 100)

    text = f"Looked at {plural(len(rows), 'diagram')} with {model}: "
    if not problems:
        text += "no problems found."
    elif not fix:
        text += f"{plural(problems, 'problem')} found; nothing was changed, this was a review only."
    else:
        text += f"{plural(problems, 'problem')} found"
        text += f", {plural(len(redrawn), 'diagram')} drawn again" if redrawn else ""
        text += f" ({plural(len(kept_as_was), 'diagram')} put back as it was, the new drawing was worse)" if kept_as_was else ""
        text += (f"; {plural(len(remaining), 'problem')} still visible after round {2 if second else 1}."
                 if remaining else "; none left that matters.")
    if unreviewed:
        text += f" Could not be reviewed: {', '.join(unreviewed)}."
    bus.agent_msg(project, text, title="Diagram check", kind="narration")
    bus.phase(project, PHASE, "Checking the diagrams with a vision model", status="complete")
    return {"status": "done", **report}
