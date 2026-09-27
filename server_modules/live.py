"""The live browser: what a running test is looking at, shown in the studio's preview.

A generated app's Playwright run streams into here (its fixture posts frames, its reporter
posts what the test is doing). Nothing is stored: the studio shows the newest frame, and the
frames of a run that has ended are of no use to anyone.
"""
from __future__ import annotations

import threading
from typing import Any

from . import bus

# A frame is a JPEG as a data URL. Larger than this is not a screencast frame.
MAX_FRAME_CHARS = 700_000

_lock = threading.Lock()
_active: set[str] = set()


def url_for(project: str) -> str:
    """Where a command run for `project` posts its live view (see `AGENTFORGE_LIVE_URL`)."""
    from . import config

    return f"http://127.0.0.1:{config.API_PORT}{config.API_PREFIX}/live/{project}"


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _cursor(data: Any) -> dict[str, Any] | None:
    """Where the test's pointer is and what it is doing, as the preview draws it."""
    if not isinstance(data, dict):
        return None
    x, y = _number(data.get("x")), _number(data.get("y"))
    if x is None or y is None:
        return None
    action = str(data.get("action") or "move")
    out: dict[str, Any] = {"x": x, "y": y, "action": action if action in {"move", "click", "type", "key"} else "move"}
    box = data.get("box")
    if isinstance(box, dict) and all(_number(box.get(k)) is not None for k in ("x", "y", "width", "height")):
        out["box"] = {k: float(box[k]) for k in ("x", "y", "width", "height")}
    return out


def _colour(value: Any) -> str:
    """A CSS colour the page reported for its own background: nothing else is passed on."""
    text = str(value or "").strip()
    return text if len(text) <= 40 and all(c.isalnum() or c in "#(),. %" for c in text) else ""


def frame(project: str, data: dict[str, Any]) -> None:
    picture = str(data.get("frame") or "")
    if not picture.startswith("data:image/") or len(picture) > MAX_FRAME_CHARS:
        return
    with _lock:
        _active.add(project)
    viewport = data.get("viewport") if isinstance(data.get("viewport"), dict) else {}
    bus.transient({"type": "browser_frame", "project": project, "frame": picture, "kind": "test",
                   "url": str(data.get("url") or ""), "title": str(data.get("title") or ""),
                   "bg": _colour(data.get("bg")),
                   "viewport": {"width": viewport.get("width"), "height": viewport.get("height")}})


def cursor(project: str, data: dict[str, Any]) -> None:
    """The pointer moved, clicked or typed: tiny, and sent on its own so it never waits for a picture."""
    point = _cursor(data.get("cursor"))
    if point is None:
        return
    with _lock:
        _active.add(project)
    bus.transient({"type": "browser_cursor", "project": project, "cursor": point, "bg": _colour(data.get("bg"))})


def event(project: str, data: dict[str, Any]) -> None:
    """One thing the test is doing: a journey starting, a step, a journey ending."""
    keep = {key: data[key] for key in ("state", "title", "label", "message", "role", "route", "verb", "value",
                                       "status", "ok", "index", "total", "lane", "suite", "project_name")
            if key in data}
    with _lock:
        _active.add(project)
    bus.transient({"type": "e2e_event", "project": project, **keep})


def finish(project: str) -> None:
    """The run is over: give the preview back. Safe to call when nothing was live."""
    with _lock:
        if project not in _active:
            return
        _active.discard(project)
    bus.transient({"type": "browser_frame", "project": project, "frame": None})
    bus.transient({"type": "e2e_done", "project": project})


def handle(project: str, body: dict[str, Any]) -> dict[str, Any]:
    kind = str(body.get("kind") or "")
    if kind == "frame":
        frame(project, body)
    elif kind == "cursor":
        cursor(project, body)
    elif kind == "event":
        event(project, body)
    elif kind == "end":
        finish(project)
    # Whether anyone is looking. A run that finds nobody does not spend time streaming.
    return {"ok": True, "watching": bus.viewers() > 0}
