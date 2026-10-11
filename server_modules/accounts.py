"""AgentForge accounts: a person signs in with an account the admin approved, and every model call is one request against the
request limit the admin gave it.

The accounts live in the admin app (a separate project, `C:\\agentforge-admin`, deployed with its own MongoDB). Its address
ships with AgentForge in `accounts.json` (or `AGENTFORGE_ACCOUNTS_URL`); with none, accounts are off and AgentForge works as it
always did, signed in as the person at this computer. Accounts apply in the Studio's own backend, which turns them on at start
(`switch_on`, from server.py); the code used on its own (the tests, a script) is never asked to sign in.

- Creating an account sends it to the admin for approval; signing in works once it is approved, and keeps the account's sign-in token.
- Every model call (`session.RetryingClient.chat`) asks `check()` first: a person who is not signed in, whose account is not
  approved, or whose requests are used up gets a plain answer instead of the call. A run already going finishes its current call.
- Each call that the model answers is one request (`record`): the count here goes up at once and is shown live
  (`account_usage` events), and the requests are sent to the admin app a few at a time, which answers with the limit and what
  is used.
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from . import bus, config

SERVER_FILE = Path(__file__).with_name("accounts.json")
TOKEN = "account_token"
CACHE = "account"
FRESH_SECONDS = 15           # how long what the admin app said about the account is believed before asking again
FLUSH_SECONDS = 2            # how often counted requests are sent
TIMEOUT = httpx.Timeout(15.0, connect=8.0)

_lock = threading.Lock()
_on = False                  # set by the Studio's backend at start
_pending = {"requests": 0}
_asked_at = 0.0
_flusher: threading.Thread | None = None


class NotAllowed(RuntimeError):
    """A model call the account may not make: not signed in, not approved, or out of requests."""


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
    row = {key: account.get(key) for key in ("id", "email", "name", "username", "status", "limit", "used")}
    row["unlimited"] = bool(account.get("unlimited"))         # the admin: never limited
    if isinstance(account.get("ollama"), dict):
        row["ollama"] = account["ollama"]                    # the admin is told the Ollama account's balance
    row["remaining"] = max(0, int(account.get("limit") or 0) - int(account.get("used") or 0))
    config.save_settings({CACHE: row})
    _asked_at = time.time()
    bus.transient({"type": "account_usage", **row})
    return row


def signup(username: str, email: str, password: str, name: str = "") -> dict[str, Any]:
    status, data = _call("POST", "/api/accounts/signup", {"username": username, "email": email, "password": password,
                                                          "name": name})
    if status >= 400:
        return {"ok": False, "error": str(data.get("error") or "The account could not be created.")}
    return {"ok": False, "pending": True,
            "error": "Your account is created and is waiting for the admin's approval. You can sign in once it is approved."}


def login(login_name: str, password: str) -> dict[str, Any]:
    status, data = _call("POST", "/api/accounts/login", {"login": login_name, "password": password})
    if status == 403 and data.get("status") == "pending":
        return {"ok": False, "pending": True, "error": "Your account is waiting for the admin's approval."}
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
    out = {"status": row.get("status") or "", "limit": int(row.get("limit") or 0), "used": int(row.get("used") or 0),
           "remaining": max(0, int(row.get("limit") or 0) - int(row.get("used") or 0)), "unlimited": bool(row.get("unlimited"))}
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
    """Raise NotAllowed when the signed-in account may not make a model call now."""
    if not enabled():
        return
    row = current()
    if not row:
        raise NotAllowed("Sign in to AgentForge to use the AI.")
    if row.get("status") != "approved":
        raise NotAllowed("Your AgentForge account is waiting for the admin's approval.")
    if row.get("unlimited"):
        return                                               # the admin uses the Ollama account in full
    with _lock:
        waiting = _pending["requests"]
    if int(row.get("limit") or 0) - int(row.get("used") or 0) - waiting <= 0:
        raise NotAllowed("Your request limit is used up. Ask the admin for more requests.")


def record() -> None:
    """Count one request the model answered: at once here (shown live), and soon at the admin app."""
    if not enabled() or not config.setting(TOKEN, ""):
        return
    with _lock:
        _pending["requests"] += 1
        waiting = _pending["requests"]
    cached = dict(config.setting(CACHE, {}) or {})
    if cached:
        bus.transient({"type": "account_usage", **cached, "used": int(cached.get("used") or 0) + waiting,
                       "remaining": max(0, int(cached.get("limit") or 0) - int(cached.get("used") or 0) - waiting)})
    _start_flusher()


def _start_flusher() -> None:
    global _flusher
    with _lock:
        if _flusher and _flusher.is_alive():
            return
        _flusher = threading.Thread(target=_flush_loop, name="account-usage", daemon=True)
        _flusher.start()


def _flush_loop() -> None:
    while True:
        time.sleep(FLUSH_SECONDS)
        if not flush():
            return


def flush() -> bool:
    """Send the counted requests to the admin app. Returns whether there is still something to send (a failed send is kept)."""
    with _lock:
        batch = dict(_pending)
        if not batch["requests"]:
            return False
        for key in _pending:
            _pending[key] = 0
    token = str(config.setting(TOKEN, "") or "")
    try:
        code, data = _call("POST", "/api/accounts/usage", batch, token=token) if token else (401, {})
    except ConnectionError:
        code, data = 0, {}
    if code == 0:                                             # not reached: kept, and sent with the next ones
        with _lock:
            for key in _pending:
                _pending[key] += batch[key]
        return True
    if data.get("account"):
        _remember(data["account"])
    return False
