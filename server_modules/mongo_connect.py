"""Connecting a MongoDB Atlas account, and giving the studio a real cluster of its own.

Atlas has a true browser sign-in OAuth2 flow (Atlas App Connections, authorization-code + PKCE,
the same shape as `supabase_connect.py`'s own OAuth dance) - but unlike Supabase's, it is not
self-service: MongoDB issues the `client_id`/`client_secret` only after approving an application as
a design partner (confirmed live against
https://www.mongodb.com/docs/atlas/app-connections/partner-integration-guide/ - its own
"Prerequisites & Eligibility" section says so explicitly). Until that approval exists, this studio
cannot offer the Supabase-style "click to sign in, a browser opens" button for Atlas at all.

What *is* self-service today is a Service Account - Atlas's own recommended replacement for a bare
API key pair, and still real OAuth2 underneath (`POST https://cloud.mongodb.com/api/oauth/token`,
`grant_type=client_credentials`, confirmed live against MongoDB's docs). The customer creates one
once, in the Atlas UI (Organization Access Manager -> Service Accounts, any role that can manage
projects and clusters), and pastes its Client ID and Secret here - the one-time paste every other
CLI-less provider in this studio already needs (`cli_signin.py`'s Supabase note), except the
exchange itself is a standard, verifiable OAuth2 grant rather than a bespoke token format.

One studio-wide connection, like the account-level tokens in `config.py` (`github_token`,
`vercel_token`, ...) - a Service Account belongs to the customer's Atlas organisation, not to one
AgentForge project, and `deploy_mongodb_uri` (the setting this module ultimately writes) is already
studio-wide for exactly that reason. `ensure_cluster()` creates (or reuses) one free M0 cluster, one
database user and an open-from-anywhere IP access list entry, then writes the resulting real
`mongodb+srv://` connection string into that same setting - every other part of the system
(`deploy_vars.py`, `mongo_check.py`, the Integrations panel's plain paste box) keeps working exactly
as it does for a hand-typed string, because that is still, in the end, exactly what this produces.
"""
from __future__ import annotations

import secrets
import string
import time
from typing import Any

import httpx

from . import config

TOKEN_URL = "https://cloud.mongodb.com/api/oauth/token"
API_BASE = "https://cloud.mongodb.com/api/atlas/v2"
API_VERSION = "application/vnd.atlas.2023-01-01+json"

CLIENT_ID_SETTING = "mongodb_client_id"
CLIENT_SECRET_SETTING = "mongodb_client_secret"
ACCESS_TOKEN_SETTING = "mongodb_oauth_access_token"
EXPIRES_AT_SETTING = "mongodb_oauth_expires_at"
ORG_SETTING = "mongodb_org"

# What a provisioned cluster is called and recorded under - not a customer choice (this is the one
# studio-wide cluster, not a project of its own the way Supabase's is), just somewhere stable to
# look for it again so a second `ensure_cluster()` call reuses it instead of making another.
GROUP_NAME = "agentforge-studio"
CLUSTER_NAME = "agentforge"
DB_USERNAME = "agentforge_app"
DEFAULT_REGION = "US_EAST_1"

GROUP_ID_SETTING = "mongodb_atlas_group_id"
CLUSTER_NAME_SETTING = "mongodb_atlas_cluster_name"


def credentials_saved() -> bool:
    return bool(config.setting(CLIENT_ID_SETTING) and config.setting(CLIENT_SECRET_SETTING))


def status() -> dict:
    """What the studio may show: never the credentials or tokens, only that an account is
    connected, which organisation, and whether a cluster has already been provisioned."""
    return {
        "connected": credentials_saved(),
        "org": str(config.setting(ORG_SETTING) or ""),
        "cluster_ready": bool(config.setting(CLUSTER_NAME_SETTING)),
    }


def forget_account() -> None:
    config.save_settings({CLIENT_ID_SETTING: "", CLIENT_SECRET_SETTING: "",
                          ACCESS_TOKEN_SETTING: "", EXPIRES_AT_SETTING: 0, ORG_SETTING: ""})


# --- the OAuth2 client-credentials exchange (no browser: the customer already has the credentials) -

def _json_body(answer: httpx.Response) -> dict:
    try:
        body = answer.json()
    except ValueError:
        return {}
    return body if isinstance(body, dict) else {}


def _request_token(client_id: str, client_secret: str) -> dict:
    try:
        answer = httpx.post(TOKEN_URL, auth=(client_id, client_secret),
                            data={"grant_type": "client_credentials"},
                            headers={"Accept": "application/json"}, timeout=30)
    except httpx.HTTPError as exc:
        raise ValueError(f"MongoDB Atlas could not be reached: {exc}") from exc
    body = _json_body(answer)
    if answer.status_code >= 400 or not body.get("access_token"):
        raise ValueError(str(body.get("error_description") or body.get("error")
                             or f"Atlas rejected that Service Account (HTTP {answer.status_code})."))
    return body


def _token() -> str:
    """The access token to use right now, silently refreshed if it has lapsed. Service Account
    tokens carry no separate refresh token - a lapsed one is just asked for again the same way."""
    access = str(config.setting(ACCESS_TOKEN_SETTING) or "")
    expires_at = float(config.setting(EXPIRES_AT_SETTING) or 0)
    if access and time.time() < expires_at:
        return access
    client_id, client_secret = str(config.setting(CLIENT_ID_SETTING) or ""), str(config.setting(CLIENT_SECRET_SETTING) or "")
    if not client_id or not client_secret:
        raise ValueError("No MongoDB Atlas Service Account is connected yet.")
    body = _request_token(client_id, client_secret)
    expires_in = int(body.get("expires_in") or 3600)
    config.save_settings({ACCESS_TOKEN_SETTING: str(body["access_token"]),
                          EXPIRES_AT_SETTING: time.time() + expires_in - 60})
    return str(body["access_token"])


def _api(method: str, path: str, json_body: dict | None = None, token: str = "") -> Any:
    answer = httpx.request(method, f"{API_BASE}{path}", json=json_body, timeout=30,
                           headers={"Authorization": f"Bearer {token or _token()}",
                                    "Accept": API_VERSION,
                                    **({"Content-Type": "application/json"} if json_body is not None else {})})
    body = _json_body(answer)
    if answer.status_code >= 400:
        raise ValueError(str(body.get("detail") or body.get("reason")
                             or f"Atlas API refused {method} {path} (HTTP {answer.status_code})."))
    return body if body else (answer.json() if answer.content else {})


def save_account(client_id: str, client_secret: str) -> dict:
    """Saved only after a real token exchange succeeds - the same "tried for real before accepting
    it" rule every other credential in this studio follows (deploy_vars.accept, cli_signin)."""
    client_id, client_secret = str(client_id or "").strip(), str(client_secret or "").strip()
    if not client_id or not client_secret:
        raise ValueError("Both the Client ID and Client Secret are needed.")
    body = _request_token(client_id, client_secret)
    config.save_settings({CLIENT_ID_SETTING: client_id, CLIENT_SECRET_SETTING: client_secret,
                          ACCESS_TOKEN_SETTING: str(body["access_token"]),
                          EXPIRES_AT_SETTING: time.time() + int(body.get("expires_in") or 3600) - 60})
    org = _first_org_name(str(body["access_token"]))
    if org:
        config.save_settings({ORG_SETTING: org})
    return status()


def _first_org_name(token: str) -> str:
    try:
        orgs = _api("GET", "/orgs", token=token).get("results") or []
    except ValueError:
        return ""
    return str(orgs[0].get("name") or "") if orgs else ""


# --- making the one cluster this studio uses -----------------------------------------------------

def _db_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(24))


def _ensure_group(token: str) -> str:
    orgs = _api("GET", "/orgs", token=token).get("results") or []
    if not orgs:
        raise ValueError("This Service Account's organisation has no projects it can see. "
                         "Give it a role with project access in Atlas and try again.")
    org_id = str(orgs[0].get("id") or "")
    groups = _api("GET", f"/groups?orgId={org_id}", token=token).get("results") or []
    named = next((g for g in groups if g.get("name") == GROUP_NAME), None)
    if named:
        return str(named["id"])
    if groups:
        # A Service Account scoped to one existing project (Project Owner there) rather than given
        # organisation-wide "Project Creator" never has the right to create a second project - use
        # the one it can already see instead of failing on a permission most people never grant.
        return str(groups[0]["id"])
    created = _api("POST", "/groups", {"name": GROUP_NAME, "orgId": org_id}, token=token)
    group_id = str(created.get("id") or "")
    if not group_id:
        raise ValueError("Atlas did not return the new project's id.")
    return group_id


def _ensure_cluster(token: str, group_id: str, say, region: str = "") -> str:
    """The name of the cluster to use in this project - not necessarily CLUSTER_NAME: a free-tier
    project allows only one M0 cluster, so an existing one (whatever a person already made by hand)
    is reused rather than failing to create a second one there is no room for."""
    try:
        _api("GET", f"/groups/{group_id}/clusters/{CLUSTER_NAME}", token=token)
        return CLUSTER_NAME
    except ValueError:
        pass
    others = _api("GET", f"/groups/{group_id}/clusters", token=token).get("results") or []
    if others:
        return str(others[0]["name"])
    say(f"Creating the {CLUSTER_NAME} cluster (free tier)…")
    _api("POST", f"/groups/{group_id}/clusters", {
        "name": CLUSTER_NAME, "clusterType": "REPLICASET",
        "providerSettings": {"providerName": "TENANT", "instanceSizeName": "M0", "regionName": region or DEFAULT_REGION},
    }, token=token)
    return CLUSTER_NAME


def _wait_idle(token: str, group_id: str, cluster_name: str, say) -> dict:
    say(f"Waiting for {cluster_name} to come up…")
    for _ in range(60):  # ~5 minutes
        cluster = _api("GET", f"/groups/{group_id}/clusters/{cluster_name}", token=token)
        if cluster.get("stateName") == "IDLE":
            return cluster
        time.sleep(5)
    raise ValueError(f"The {cluster_name} cluster did not finish provisioning in time. "
                     "Check the Atlas UI and try again.")


def _ensure_db_user(token: str, group_id: str, password: str) -> None:
    try:
        _api("GET", f"/groups/{group_id}/databaseUsers/admin/{DB_USERNAME}", token=token)
        return  # already exists - leave its password as whatever it already is
    except ValueError:
        pass
    _api("POST", f"/groups/{group_id}/databaseUsers", {
        "username": DB_USERNAME, "password": password, "databaseName": "admin",
        "roles": [{"roleName": "readWriteAnyDatabase", "databaseName": "admin"}],
    }, token=token)


def _ensure_access_list(token: str, group_id: str) -> None:
    entries = _api("GET", f"/groups/{group_id}/accessList", token=token).get("results") or []
    if any(e.get("cidrBlock") == "0.0.0.0/0" for e in entries):
        return
    # Every MongoDB-stack deployment target (Vercel/Netlify serverless, or a fixed-IP target that
    # has not told Atlas its address yet) needs to reach this cluster; the connection string's own
    # username/password is the real access control, matching the note deploy_vars.py's own comment
    # makes about this exact trade-off for a studio-managed cluster.
    _api("POST", f"/groups/{group_id}/accessList", {
        "accessList": [{"cidrBlock": "0.0.0.0/0", "comment": "AgentForge-managed cluster: open, password-protected"}],
    }, token=token)


def account_facts() -> dict:
    """What the build may ask about: whether an Atlas account is connected, the cluster this studio already
    made, and whether a connection string is already saved. Never the string itself."""
    from . import deploy_vars

    saved = {row["name"] for row in deploy_vars.names()}
    return {"atlas_connected": credentials_saved(),
            "studio_cluster": str(config.setting(CLUSTER_NAME_SETTING) or ""),
            "connection_string_saved": bool(config.setting("deploy_mongodb_uri", "") or "MONGODB_URI" in saved)}


def ensure_cluster(log=None, region: str = "") -> dict:
    """The studio's one Atlas cluster: the existing one, or a freshly provisioned one. Blocking
    (cluster creation takes a few minutes) - called from a background job (routes_deploy.py), the
    same way the Deploy panel already runs anything slow."""
    say = log or (lambda _line: None)
    if not credentials_saved():
        raise ValueError("Connect a MongoDB Atlas Service Account first.")
    if config.setting(CLUSTER_NAME_SETTING):
        return status()  # already provisioned by this flow; the manual box can still override it

    token = _token()
    say("Finding or creating the Atlas project…")
    group_id = _ensure_group(token)
    cluster_name = _ensure_cluster(token, group_id, say, region)
    cluster = _wait_idle(token, group_id, cluster_name, say)
    password = _db_password()
    say("Creating the database user…")
    _ensure_db_user(token, group_id, password)
    say("Opening the cluster to the deployed application…")
    _ensure_access_list(token, group_id)

    srv = str((cluster.get("connectionStrings") or {}).get("standardSrv") or "")
    if not srv:
        raise ValueError("Atlas did not return a connection string for the cluster.")
    # standardSrv is a bare mongodb+srv://<cluster-host> (no path, no query, confirmed live) -
    # credentials and a database name are ours to add, never Atlas's to generate.
    scheme, _, rest = srv.partition("://")
    host = rest.split("/", 1)[0].split("?", 1)[0]
    uri = f"{scheme}://{DB_USERNAME}:{password}@{host}/app?retryWrites=true&w=majority"

    config.save_settings({"deploy_mongodb_uri": uri, GROUP_ID_SETTING: group_id, CLUSTER_NAME_SETTING: cluster_name})
    say("Cluster ready.")
    return status()
