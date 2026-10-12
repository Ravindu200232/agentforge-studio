"""Account sign-in and cloud-credit status for the built-in AgentForge engine.

The engine proxy authorizes and meters cloud model calls. Local Ollama and a
person's own direct Ollama API key do not spend AgentForge cloud credit.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx

from . import bus, config

SERVER_FILE = Path(__file__).with_name("accounts.json")
TOKEN = "account_token"
CACHE = "account"
FRESH_SECONDS = 15           # how long what the admin app said about the account is believed before asking again
TIMEOUT = httpx.Timeout(15.0, connect=8.0)

_on = False                  # set by the Studio's backend at start
_asked_at = 0.0


class NotAllowed(RuntimeError):
    """A built-in cloud model call the account may not make."""


def server_url() -> str:
    url = os.environ.get("AGENTFORGE_ACCOUNTS_URL", "").strip() or str(config.setting("accounts_url", "") or "").strip()
    if not url:
        try:
            import json

            url = str(json.loads(SERVER_FILE.read_text(encoding="utf-8")).get("url") or "").strip()
        except (OSError, ValueError):
            url = ""
    return url.rstrip("/")


def switch_on() -> None:
    """The Studio's backend is starting: with an address set, people sign in from now on and their requests are counted."""
    global _on
    _on = True


def enabled() -> bool:
    return _on and bool(server_url())


def _call(method: str, path: str, body: dict[str, Any] | None = None, token: str = "") -> tuple[int, dict[str, Any]]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        answer = httpx.request(method, server_url() + path, json=body, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise ConnectionError(f"the AgentForge account service could not be reached ({str(exc)[:120]})") from exc
    try:
        data = answer.json()
    except ValueError:
        data = {}
    return answer.status_code, data if isinstance(data, dict) else {}


def _remember(account: dict[str, Any]) -> dict[str, Any]:
    global _asked_at
    row = {key: account.get(key) for key in ("id", "email", "name", "username", "status", "plan",
                                           "limitUsd", "usedUsd", "remainingUsd", "weekResetsAt", "paidUntil",
                                           "weeklyPriceUsd", "checkoutAvailable")}
    row["unlimited"] = bool(account.get("unlimited"))         # the admin: never limited
    if isinstance(account.get("ollama"), dict):
        row["ollama"] = account["ollama"]                    # the admin is told the Ollama account's balance
    config.save_settings({CACHE: row})
    _asked_at = time.time()
    bus.transient({"type": "account_usage", **row})
    return row


def signup(username: str, email: str, password: str, name: str = "") -> dict[str, Any]:
    status, data = _call("POST", "/api/accounts/signup", {"username": username, "email": email, "password": password,
                                                          "name": name})
    if status >= 400:
        return {"ok": False, "error": str(data.get("error") or "The account could not be created.")}
    if not data.get("token"):
        return {"ok": False, "error": "The account was created, but sign-in could not be completed."}
    config.save_settings({TOKEN: str(data["token"])})
    row = _remember(data.get("account") or {})
    return {"ok": True, "user": user_of(row), "token": "account"}


def login(login_name: str, password: str) -> dict[str, Any]:
    status, data = _call("POST", "/api/accounts/login", {"login": login_name, "password": password})
    if status >= 400 or not data.get("token"):
        return {"ok": False, "error": str(data.get("error") or "The email or password is not right.")}
    config.save_settings({TOKEN: str(data["token"])})
    row = _remember(data.get("account") or {})
    return {"ok": True, "user": user_of(row), "token": "account"}


def logout() -> None:
    config.save_settings({TOKEN: "", CACHE: {}})
    bus.transient({"type": "account_usage", "status": "signed_out"})


def user_of(row: dict[str, Any]) -> dict[str, Any]:
    return {"id": row.get("id") or "", "username": row.get("username") or row.get("email") or "",
            "name": row.get("name") or row.get("username") or row.get("email") or "", "email": row.get("email") or "",
            "plan": "account", "account": status_of(row)}


def status_of(row: dict[str, Any]) -> dict[str, Any]:
    out = {"status": row.get("status") or "", "plan": row.get("plan") or "free",
           "limitUsd": float(row.get("limitUsd") or 0), "usedUsd": float(row.get("usedUsd") or 0),
           "remainingUsd": float(row.get("remainingUsd") or 0), "weekResetsAt": row.get("weekResetsAt"),
           "paidUntil": row.get("paidUntil"), "weeklyPriceUsd": float(row.get("weeklyPriceUsd") or 21),
           "checkoutAvailable": bool(row.get("checkoutAvailable")), "unlimited": bool(row.get("unlimited"))}
    if isinstance(row.get("ollama"), dict):
        out["ollama"] = row["ollama"]
    return out


def current(fresh: bool = False) -> dict[str, Any]:
    """What is known about the signed-in account ({} when nobody is signed in), asked of the admin app when it is older than a
    few seconds. When the service cannot be reached, the last answer stands."""
    token = str(config.setting(TOKEN, "") or "")
    if not token:
        return {}
    cached = config.setting(CACHE, {}) or {}
    if not fresh and cached and time.time() - _asked_at < FRESH_SECONDS:
        return cached
    try:
        status, data = _call("GET", "/api/accounts/me", token=token)
    except ConnectionError:
        return cached
    if status == 401:
        config.save_settings({TOKEN: "", CACHE: {}})
        return {}
    return _remember(data.get("account") or {}) if data.get("account") else cached


def status(fresh: bool = False) -> dict[str, Any]:
    """For the studio: whether accounts are on, who is signed in, and their requests."""
    if not enabled():
        return {"enabled": False}
    row = current(fresh)
    return {"enabled": True, "signed_in": bool(row), **({"email": row.get("email"), "name": row.get("name")} if row else {}),
            **(status_of(row) if row else {})}


def check() -> None:
    """Give a fast local error; the engine proxy makes the authoritative budget decision."""
    if not enabled() or config.engine() != "built-in":
        return
    row = current()
    if not row:
        raise NotAllowed("Sign in to AgentForge to use the AI.")
    if row.get("status") != "approved":
        raise NotAllowed("Your AgentForge account is inactive. Contact the admin.")
    if row.get("unlimited"):
        return                                               # the admin uses the Ollama account in full
    if float(row.get("remainingUsd") or 0) <= 0:
        raise NotAllowed("Your cloud credit is used up. Switch to local Ollama or buy a paid plan.")


def record() -> None:
    """Compatibility hook. The engine proxy records provider usage server-side."""


def checkout() -> dict[str, Any]:
    """Start a Stripe checkout for the signed-in account without putting its token in a URL."""
    token = str(config.setting(TOKEN, "") or "")
    if not token:
        return {"ok": False, "error": "Sign in before buying a plan."}
    try:
        code, data = _call("POST", "/api/accounts/checkout", {}, token=token)
    except ConnectionError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": code < 400 and bool(data.get("url")),
            **({"url": data["url"]} if data.get("url") else {"error": str(data.get("error") or "Checkout is unavailable.")})}

def flush() -> bool:
    """Legacy compatibility: no client-side usage batch remains."""
    return False
