"""Silent screenshots of the prototype's pages, for a model that can look at them.

The prototype is one bundled HTML page (`app/bundle.html`) that shows the screen named in its address hash, so any screen can be
photographed by opening that page at `#/route`, in a browser that is already on the computer (`ollama_terminal.screenshot`). A screen
that needs a signed-in role is shown signed in as one that can open it: the page opens signed in as the account in `?as=`.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote

from ollama_terminal import screenshot

from . import demo


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
    bundle = root / "app" / "bundle.html"
    if not bundle.is_file():
        raise ValueError("the prototype is not bundled yet, so there is nothing to photograph")
    chosen = role_for(row, accounts) if email is None else email
    work = Path(tempfile.mkdtemp(prefix="agentforge-prototype-"))
    try:
        html = bundle.read_text(encoding="utf-8", errors="replace")
        end = html.lower().rfind("</body>")
        page = work / "prototype.html"
        page.write_text(html[:end] + screenshot.MEASURE + html[end:] if end >= 0 else html + screenshot.MEASURE, encoding="utf-8")
        suffix = (f"?as={quote(chosen)}" if chosen else "") + "#" + str(row.get("route") or "/")
        return screenshot.shoot(page, out, viewport, cancelled=cancelled, suffix=suffix)
    finally:
        shutil.rmtree(work, ignore_errors=True)
