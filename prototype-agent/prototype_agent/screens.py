"""Silent screenshots of every prototype page, for a model that can look at them.

The prototype is one React app built into a single `bundle.html`, and each page is a hash route of it (`bundle.html#/orders`),
so `ollama_terminal.screenshot` (a browser that is already on the computer, headless, its own empty profile) photographs a page
straight from disk. What it photographs is a copy of the bundle with the height measure in its body, so every picture is as tall
as its page; the bundle itself is never changed.
"""
from __future__ import annotations

import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from ollama_terminal import screenshot
from server_modules import web_app
from server_modules.session import RunCancelled

VIEWPORTS = tuple(screenshot.VIEWPORTS)
LANES = 3
REVIEW_DIR = "review"


def bundle_of(root: Path) -> Path:
    """The built prototype, from the prototype folder (`.agentforge/prototype`)."""
    return root / "app" / web_app.BUNDLE


def measured_copy(bundle: Path, target: Path) -> Path:
    """`target`: a copy of the bundle whose body ends with the height measure."""
    html = bundle.read_text(encoding="utf-8", errors="replace")
    end = html.lower().rfind("</body>")
    target.write_text(html[:end] + screenshot.MEASURE + html[end:] if end >= 0 else html + screenshot.MEASURE, encoding="utf-8")
    return target


def find_page(rows: list[dict[str, Any]], target: str) -> dict[str, Any] | None:
    """The prototype page `target` names: its route (`/dashboard`, `#/dashboard`), its name, or its file-name form."""
    wanted = str(target or "").strip().strip("`'\"").lstrip("#").split("?", 1)[0]
    lowered = wanted.lower().lstrip("/")
    for row in rows:
        route = str(row.get("route") or "")
        if wanted == route or lowered in (route.lower().lstrip("/"), str(row.get("name", "")).lower(), web_app.route_slug(route)):
            return row
    if wanted in ("", "/"):
        return next((r for r in rows if r.get("route") == "/"), rows[0] if rows else None)
    return None


def shoot_page(root: Path, row: dict[str, Any], out: Path, viewport: str,
               cancelled: Callable[[], bool] | None = None) -> Path:
    """One picture of one prototype page."""
    bundle = bundle_of(root)
    if not bundle.is_file():
        raise ValueError("the prototype is not built yet")
    work = Path(tempfile.mkdtemp(prefix="agentforge-prototype-"))
    try:
        page = measured_copy(bundle, work / "app.html")
        return screenshot.shoot(page, out, viewport, cancelled=cancelled, fragment=web_app.hash_for(str(row["route"])))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def capture_all(root: Path, rows: list[dict[str, Any]], viewports: tuple[str, ...] = VIEWPORTS, on_done=None,
                cancelled: Callable[[], bool] | None = None) -> list[dict[str, Any]]:
    """Pictures of every page in `rows` (the prototype's routes) at each of `viewports`, under `root/review/`.

    Each answer is {"route", "viewport", "path" (relative to root, "" when it failed), "error"}; one page that will not draw
    costs that page, never the rest."""
    bundle = bundle_of(root)
    if not bundle.is_file():
        raise ValueError("the prototype is not built yet")
    try:
        browser = screenshot.working_browser(cancelled=cancelled)
    except InterruptedError as exc:
        raise RunCancelled("prototype") from exc
    if not browser:
        raise ValueError("no browser to take the screenshots with (Edge, Chrome or Chromium)")
    work = Path(tempfile.mkdtemp(prefix="agentforge-prototype-"))
    try:
        page = measured_copy(bundle, work / "app.html")
        jobs = [(row, viewport) for row in rows for viewport in viewports]
        lock = threading.Lock()
        finished = [0]

        def take(job: tuple[dict[str, Any], str]) -> dict[str, Any]:
            if cancelled and cancelled():
                raise RunCancelled("prototype")
            row, viewport = job
            route = str(row["route"])
            out = root / REVIEW_DIR / f"{web_app.route_slug(route)}-{viewport}.png"
            answer = {"route": route, "viewport": viewport, "path": "", "error": ""}
            try:
                screenshot.shoot(page, out, viewport, browser, fragment=web_app.hash_for(route),
                                 **({"cancelled": cancelled} if cancelled else {}))
                answer["path"] = out.relative_to(root).as_posix()
            except InterruptedError as exc:
                raise RunCancelled("prototype") from exc
            except (ValueError, OSError) as exc:
                answer["error"] = str(exc)[:300]
            if cancelled and cancelled():
                raise RunCancelled("prototype")
            if on_done:
                with lock:
                    finished[0] += 1
                    on_done(finished[0], len(jobs))
            return answer

        with ThreadPoolExecutor(max_workers=LANES) as pool:
            return list(pool.map(take, jobs))
    finally:
        shutil.rmtree(work, ignore_errors=True)
