"""Connecting Supabase, and giving a project its own real Supabase project inside it.

The Supabase CLI has no browser or device-code sign-in the way `gh`/`vercel`/`netlify`/`az` do
(`cli_signin.py`) - tried live: `supabase login` refuses outright unless it is run in a real
interactive terminal ("Cannot use automatic login flow inside non-TTY environments"), which a
subprocess this server launches never is, and it has no device-code fallback the way GitHub's does.
Its only documented non-interactive path is a pasted personal access token, which is not the
one-click browser sign-in the rest of the Studio gives every other provider.

What Supabase does have is a real OAuth2 API for third-party integrations
(api.supabase.com/v1/oauth/authorize, .../v1/oauth/token, PKCE supported, a `localhost` redirect
explicitly allowed) - confirmed against Supabase's own docs. Unlike GitHub's device flow, its token
endpoint needs a **client secret** as well as a client id, and a secret cannot ship inside an app
everyone installs. So nobody who installs AgentForge registers anything: the publisher registers ONE
OAuth app, and the secret stays in the engine Worker (`engine-proxy/`, the same server that holds the
AI key and that `config.built_in_engine()` already points every copy at). `OAUTH.start()` asks that
broker for the authorize link, and the code exchange and every refresh go through it too; the person
only clicks "Sign in with Supabase" and approves in the browser, the way "Sign in with Google" works.

A copy with no broker (a development checkout with no `engine.json`, or a broker not yet set up)
keeps the older path: the person registers an OAuth app in their own Supabase organisation
(Organization settings -> OAuth Apps -> Publish OAuth app), with `REDIRECT_URI` below as its exact
callback URL, and pastes the Client ID and Secret into Settings. Which path issued the saved tokens
is remembered (`supabase_oauth_via`), because a refresh token only works with the app that issued it.

Either way the browser ends up on the Studio's own already-running API server, at one fixed URL
(`httpd.py`'s `/supabase-oauth/callback` route) - no separate listener to open or a port of its own
to collide with. `OAUTH.start()` opens the browser and hands back a flow id (used as the OAuth
`state`, so the callback route can find it again); the callback route only records what arrived and
answers the browser with a page to close; `OAUTH.poll()` (from the studio, in the background) is
what actually exchanges the code for tokens once they've arrived, refreshing them silently from then
on - one Supabase account for the whole studio, the same as `netlify_token` or `github_token`.

What still needs its own project is the database itself: an account token is not a project's URL
and keys (see the `_no_signin` note this replaced, on the old `supabase` image-upload plugin in
`provider_catalog/plugins.json`) - getting those needs `projects create` against an organisation,
then `projects api-keys` for the ref it made, both run through the CLI with the signed-in account's
access token in its environment. `ensure_project()` does exactly that, once, the first time a
Supabase-stack project actually builds (see `builder_agent/build.py`); every command after that
reads the same record back through `env_for()`.

One AgentForge project gets one real Supabase project. Its URL and keys are kept here, encrypted,
keyed by the AgentForge project - not a studio-wide setting like the account connection above,
because (unlike an account you sign in to once) a database is one project's own.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import string
import subprocess
import threading
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

import httpx
from cryptography.fernet import Fernet

from . import config

KEY = config.STATE / "supabase.key"
VAULT = config.STATE / "supabase.enc"

# --- the one Supabase account this studio is connected as (settings.json, studio-wide) ---------

CLIENT_ID_SETTING = "supabase_client_id"
CLIENT_SECRET_SETTING = "supabase_client_secret"
ACCESS_TOKEN_SETTING = "supabase_oauth_access_token"
REFRESH_TOKEN_SETTING = "supabase_oauth_refresh_token"
EXPIRES_AT_SETTING = "supabase_oauth_expires_at"
ORG_SETTING = "supabase_org"
# Which OAuth app issued the saved tokens: "broker" (the publisher's, through the engine Worker) or "own"
# (one this person registered; also what tokens saved before the broker existed are).
VIA_SETTING = "supabase_oauth_via"
VIA_BROKER, VIA_OWN = "broker", "own"
# The other accounts signed in, kept aside (id -> its tokens); "credentials" in the name keeps them out of GET /settings.
ACCOUNTS_SETTING = "supabase_account_credentials"
ACTIVE_ID_SETTING = "supabase_account_id"

AUTHORIZE_URL = "https://api.supabase.com/v1/oauth/authorize"
TOKEN_URL = "https://api.supabase.com/v1/oauth/token"
CALLBACK_PATH = "/supabase-oauth/callback"
# Fixed, because an OAuth app's callback URL is matched exactly - this is what goes in Supabase's
# own "Authorization callback URLs" field when publishing the app: this studio's own API server
# (API_PORT/API_PREFIX, config.py), not a port of its own and not a project's local Supabase stack
# (which already owns 54321-54323).
#
# "localhost", not "127.0.0.1": tried live - Supabase's authorize endpoint answers
# {"message":"redirect_uri must use HTTPS"} for a loopback *IP*, even though the dashboard's own
# callback-URL field accepts one ("All URLs must use HTTPS, except for localhost"). Supabase's own
# published example uses `http://localhost:54321/...`, confirming the HTTP exception is keyed to
# the literal hostname, not any loopback address - and httpd.serve() binds 127.0.0.1, which
# "localhost" resolves to on the same machine either way.
REDIRECT_URI = f"http://localhost:{config.API_PORT}{config.API_PREFIX}{CALLBACK_PATH}"
FLOW_TTL_SECONDS = 600

# Not a considered choice - just somewhere to start a project before the deploy questions (see
# stack-*-supabase/SKILL.md) ask where it should really run.
DEFAULT_REGION = "us-east-1"


def credentials_saved() -> bool:
    """Whether a person's own OAuth app (Settings) is registered."""
    return bool(config.setting(CLIENT_ID_SETTING) and config.setting(CLIENT_SECRET_SETTING))


def _broker() -> dict[str, str]:
    """The engine Worker that holds the publisher's OAuth app secret ({} when this copy has none)."""
    return config.built_in_engine()


def token_status() -> dict:
    """What the studio may show: whether an account is connected and which, never the tokens.

    `app_registered` is whether signing in can start at all: a broker supplies the OAuth app, so the person
    registers nothing; without one it is whether they registered their own."""
    connected = _signed_in()
    broker = bool(_broker())
    return {"app_registered": broker or credentials_saved(), "connected": connected,
            "org": str(config.setting(ORG_SETTING) or ""), "broker": broker,
            "accounts": accounts(), "active": _current_id() if connected else ""}


def forget_account() -> None:
    """Sign the active account out. Accounts kept aside (`accounts()`) stay signed in."""
    config.save_settings({ACCESS_TOKEN_SETTING: "", REFRESH_TOKEN_SETTING: "", EXPIRES_AT_SETTING: 0,
                          ORG_SETTING: "", VIA_SETTING: "", ACTIVE_ID_SETTING: ""})


# --- more than one account ----------------------------------------------------------------------
#
# One Supabase account is the active one: its tokens are the flat settings above, which is what every build and
# deployment reads. Any others the person has signed in as are kept aside in settings.json, as the active ones are
# (the key name carries "credentials", so GET /settings never returns them), and switching swaps one with the
# active one. An account is told apart by its organisation: a Supabase sign-in is a grant on an organisation, so
# signing in again with another organisation (of the same login or of another) is how a second account is added.

def _signed_in() -> bool:
    return bool(config.setting(ACCESS_TOKEN_SETTING) or config.setting(REFRESH_TOKEN_SETTING))


def _aside() -> dict:
    kept = config.setting(ACCOUNTS_SETTING)
    return dict(kept) if isinstance(kept, dict) else {}


def _current_id() -> str:
    """The active account's id: its organisation's, or - for a session saved before accounts existed, until
    it is next signed in - something stable made from its token."""
    known = str(config.setting(ACTIVE_ID_SETTING) or "")
    if known or not _signed_in():
        return known
    seed = str(config.setting(REFRESH_TOKEN_SETTING) or config.setting(ACCESS_TOKEN_SETTING) or "")
    return "acct-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:10]


def _active_row() -> dict:
    return {"label": str(config.setting(ORG_SETTING) or "Supabase account"),
            "access_token": str(config.setting(ACCESS_TOKEN_SETTING) or ""),
            "refresh_token": str(config.setting(REFRESH_TOKEN_SETTING) or ""),
            "expires_at": float(config.setting(EXPIRES_AT_SETTING) or 0), "via": _via()}


def _make_active(account_id: str, row: dict) -> None:
    config.save_settings({
        ACCESS_TOKEN_SETTING: row.get("access_token", ""), REFRESH_TOKEN_SETTING: row.get("refresh_token", ""),
        EXPIRES_AT_SETTING: row.get("expires_at", 0), VIA_SETTING: row.get("via", ""),
        ORG_SETTING: row.get("label", ""), ACTIVE_ID_SETTING: account_id})


def accounts() -> list[dict]:
    """Every account signed in, the active one first: [{"id", "label", "active"}]. Never the tokens."""
    rows = [{"id": _current_id(), "label": str(config.setting(ORG_SETTING) or "Supabase account"), "active": True}] \
        if _signed_in() else []
    rows += [{"id": key, "label": str(row.get("label") or "Supabase account"), "active": False}
             for key, row in _aside().items() if isinstance(row, dict)]
    return rows


def switch_account(account_id: str) -> dict:
    """Make a signed-in account the one new projects are made in, keeping the one it replaces signed in."""
    account_id = str(account_id or "")
    kept = _aside()
    if account_id == _current_id() and _signed_in():
        return token_status()
    row = kept.pop(account_id, None)
    if not isinstance(row, dict):
        raise ValueError("That Supabase account is not signed in here. Add it first.")
    if _signed_in():
        kept[_current_id()] = _active_row()
    _make_active(account_id, row)
    config.save_settings({ACCOUNTS_SETTING: kept})
    return token_status()


def remove_account(account_id: str) -> dict:
    """Sign one account out of the studio (the active one, or one kept aside). Nothing is deleted on Supabase."""
    account_id = str(account_id or "")
    kept = _aside()
    if account_id in kept:
        kept.pop(account_id)
        config.save_settings({ACCOUNTS_SETTING: kept})
    elif _signed_in() and account_id == _current_id():
        forget_account()
    else:
        raise ValueError("That Supabase account is not signed in here.")
    return token_status()


def _json_body(answer: httpx.Response) -> dict:
    try:
        body = answer.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _via() -> str:
    """Which OAuth app issued the saved tokens (anything saved before the broker existed is the person's own)."""
    return VIA_BROKER if config.setting(VIA_SETTING) == VIA_BROKER else VIA_OWN


def _broker_post(path: str, payload: dict) -> httpx.Response:
    engine = _broker()
    if not engine:
        raise ValueError("This copy of AgentForge has no sign-in server to use.")
    return httpx.post(f"{engine['url']}{path}", json=payload, timeout=30,
                      headers={"Authorization": f"Bearer {engine['token']}", "Accept": "application/json"})


def _token_request(form: dict, via: str) -> httpx.Response:
    """Trade a code or a refresh token for tokens, as the OAuth app that `via` names. Through the broker the
    client secret is added by the Worker; on the person's own app it is added here."""
    if via == VIA_BROKER:
        return _broker_post("/oauth/supabase/token", form)
    client_id, client_secret = str(config.setting(CLIENT_ID_SETTING) or ""), str(config.setting(CLIENT_SECRET_SETTING) or "")
    own = dict(form)
    if own["grant_type"] == "authorization_code":
        own["redirect_uri"] = REDIRECT_URI
    return httpx.post(TOKEN_URL, auth=(client_id, client_secret), data=own,
                      headers={"Accept": "application/json"}, timeout=30)


def _keep_tokens(body: dict, via: str | None = None) -> dict:
    """Keep the tokens just issued as the active account's. A sign-in (`via` given) that lands on a different
    organisation than the one active keeps the one it replaces signed in, aside; a refresh only renews."""
    previous = None
    if via and _signed_in():
        previous = {"id": _current_id(), **_active_row()}
        if not config.setting(ACTIVE_ID_SETTING):
            # Saved before accounts existed: ask which organisation it is while its own token is still the one in use.
            previous["id"] = _fetch_org().get("id") or previous["id"]
    expires_in = int(body.get("expires_in") or 3600)
    config.save_settings({
        ACCESS_TOKEN_SETTING: str(body.get("access_token") or ""),
        REFRESH_TOKEN_SETTING: str(body.get("refresh_token") or config.setting(REFRESH_TOKEN_SETTING) or ""),
        EXPIRES_AT_SETTING: time.time() + expires_in - 60,
        **({VIA_SETTING: via} if via else {}),
    })
    org = _fetch_org()
    if org.get("name"):
        config.save_settings({ORG_SETTING: org["name"]})
    if org.get("id") and (via or not config.setting(ACTIVE_ID_SETTING)):
        config.save_settings({ACTIVE_ID_SETTING: org["id"]})
    elif via:
        config.save_settings({ACTIVE_ID_SETTING: ""})   # which organisation this is cannot be asked: do not keep the last one's id
    if via:
        kept = _aside()
        kept.pop(org.get("id") or "", None)            # signed in again as one kept aside: it is the active one now
        if previous and org.get("id") and previous["id"] != org["id"]:
            kept[previous.pop("id")] = previous
        config.save_settings({ACCOUNTS_SETTING: kept})
    return token_status()


def _fetch_org() -> dict:
    """The organisation the active token was granted on: {"id", "name"}, or {} when it cannot be asked."""
    try:
        orgs = _run_json([_tool(), "orgs", "list", "--output", "json"]) or []
    except ValueError:
        return {}
    first = orgs[0] if isinstance(orgs, list) and orgs and isinstance(orgs[0], dict) else {}
    return {"id": str(first.get("id") or ""), "name": str(first.get("name") or "")}


def _refresh_if_needed() -> str:
    """The access token to use right now, silently refreshed if it has lapsed."""
    access = str(config.setting(ACCESS_TOKEN_SETTING) or "")
    expires_at = float(config.setting(EXPIRES_AT_SETTING) or 0)
    if access and time.time() < expires_at:
        return access
    refresh = str(config.setting(REFRESH_TOKEN_SETTING) or "")
    if not refresh:
        return access
    try:
        answer = _token_request({"grant_type": "refresh_token", "refresh_token": refresh}, _via())
        body = _json_body(answer)
        if answer.status_code < 400 and body.get("access_token"):
            _keep_tokens(body)
            return str(body["access_token"])
    except (httpx.HTTPError, ValueError):
        pass
    # Stale and could not be refreshed (revoked, network down): handed to the CLI as-is, so the
    # failure is a clear 401 from Supabase's own API rather than a silent, wrongly-scoped success.
    return access


def _env_with_token() -> dict[str, str]:
    return {**os.environ, "NO_COLOR": "1", "SUPABASE_ACCESS_TOKEN": _refresh_if_needed()}


# --- the browser sign-in itself (PKCE authorization-code, callback on the studio's own server) --

def _pkce_pair() -> tuple[str, str]:
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).decode("ascii").rstrip("=")
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode("ascii").rstrip("=")
    return verifier, challenge


@dataclass
class _Flow:
    flow_id: str
    verifier: str
    via: str = VIA_OWN  # which OAuth app this sign-in is with, so its code is exchanged with the same one
    started: float = field(default_factory=time.time)
    result: dict | None = None  # set by receive_callback() once the browser redirect lands


class OAuthConnects:
    """One sign-in at a time: a browser tab, a callback the studio's own server catches, and the
    token exchange. The flow id doubles as the OAuth `state` - it only has to be opaque and
    round-tripped unchanged, which is exactly what `state` is for, so a second value would be
    redundant."""

    def __init__(self) -> None:
        self._flows: dict[str, _Flow] = {}
        self._lock = threading.RLock()

    def _prune(self) -> None:
        now = time.time()
        for key in [k for k, f in self._flows.items() if now - f.started > FLOW_TTL_SECONDS]:
            self._flows.pop(key, None)

    @staticmethod
    def _broker_link(flow_id: str, challenge: str) -> str:
        """The authorize link from the broker: it knows the OAuth app's client id and the one callback URL that
        app was registered with, and signs the state so only it will accept the browser coming back."""
        try:
            answer = _broker_post("/oauth/supabase/start",
                                  {"flow_id": flow_id, "challenge": challenge, "return_to": REDIRECT_URI})
        except httpx.HTTPError as exc:
            raise ValueError(f"The AgentForge sign-in server could not be reached: {exc}") from exc
        body = _json_body(answer)
        link = str(body.get("authorize_url") or "")
        if answer.status_code >= 400 or not link:
            raise ValueError(str(body.get("error") or f"Supabase sign-in is not available (HTTP {answer.status_code})."))
        # Opened in the person's browser, so only ever Supabase's own authorize page.
        if not link.startswith(AUTHORIZE_URL + "?"):
            raise ValueError("The sign-in server answered with a link that is not Supabase's. Not opened.")
        return link

    def _own_link(self, flow_id: str, challenge: str) -> str:
        params = {"response_type": "code", "client_id": str(config.setting(CLIENT_ID_SETTING) or ""),
                  "redirect_uri": REDIRECT_URI, "scope": "all", "state": flow_id,
                  "code_challenge": challenge, "code_challenge_method": "S256"}
        return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    def start(self) -> dict:
        verifier, challenge = _pkce_pair()
        flow_id = "sbo_" + secrets.token_urlsafe(24)
        via, link = VIA_OWN, ""
        if _broker():
            # The publisher's OAuth app: nothing for the person to register. If the broker is not set up (or not
            # reachable) a person's own saved app still works; with none, say why.
            try:
                via, link = VIA_BROKER, self._broker_link(flow_id, challenge)
            except ValueError:
                if not credentials_saved():
                    raise
        elif not credentials_saved():
            raise ValueError("Register a Supabase OAuth app first (Organization settings -> OAuth Apps) "
                              "and save its Client ID and Secret.")
        if not link:
            via, link = VIA_OWN, self._own_link(flow_id, challenge)
        # The desktop app listens on no port: its callback is answered only while this sign-in is waiting.
        from . import oauth_listener

        oauth_listener.open_for(CALLBACK_PATH, FLOW_TTL_SECONDS)
        with self._lock:
            self._prune()
            self._flows[flow_id] = _Flow(flow_id=flow_id, verifier=verifier, via=via)
        return {"flow_id": flow_id, "verification_uri": link}

    def receive_callback(self, state: str, code: str, error: str) -> bool:
        """Called by httpd.py's `/supabase-oauth/callback` route, on the browser's own request.
        Only records what arrived - the exchange happens from `poll()`, so a network hiccup here
        doesn't lose a callback the browser will not send twice. Returns whether `state` matched a
        flow this studio actually started (the route uses this to choose its response page)."""
        with self._lock:
            flow = self._flows.get(str(state or ""))
            if not flow:
                return False
            flow.result = {"code": code, "error": error}
        return True

    def poll(self, flow_id: str) -> dict:
        with self._lock:
            flow = self._flows.get(str(flow_id or ""))
        if not flow:
            raise ValueError("That sign-in is no longer running. Start it again.")
        if flow.result is None:
            if time.time() - flow.started > FLOW_TTL_SECONDS:
                with self._lock:
                    self._flows.pop(flow.flow_id, None)
                raise ValueError("That sign-in timed out. Start it again.")
            return {"status": "pending"}
        with self._lock:
            self._flows.pop(flow.flow_id, None)
        if flow.result.get("error"):
            raise ValueError(f"Supabase refused the sign-in: {flow.result['error']}")
        if not flow.result.get("code"):
            raise ValueError("Supabase did not send back an authorization code.")
        return self._exchange(flow.result["code"], flow.verifier, flow.via)

    def _exchange(self, code: str, verifier: str, via: str = VIA_OWN) -> dict:
        try:
            answer = _token_request({"grant_type": "authorization_code", "code": code, "code_verifier": verifier}, via)
        except httpx.HTTPError as exc:
            raise ValueError(f"Supabase could not be reached: {exc}") from exc
        body = _json_body(answer)
        if answer.status_code >= 400 or not body.get("access_token"):
            raise ValueError(str(body.get("error_description") or body.get("message") or body.get("error")
                                 or f"Supabase rejected the sign-in (HTTP {answer.status_code})."))
        return {"status": "ready", **_keep_tokens(body, via)}

    def cancel(self, flow_id: str) -> dict:
        with self._lock:
            self._flows.pop(str(flow_id or ""), None)
        return {"status": "cancelled"}


OAUTH = OAuthConnects()


# --- the encrypted, per-project record (which real Supabase project this project owns) ----------

def _cipher() -> Fernet:
    KEY.parent.mkdir(parents=True, exist_ok=True)
    if not KEY.is_file():
        KEY.write_bytes(Fernet.generate_key())
        try:
            os.chmod(KEY, 0o600)
        except OSError:
            pass
    return Fernet(KEY.read_bytes())


def _read_all() -> dict[str, dict]:
    if not VAULT.is_file():
        return {}
    try:
        return json.loads(_cipher().decrypt(VAULT.read_bytes()).decode("utf-8"))
    except (OSError, ValueError):
        return {}


def _write_all(rows: dict[str, dict]) -> None:
    VAULT.parent.mkdir(parents=True, exist_ok=True)
    VAULT.write_bytes(_cipher().encrypt(json.dumps(rows).encode("utf-8")))
    try:
        os.chmod(VAULT, 0o600)
    except OSError:
        pass


def record(project: str) -> dict:
    """This project's connected Supabase project, or {} if none is linked yet."""
    return _read_all().get(str(project), {})


def status(project: str) -> dict:
    """What the studio may show: never the keys, only that a project is linked and which one."""
    row = record(project)
    if not row:
        return {"connected": False}
    return {"connected": True, "ref": row.get("ref", ""), "name": row.get("name", ""),
            "url": row.get("url", "")}


def env_for(project: str) -> dict[str, str]:
    """What a build, test or deploy command is given: every alias a framework's template expects.

    Handing out all of them regardless of stack is harmless - an unused one is simply never read -
    and saves this module from knowing which of the five stacks is asking.
    """
    row = record(project)
    if not row:
        return {}
    url, anon, service = row.get("url", ""), row.get("anon_key", ""), row.get("service_role_key", "")
    ref, password = row.get("ref", ""), row.get("db_password", "")
    env = {
        "SUPABASE_URL": url, "SUPABASE_ANON_KEY": anon, "SUPABASE_SERVICE_ROLE_KEY": service,
        "NEXT_PUBLIC_SUPABASE_URL": url, "NEXT_PUBLIC_SUPABASE_ANON_KEY": anon,
        "VITE_SUPABASE_URL": url, "VITE_SUPABASE_ANON_KEY": anon,
    }
    if ref and password:
        # The direct Postgres connection (`supabase db push`, and this project's own QA-run
        # database connection used by migrations or commands) - not something a client ever reads,
        # so it carries no NEXT_PUBLIC_/VITE_ alias.
        env["SUPABASE_DB_URL"] = f"postgresql://postgres:{password}@db.{ref}.supabase.co:5432/postgres"
    return env


def forget(project: str) -> None:
    rows = _read_all()
    if rows.pop(str(project), None) is not None:
        _write_all(rows)


# --- making the one project this AgentForge project gets ---------------------------------------

def _tool() -> str:
    from . import cli_signin
    found = cli_signin._where("supabase")  # noqa: SLF001 - the one place outside cli_signin that needs it
    if not found:
        raise ValueError("The Supabase command line tool is not installed on this machine. "
                          "Install it with `npm i -g supabase` and try again.")
    return found


def _run_json(args: list[str], timeout: int = 40) -> Any:
    """A CLI subcommand that prints `--output json` (or nothing useful), decoded if it can be."""
    done = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL,
                          shell=os.name == "nt", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                          env=_env_with_token())
    if done.returncode != 0:
        raise ValueError((done.stderr or done.stdout or "the Supabase CLI refused that command").strip()[:400])
    text = (done.stdout or "").strip()
    start = text.find("[") if text.find("[") != -1 else text.find("{")
    if start < 0:
        return None
    try:
        return json.loads(text[start:])
    except ValueError:
        return None


def _db_password() -> str:
    # Supabase requires one to create a project; this app talks to Postgres through the REST/Auth/
    # Storage APIs and the service-role key, not a raw connection string, so nobody ever types this -
    # it is generated, kept in the same encrypted record as the keys, and used again for `db push`.
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


def _keys_from(rows: Any) -> tuple[str, str]:
    """Both shapes the CLI has printed for this command across versions: a list of {name, api_key},
    or a single object with anon_key/service_role_key fields directly."""
    if isinstance(rows, list):
        by_name = {str(r.get("name", "")).lower(): str(r.get("api_key", "")) for r in rows if isinstance(r, dict)}
        return by_name.get("anon", ""), by_name.get("service_role", "")
    if isinstance(rows, dict):
        return str(rows.get("anon_key", "")), str(rows.get("service_role_key", ""))
    return "", ""


def account_facts() -> dict:
    """What the connected Supabase account already has, for the build to ask about: its organisations
    (each one's plan when Supabase says it) and its projects. Never keys. Empty when nothing can be read."""
    if not token_status()["connected"]:
        return {"connected": False}
    out: dict[str, Any] = {"connected": True, "organizations": [], "projects": []}
    try:
        tool = _tool()
        orgs = _run_json([tool, "orgs", "list", "--output", "json"]) or []
        projects = _run_json([tool, "projects", "list", "--output", "json"]) or []
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        out["unreadable"] = str(exc)[:200]
        return out
    token = _refresh_if_needed()
    for org in orgs if isinstance(orgs, list) else []:
        if not isinstance(org, dict):
            continue
        row = {"id": str(org.get("id") or org.get("slug") or ""), "name": str(org.get("name") or "")}
        try:
            answer = httpx.get(f"https://api.supabase.com/v1/organizations/{row['id']}",
                               headers={"Authorization": f"Bearer {token}"}, timeout=10)
            plan = _json_body(answer).get("plan") if answer.status_code < 400 else None
            if plan:
                row["plan"] = str(plan)
        except httpx.HTTPError:
            pass
        out["organizations"].append(row)
    for item in projects if isinstance(projects, list) else []:
        if isinstance(item, dict):
            out["projects"].append({key: str(item.get(key) or "") for key in
                                    ("name", "region", "status", "organization_id")}
                                   | {"ref": str(item.get("id") or item.get("ref") or "")})
    return out


def linked_projects() -> dict[str, str]:
    """Which AgentForge project uses each Supabase project this studio made: ref → AgentForge project id."""
    return {str(row.get("ref")): key for key, row in _read_all().items() if isinstance(row, dict) and row.get("ref")}


def make_room(ref: str, action: str, log=None) -> None:
    """Pause or delete one of the account's projects so a new one fits in its organisation.

    Only ever the project the customer named and chose this for (builder setup checks they were asked about that
    very project). Pausing keeps everything and is undone from the Supabase dashboard; deleting is permanent. Waits
    until Supabase has let the project go, because the organisation's slot is free only then; a project already
    paused or gone is left as it is, so a build that tries again does not do it twice.
    """
    if action not in ("pause", "delete"):
        raise ValueError('make_room takes "pause" or "delete"')
    say = log or (lambda _line: None)
    headers = {"Authorization": f"Bearer {_refresh_if_needed()}"}
    url = f"https://api.supabase.com/v1/projects/{ref}"

    def current() -> str:
        answer = httpx.get(url, headers=headers, timeout=15)
        if answer.status_code == 404:
            return "GONE"
        return str(_json_body(answer).get("status") or "").upper() if answer.status_code < 400 else ""

    done = {"pause": {"INACTIVE", "PAUSED", "GONE", "REMOVED"}, "delete": {"GONE", "REMOVED"}}[action]
    if current() not in done:
        say(f"{'Pausing' if action == 'pause' else 'Deleting'} the Supabase project {ref}, as you chose…")
        answer = (httpx.post(f"{url}/pause", headers=headers, timeout=30) if action == "pause"
                  else httpx.delete(url, headers=headers, timeout=30))
        if answer.status_code >= 400:
            reason = _json_body(answer).get("message") or answer.text
            raise ValueError(f"Supabase would not {action} project {ref}: {str(reason)[:300]}")
        for _ in range(48):  # ~4 minutes
            if current() in done:
                break
            time.sleep(5)
        else:
            raise ValueError(f"Supabase is still taking project {ref} down; its place in the organisation is not free "
                             "yet. Try again in a few minutes.")
    if action == "delete":
        # The AgentForge project that used it has no Supabase project any more: its next build makes a new one.
        rows = _read_all()
        gone = [key for key, row in rows.items() if isinstance(row, dict) and row.get("ref") == ref]
        for key in gone:
            rows.pop(key, None)
        if gone:
            _write_all(rows)
    say(f"Supabase project {ref} {'paused' if action == 'pause' else 'deleted'}.")


def ensure_project(project: str, name: str = "", log=None, region: str = "", org_id: str = "",
                   fresh: bool = False) -> dict:
    """The project's own Supabase project: the existing one, or a freshly created one.

    Blocking (project creation takes a minute or two): called from the build pipeline, which
    already runs in its own background thread and already streams progress, rather than from a
    request a browser is waiting on - `log`, when given, is called with short progress lines the
    same way `bus.log` is, so the build's own activity feed can show them.
    """
    project = str(project or "")
    if not project:
        raise ValueError("no project given")
    if fresh:
        forget(project)  # a new one was asked for: the old project stays in the account, unused by this one
    existing = record(project)
    if existing:
        return status(project)
    if not token_status()["connected"]:
        raise ValueError("No Supabase account is connected yet. Pick this stack again and sign in "
                          "when prompted, then start the build.")

    say = log or (lambda _line: None)
    tool = _tool()
    say("Creating this project's own Supabase project…")
    orgs = _run_json([tool, "orgs", "list", "--output", "json"]) or []
    if not isinstance(orgs, list) or not orgs:
        raise ValueError("Your Supabase account has no organisation to create a project in. "
                          "Make one at supabase.com/dashboard/organizations and try again.")
    known = {str(org.get("id") or org.get("slug") or "") for org in orgs if isinstance(org, dict)}
    if org_id and org_id not in known:
        raise ValueError(f"Your Supabase account has no organisation {org_id}.")
    org_id = org_id or str(orgs[0].get("id") or orgs[0].get("slug") or "")
    db_password = _db_password()
    created = _run_json([
        tool, "projects", "create", name or project, "--org-id", org_id,
        "--db-password", db_password, "--region", region or DEFAULT_REGION, "--output", "json",
    ], timeout=60) or {}
    ref = str(created.get("id") or created.get("ref") or "")
    if not ref:
        raise ValueError("Supabase did not return the new project's reference.")

    say(f"Project {ref} created - waiting for it to come up…")
    anon, service = "", ""
    for _ in range(36):  # ~3 minutes
        try:
            keys = _run_json([tool, "projects", "api-keys", "--project-ref", ref, "--output", "json"])
        except ValueError:
            keys = None  # still provisioning
        anon, service = _keys_from(keys)
        if anon and service:
            break
        time.sleep(5)
    if not anon or not service:
        raise ValueError(f"Project {ref} did not finish provisioning in time. Check "
                          f"supabase.com/dashboard/project/{ref} and try the build again.")

    row = {"ref": ref, "name": name or project, "url": f"https://{ref}.supabase.co",
          "anon_key": anon, "service_role_key": service, "db_password": db_password}
    rows = _read_all()
    rows[project] = row
    _write_all(rows)
    say(f"Supabase project ready: {row['url']}")
    return status(project)
