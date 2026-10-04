"""Silent screenshots of every prototype page, for a model that can look at them.

The prototype is static HTML, so `ollama_terminal.screenshot` (a browser that is already on the computer, headless, its own
empty profile) can photograph it from disk. A page that needs a signed-in role is shown signed in as one that can open it: the
demo session is a key in the browser's local storage (`assets/flow.js`), so each role gets its own copy of the prototype with
that key set in the head of every page, which leaves the pages themselves, and the file names they work out their route
from, as they are.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ollama_terminal import screenshot

from . import prototype_brief

VIEWPORTS = tuple(screenshot.VIEWPORTS)
LANES = 3
SESSION_KEY = "agentforge.prototype.user"
REVIEW_DIR = "review"


def _seed(email: str) -> str:
    """Put the demo session in place before anything on the page runs."""
    value = email.replace("\\", "").replace("'", "")
    return (f"<script>(function(){{var K='{SESSION_KEY}';try{{localStorage.setItem(K,'{value}')}}catch(e){{}}"
            f"window.name=K+'={value}'}})()</script>")


def with_scripts(html: str, seed: str = "") -> str:
    """`html` with the demo session seeded first in its head and the height measure last in its body."""
    if seed:
        head = re.search(r"<head[^>]*>", html, re.I)
        html = html[:head.end()] + seed + html[head.end():] if head else seed + html
    end = html.lower().rfind("</body>")
    return html[:end] + screenshot.MEASURE + html[end:] if end >= 0 else html + screenshot.MEASURE


def copy_for(source: Path, target: Path, email: str) -> None:
    """A copy of the prototype in `target` whose pages open signed in as `email` ("" = signed out)."""
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(REVIEW_DIR, "input", "plan.md", "generation.json"))
    seed = _seed(email) if email else ""
    for page in target.glob("*.html"):
        page.write_text(with_scripts(page.read_text(encoding="utf-8", errors="replace"), seed), encoding="utf-8")


def _can_open(account: dict[str, Any]) -> set[str]:
    rows = account.get("can_open") if account.get("can_open") is not None else account.get("canOpen")
    return {str(row.get("route") if isinstance(row, dict) else row) for row in rows or []}


def role_for(row: dict[str, Any], accounts: list[dict[str, Any]]) -> str:
    """The demo account (by email) a page is shown as: none for a page anyone can open signed out, else the first account
    that can open it."""
    signed_in = row.get("signed_in")
    if signed_in is None:
        # A prototype drawn before pages were flagged: only signing-in roles opening a page make it a signed-in one.
        signed_in = prototype_brief.signed_in_page({"allowed_roles": row.get("roles") or []})
    if not signed_in or not accounts:
        return ""
    route = str(row.get("route") or "")
    chosen = next((a for a in accounts if route in _can_open(a)), accounts[0])
    return str(chosen.get("email") or "")


def find_page(root: Path, target: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The prototype page `target` names: its file (`dashboard.html`), its route (`/dashboard`), or its name."""
    wanted = str(target or "").strip().strip("`'\"")
    wanted = wanted.split("?", 1)[0].split("#", 1)[0]
    lowered = wanted.lower().lstrip("/")
    for row in rows:
        if wanted in (str(row.get("file")), str(row.get("route"))) or lowered in (
                str(row.get("file", "")).lower(), str(row.get("route", "")).lower().lstrip("/"), str(row.get("name", "")).lower()):
            return row
    if wanted in ("", "/"):
        return next((r for r in rows if r.get("route") == "/"), rows[0] if rows else None)
    return None


def shoot_page(root: Path, row: dict[str, Any], accounts: list[dict[str, Any]], out: Path, viewport: str,
               email: str | None = None) -> Path:
    """One picture of one prototype page, signed in as `email` (default: the account that can open it)."""
    chosen = role_for(row, accounts) if email is None else email
    work = Path(tempfile.mkdtemp(prefix="agentforge-prototype-"))
    try:
        copy_for(root, work / "copy", chosen)
        return screenshot.shoot(work / "copy" / str(row["file"]), out, viewport)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def capture_all(root: Path, rows: list[dict[str, Any]], accounts: list[dict[str, Any]],
                viewports: tuple[str, ...] = VIEWPORTS, on_done=None) -> list[dict[str, Any]]:
    """Pictures of every page in `rows` (the prototype's routes) at each of `viewports`, under `root/review/`.

    Each answer is {"route", "file", "viewport", "path" (relative to root, "" when it failed), "error"}; one page that will
    not draw costs that page, never the rest."""
    browser = screenshot.working_browser()
    if not browser:
        raise ValueError("no browser to take the screenshots with (Edge, Chrome or Chromium)")
    work = Path(tempfile.mkdtemp(prefix="agentforge-prototype-"))
    try:
        copies: dict[str, Path] = {}
        for email in {role_for(row, accounts) for row in rows}:
            copies[email] = work / (re.sub(r"[^a-z0-9]+", "-", email.lower()).strip("-") or "signed-out")
            copy_for(root, copies[email], email)
        jobs = [(row, viewport) for row in rows for viewport in viewports]
        lock = threading.Lock()
        finished = [0]

        def take(job: tuple[dict[str, Any], str]) -> dict[str, Any]:
            row, viewport = job
            page = copies[role_for(row, accounts)] / str(row["file"])
            out = root / REVIEW_DIR / f"{Path(str(row['file'])).stem}-{viewport}.png"
            answer = {"route": row.get("route"), "file": row["file"], "viewport": viewport, "path": "", "error": ""}
            try:
                screenshot.shoot(page, out, viewport, browser)
                answer["path"] = out.relative_to(root).as_posix()
            except (ValueError, OSError) as exc:
                answer["error"] = str(exc)[:300]
            if on_done:
                with lock:
                    finished[0] += 1
                    on_done(finished[0], len(jobs))
            return answer

        with ThreadPoolExecutor(max_workers=LANES) as pool:
            return list(pool.map(take, jobs))
    finally:
        shutil.rmtree(work, ignore_errors=True)
