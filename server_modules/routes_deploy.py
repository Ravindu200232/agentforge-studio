"""The `/deploy/...` router.

The studio's Deploy panel polls a run rather than holding a socket open for it,
so everything here reads the run's own files back. A deployment that is still
going and a deployment that finished an hour ago are answered the same way.
"""
from __future__ import annotations

import json

import re
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from deploy_agent import deploy as deployer

from . import config, mongo_check, mongo_connect, store

Handler = Callable[[dict[str, Any]], Any]

_ROUTES: list[tuple[str, re.Pattern[str], Handler]] = []


def route(method: str, pattern: str) -> Callable[[Handler], Handler]:
    compiled = re.compile("^" + pattern + "$")

    def register(fn: Handler) -> Handler:
        _ROUTES.append((method.upper(), compiled, fn))
        return fn

    return register


def dispatch(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    parsed = urlparse(path or "")
    clean = "/" + parsed.path.strip("/")
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    for verb, pattern, handler in _ROUTES:
        if verb != method.upper():
            continue
        match = pattern.match(clean)
        if match:
            return handler({**(body or {}), "_match": match, "_query": query})
    raise FileNotFoundError(f"no deployment route for {method} {clean}")


def _project_of(run_id: str) -> str:
    """Which project owns this run. Runs are per project, so the store knows."""
    for row in store.listing():
        state = deployer.run_state(row["name"])
        if state.get("run_id") == run_id:
            return row["name"]
    raise FileNotFoundError(f"no deployment run {run_id}")


# --- what the panel asks on load -------------------------------------------

@route("GET", r"/onboarding/status")
def onboarding_status(_body: dict) -> Any:
    """Which targets are usable, and what is still missing for each."""
    saved = config.settings()
    return {
        "ok": True,
        "targets": deployer.targets(),
        "accounts": {
            "github": bool(saved.get("github_token")),
            "vercel": bool(saved.get("vercel_token")),
            "netlify": bool(saved.get("netlify_token")),
            "azure": bool(saved.get("azure_token") or saved.get("azure_credentials") or saved.get("azure_account")),
            "aws": bool(saved.get("aws_profile")),
        },
        "engine": "ollama-terminal",
    }


@route("POST", r"/onboarding/login")
def onboarding_login(body: dict) -> Any:
    """Record a provider credential. The value is stored, never returned."""
    provider = str(body.get("provider") or "").strip()
    token = str(body.get("token") or "").strip()
    if not provider:
        raise ValueError("name the provider")
    config.save_settings({f"{provider}_token": token})
    return {"ok": True, "provider": provider, "saved": bool(token)}


@route("POST", r"/aws/(?P<provider>[^/]+)/status")
@route("GET", r"/aws/(?P<provider>[^/]+)/status")
def provider_status(body: dict) -> Any:
    provider = body["_match"].group("provider")
    saved = config.settings()
    connected = any(saved.get(f"{provider}_{kind}") for kind in ("token", "profile", "credentials", "account"))
    answer = {"ok": True, "provider": provider, "connected": bool(connected)}
    if saved.get(f"{provider}_account"):
        try:                                   # what the CLI sign-in recorded about who is signed in
            who = json.loads(saved[f"{provider}_account"])
            answer["account"] = " · ".join(str(x) for x in (who.get("account"), who.get("subscription")) if x)
        except ValueError:
            pass
    return answer


@route("POST", r"/mongodb/status")
def mongodb_status(body: dict) -> Any:
    """Try a connection string for real, the same check a value question runs before it accepts one
    (deploy_vars.accept). An empty `uri` tests the saved production value instead of a typed one, the
    same shape `provider_status`'s `HostedCredential` card already uses for Netlify's and Azure's own
    tokens - so this Row's "Test connection" button needs nothing special to work the same way."""
    uri = str(body.get("uri") or "").strip()
    saved = bool(not uri and config.setting("deploy_mongodb_uri", ""))
    try:
        result = mongo_check.check(uri)
    except Exception as exc:  # noqa: BLE001 - a check that cannot run is reported, not a 500
        result = {"ok": False, "stage": "error", "message": str(exc)[:300]}
    return {"ok": True, "connected": bool(result.get("ok")), "using_saved": saved,
            "message": result.get("message", ""), "stage": result.get("stage", ""),
            "warnings": result.get("warnings") or []}


@route("GET", r"/mongodb/account/status")
def mongodb_account_status(_body: dict) -> Any:
    return {"ok": True, **mongo_connect.status()}


@route("POST", r"/mongodb/account/save")
def mongodb_account_save(body: dict) -> Any:
    """A Service Account's Client ID and Secret, tried for real (a token exchange) before saving -
    the same "verify before accept" rule every credential in this studio follows."""
    result = mongo_connect.save_account(str(body.get("client_id") or ""), str(body.get("client_secret") or ""))
    return {"ok": True, **result}


@route("POST", r"/mongodb/account/forget")
def mongodb_account_forget(_body: dict) -> Any:
    mongo_connect.forget_account()
    return {"ok": True}


@route("POST", r"/mongodb/provision")
def mongodb_provision(_body: dict) -> Any:
    """Create (or reuse) the studio's one Atlas cluster and point deploy_mongodb_uri at it. Slow
    (a few minutes) - the caller already runs this through the Deploy panel's job queue, same as
    everything else here that takes real time."""
    return {"ok": True, **mongo_connect.ensure_cluster()}


# --- one run ----------------------------------------------------------------

@route("GET", r"/runs/(?P<run>[^/]+)")
def run_detail(body: dict) -> Any:
    run_id = body["_match"].group("run")
    return deployer.run_state(_project_of(run_id))


@route("GET", r"/runs/(?P<run>[^/]+)/events")
def run_events(body: dict) -> Any:
    run_id = body["_match"].group("run")
    recent = int(body["_query"].get("recent") or 1000)
    return {"events": deployer.events(_project_of(run_id), limit=recent)}


@route("GET", r"/runs/(?P<run>[^/]+)/monitor")
def run_monitor(body: dict) -> Any:
    run_id = body["_match"].group("run")
    project = _project_of(run_id)
    state = deployer.run_state(project)
    return {
        "snap": {
            "state": state.get("state", ""),
            "url": state.get("url", ""),
            "errors": [state["error"]] if state.get("error") else [],
            "security": state.get("security") or {},
        },
        "question": deployer.pending_question(project),
    }


@route("GET", r"/runs/(?P<run>[^/]+)/artifacts")
def run_artifacts(body: dict) -> Any:
    run_id = body["_match"].group("run")
    state = deployer.run_state(_project_of(run_id))
    return {"artifacts": state.get("artifacts") or []}


@route("GET", r"/runs/(?P<run>[^/]+)/artifact")
def run_artifact(body: dict) -> Any:
    from .session import session_for

    run_id = body["_match"].group("run")
    project = _project_of(run_id)
    wanted = str(body["_query"].get("path") or "")
    session = session_for(project)
    path = (session.workspace / wanted).resolve()
    if not path.is_relative_to(session.workspace.resolve()) or not path.is_file():
        raise FileNotFoundError(wanted)
    return {"path": wanted, "content": path.read_text(encoding="utf-8", errors="replace")}


@route("GET", r"/runs/(?P<run>[^/]+)/evidence")
def run_evidence(body: dict) -> Any:
    run_id = body["_match"].group("run")
    state = deployer.run_state(_project_of(run_id))
    return {"evidence": state.get("evidence") or []}


@route("POST", r"/runs/(?P<run>[^/]+)/answer")
def run_answer(body: dict) -> Any:
    run_id = body["_match"].group("run")
    return deployer.answer(_project_of(run_id), str(body.get("reply") or ""))


@route("POST", r"/runs/(?P<run>[^/]+)/cancel")
def run_cancel(body: dict) -> Any:
    run_id = body["_match"].group("run")
    return deployer.cancel(_project_of(run_id))
