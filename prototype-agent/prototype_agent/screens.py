"""Silent screenshots of the prototype's pages, for a model that can look at them.

The prototype is one bundled HTML page (`app/bundle.html`) that shows the screen named in its address hash, so any screen can be
photographed by opening that page at `#/route`, in a browser that is already on the computer (`ollama_terminal.screenshot`). A screen
that needs a signed-in role is shown signed in as one that can open it: the page opens signed in as the account in `?as=`.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from ollama_terminal import screenshot
from server_modules.session import RunCancelled

from . import demo

VIEWPORTS = tuple(screenshot.VIEWPORTS)
LANES = 3
REVIEW_DIR = "review"


def address(route: str) -> str:
    """The address a route is opened at: a screen that takes a value (`/orders/[id]`, `/orders/:id`) is opened on a sample one."""
    parts = [("1" if re.fullmatch(r"\[.+\]|:.+", part) else part) for part in str(route or "/").split("/") if part]
    return "/" + "/".join(parts)


def bundle_page(root: Path, work: Path) -> Path:
    """A copy of the bundled prototype in `work` that writes its own height into its title once it has drawn, for a whole-page picture."""
    bundle = root / "app" / "bundle.html"
    if not bundle.is_file():
        raise ValueError("the prototype is not bundled yet, so there is nothing to photograph")
    html = bundle.read_text(encoding="utf-8", errors="replace")
    end = html.lower().rfind("</body>")
    page = work / "prototype.html"
    page.write_text(html[:end] + screenshot.MEASURE + html[end:] if end >= 0 else html + screenshot.MEASURE, encoding="utf-8")
    return page


def suffix_for(route: str, email: str = "") -> str:
    return (f"?as={quote(email)}" if email else "") + "#" + address(route)


def _can_open(account: dict[str, Any]) -> set[str]:
    rows = account.get("can_open") if account.get("can_open") is not None else account.get("canOpen")
    return {str(row.get("route") if isinstance(row, dict) else row) for row in rows or []}


def role_for(row: dict[str, Any], accounts: list[dict[str, Any]]) -> str:
    """The demo account (by email) a page is shown as: none for a page anyone can open signed out, else the first account
    that can open it."""
    signed_in = row.get("signed_in")
    if signed_in is None:
        signed_in = demo.signed_in_page({"allowed_roles": row.get("roles") or []})
    if not signed_in or not accounts:
        return ""
    route = str(row.get("route") or "")
    chosen = next((a for a in accounts if route in _can_open(a)), accounts[0])
    return str(chosen.get("email") or "")


def find_page(root: Path, target: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The prototype page `target` names: its route (`/dashboard`), its page file (`dashboard`, `src/pages/dashboard.tsx`) or its name."""
    wanted = str(target or "").strip().strip("`'\"")
    wanted = wanted.split("?", 1)[0].split("#", 1)[0]
    lowered = wanted.lower().lstrip("/")
    for row in rows:
        stem = Path(str(row.get("file", ""))).stem.lower()
        if wanted in (str(row.get("file")), str(row.get("route"))) or lowered in (
                stem, str(row.get("route", "")).lower().lstrip("/"), str(row.get("name", "")).lower()):
            return row
    if wanted in ("", "/"):
        return next((r for r in rows if r.get("route") == "/"), rows[0] if rows else None)
    return None


def shoot_page(root: Path, row: dict[str, Any], accounts: list[dict[str, Any]], out: Path, viewport: str,
               email: str | None = None, cancelled: Callable[[], bool] | None = None) -> Path:
    """One picture of one prototype page, signed in as `email` (default: the account that can open it)."""
    chosen = role_for(row, accounts) if email is None else email
    work = Path(tempfile.mkdtemp(prefix="agentforge-prototype-"))
    try:
        page = bundle_page(root, work)
        return screenshot.shoot(page, out, viewport, cancelled=cancelled, suffix=suffix_for(str(row.get("route") or "/"), chosen))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def capture_all(root: Path, rows: list[dict[str, Any]], accounts: list[dict[str, Any]],
                viewports: tuple[str, ...] = VIEWPORTS, on_done=None,
                cancelled: Callable[[], bool] | None = None) -> list[dict[str, Any]]:
    """Pictures of every page in `rows` (the prototype's routes) at each of `viewports`, under `root/review/`.

    Each answer is {"route", "file", "viewport", "path" (relative to root, "" when it failed), "error"}; one page that will
    not draw costs that page, never the rest."""
    try:
        browser = screenshot.working_browser(cancelled=cancelled)
    except InterruptedError as exc:
        raise RunCancelled("prototype") from exc
    if not browser:
        raise ValueError("no browser to take the screenshots with (Edge, Chrome or Chromium)")
    work = Path(tempfile.mkdtemp(prefix="agentforge-prototype-"))
    try:
        page = bundle_page(root, work)
        jobs = [(row, viewport) for row in rows for viewport in viewports]
        lock = threading.Lock()
        finished = [0]

        def take(job: tuple[dict[str, Any], str]) -> dict[str, Any]:
            if cancelled and cancelled():
                raise RunCancelled("prototype")
            row, viewport = job
            out = root / REVIEW_DIR / f"{Path(str(row['file'])).stem}-{viewport}.png"
            answer = {"route": row.get("route"), "file": row["file"], "viewport": viewport, "path": "", "error": ""}
            try:
                suffix = suffix_for(str(row.get("route") or "/"), role_for(row, accounts))
                if cancelled:
                    screenshot.shoot(page, out, viewport, browser, cancelled=cancelled, suffix=suffix)
                else:
                    screenshot.shoot(page, out, viewport, browser, suffix=suffix)
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
