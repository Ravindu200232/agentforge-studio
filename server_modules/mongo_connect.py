"""Connecting a MongoDB Atlas account, and giving the studio a real cluster of its own.

Atlas has a true browser sign-in OAuth2 flow (Atlas App Connections, authorization-code + PKCE,
the same shape as `supabase_connect.py`'s own OAuth dance) - but unlike Supabase's, it is not
self-service: MongoDB issues the `client_id`/`client_secret` only after approving an application as
a design partner (confirmed live against
https://www.mongodb.com/docs/atlas/app-connections/partner-integration-guide/ - its own
"Prerequisites & Eligibility" section says so explicitly). Until that approval exists, this studio
cannot offer a sign-in with an OAuth app of its own for Atlas.

What it can offer is MongoDB's own: the Atlas CLI's `atlas auth login` signs a person in through the
browser and a one-time code, with MongoDB's OAuth app, and nothing for the person to register or
paste. That is the way in for a non-technical person (`cli_signin.py`, the "atlas" provider, run in a
pseudo-terminal because its login opens with a menu). Once the CLI is signed in, the cluster is made
with its commands (`_ensure_cluster_cli`), the CLI keeping the credential as it does for every
command line tool in this studio.

Still there for automation, and for anyone who has one: a Service Account - Atlas's own recommended
replacement for a bare API key pair, and still real OAuth2 underneath (`POST
https://cloud.mongodb.com/api/oauth/token`, `grant_type=client_credentials`, confirmed live against
MongoDB's docs). The customer creates one once, in the Atlas UI (Organization Access Manager ->
Service Accounts, any role that can manage projects and clusters), and pastes its Client ID and
Secret here; the exchange itself is a standard, verifiable OAuth2 grant rather than a bespoke token
format. When both exist, the Service Account is used.

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

import json
import secrets
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import urlsplit

import httpx

from . import cli_signin, config

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
LEGACY_DB_USERNAME = "agentforge_app"     # the one database user every studio used to share (see `db_username`)
DB_USER_SETTING = "mongodb_db_user"
DEFAULT_REGION = "US_EAST_1"

GROUP_ID_SETTING = "mongodb_atlas_group_id"
CLUSTER_NAME_SETTING = "mongodb_atlas_cluster_name"


def credentials_saved() -> bool:
    return bool(config.setting(CLIENT_ID_SETTING) and config.setting(CLIENT_SECRET_SETTING))


def cli_account() -> dict:
    """Who the Atlas CLI is signed in as ({} when it is not installed or is signed out). Asked of the CLI itself,
    and remembered for a few seconds by `cli_signin`."""
    row = cli_signin.SIGNINS.available(only="atlas").get("atlas") or {}
    return dict(row.get("identity") or {}) if row.get("signed_in") else {}


def status(accounts: bool = False) -> dict:
    """What the studio may show: never the credentials or tokens, only that an account is
    connected (and how), which organisation, and whether a cluster has already been provisioned.
    With `accounts`, also every account signed in through the Atlas CLI (asking the CLI about each)."""
    service_account = credentials_saved()
    cli = {} if service_account else cli_account()
    answer = {
        "connected": service_account or bool(cli),
        "via": "service_account" if service_account else "cli" if cli else "",
        "account": str(cli.get("account") or ""),
        "org": str(config.setting(ORG_SETTING) or ""),
        "cluster_ready": bool(config.setting(CLUSTER_NAME_SETTING)),
        "cluster": str(config.setting(CLUSTER_NAME_SETTING) or ""),
    }
    if accounts:
        answer["accounts"] = [] if service_account else cli_accounts()
    return answer


def db_username() -> str:
    """The database user this studio connects as, one for each installation of it.

    It used to be one name, `agentforge_app`, for every studio that used the cluster, and whoever provisioned last gave it a new
    password: the connection string every other studio (another PC, the desktop app, a deployed application) had saved then
    stopped being accepted ("refused the username or password"), again and again. Each installation now makes a user of its own
    the first time it needs one, so setting up one never changes what another is signed in with."""
    saved = str(config.setting(DB_USER_SETTING) or "").strip()
    if saved:
        return saved
    name = f"agentforge_{secrets.token_hex(4)}"
    config.save_settings({DB_USER_SETTING: name})
    return name


# --- more than one account (each is a profile of the Atlas CLI) ---------------------------------------
#
# Signing in through the CLI as another account gives it a profile of its own (cli_signin `add`), so the first stays
# signed in. One profile is the active one: every cluster command names it, and the studio's cluster record (the
# project, the cluster and the connection string made for it) belongs to it, so switching puts the other account's
# record in its place instead of leaving a string for a cluster the new account cannot reach.

PROFILE_SETTING = cli_signin.ATLAS_PROFILE_SETTING
CLUSTERS_SETTING = "mongodb_clusters_credentials"  # "credentials" in the name keeps it out of GET /settings
_ACCOUNTS_TTL = 20
_seen_accounts: list = [0.0, []]


def active_profile() -> str:
    return str(config.setting(PROFILE_SETTING) or "")


def cli_accounts(fresh: bool = False) -> list[dict]:
    """[{"id": profile, "label": the account's name, "active": bool}] for every profile signed in, the active first."""
    now = time.time()
    if not fresh and now - _seen_accounts[0] < _ACCOUNTS_TTL:
        return [dict(row) for row in _seen_accounts[1]]
    tool = cli_signin._where("atlas")  # noqa: SLF001
    rows: list[dict] = []
    if tool:
        names = cli_signin.atlas_profiles(tool)
        active = active_profile() or "default"
        with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
            for name, who in zip(names, pool.map(lambda n: cli_signin.atlas_identity(tool, n), names)):
                if who:
                    rows.append({"id": name, "label": who["account"], "active": name == active})
        rows.sort(key=lambda row: not row["active"])
    _seen_accounts[0], _seen_accounts[1] = now, rows
    return [dict(row) for row in rows]


def _forget_seen() -> None:
    _seen_accounts[0] = 0.0
    cli_signin.SIGNINS._seen.pop("atlas", None)  # noqa: SLF001 - who is signed in is asked again


def _put_cluster_aside(profile: str) -> dict:
    """Take the cluster record made for the account in use out of the settings the deployments read."""
    kept = dict(config.setting(CLUSTERS_SETTING) or {})
    updates: dict[str, Any] = {}
    if config.setting(CLUSTER_NAME_SETTING):
        kept[profile or "default"] = {"group_id": str(config.setting(GROUP_ID_SETTING) or ""),
                                      "cluster_name": str(config.setting(CLUSTER_NAME_SETTING) or ""),
                                      "uri": str(config.setting("deploy_mongodb_uri", "") or "")}
        # Only a string this module made goes with its account; one typed in by hand stays whoever signs in.
        updates["deploy_mongodb_uri"] = ""
    updates.update({GROUP_ID_SETTING: "", CLUSTER_NAME_SETTING: ""})
    config.save_settings({**updates, CLUSTERS_SETTING: kept})
    return kept


def switch_account(profile: str) -> dict:
    """Use another account signed in through the Atlas CLI ("" or "default" is the CLI's own default profile)."""
    profile = "" if str(profile or "") == "default" else str(profile or "")
    if profile == active_profile():
        _forget_seen()
        return status(accounts=True)
    kept = _put_cluster_aside(active_profile())
    restore = kept.pop(profile or "default", None)
    updates: dict[str, Any] = {PROFILE_SETTING: profile, CLUSTERS_SETTING: kept}
    if isinstance(restore, dict):
        updates.update({GROUP_ID_SETTING: restore.get("group_id", ""), CLUSTER_NAME_SETTING: restore.get("cluster_name", ""),
                        "deploy_mongodb_uri": restore.get("uri", "")})
    config.save_settings(updates)
    _forget_seen()
    return status(accounts=True)


def remove_account(profile: str) -> dict:
    """Sign one account out of the Atlas CLI. Nothing is deleted in Atlas, and its cluster stays there."""
    profile = "" if str(profile or "") == "default" else str(profile or "")
    tool = cli_signin._where("atlas")  # noqa: SLF001
    if not tool:
        raise ValueError("The MongoDB Atlas command line tool is not installed on this computer.")
    done = cli_signin._run([tool, "auth", "logout", "--force", *cli_signin.atlas_profile_args(profile)], timeout=30)  # noqa: SLF001
    if done.returncode != 0:
        raise ValueError(((done.stderr or done.stdout or "").strip().removeprefix("Error:").strip()[:300])
                         or "The Atlas CLI could not sign that account out.")
    if profile == active_profile():
        _put_cluster_aside(profile)          # what was made for it is no longer what deployments use ...
    kept = dict(config.setting(CLUSTERS_SETTING) or {})
    kept.pop(profile or "default", None)     # ... and is forgotten here; the next account picked starts from its own
    config.save_settings({CLUSTERS_SETTING: kept})
    _forget_seen()
    return status(accounts=True)


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


def _ensure_group(token: str, exact: bool = False) -> str:
    """The project to use. `exact`: only the studio's own, made if it is not there, never one that is someone else's."""
    orgs = _api("GET", "/orgs", token=token).get("results") or []
    if not orgs:
        raise ValueError("This Service Account's organisation has no projects it can see. "
                         "Give it a role with project access in Atlas and try again.")
    org_id = str(orgs[0].get("id") or "")
    groups = _api("GET", f"/groups?orgId={org_id}", token=token).get("results") or []
    named = next((g for g in groups if g.get("name") == GROUP_NAME), None)
    if named:
        return str(named["id"])
    if groups and not exact:
        # A Service Account scoped to one existing project (Project Owner there) rather than given
        # organisation-wide "Project Creator" never has the right to create a second project - use
        # the one it can already see instead of failing on a permission most people never grant.
        return str(groups[0]["id"])
    created = _api("POST", "/groups", {"name": GROUP_NAME, "orgId": org_id}, token=token)
    group_id = str(created.get("id") or "")
    if not group_id:
        raise ValueError("Atlas did not return the new project's id.")
    return group_id


def _ensure_cluster(token: str, group_id: str, say, region: str = "", exact: bool = False) -> str:
    """The name of the cluster to use in this project - not necessarily CLUSTER_NAME: a free-tier
    project allows only one M0 cluster, so an existing one (whatever a person already made by hand)
    is reused rather than failing to create a second one there is no room for. `exact`: only CLUSTER_NAME,
    made if it is not there (the person asked for a new cluster; the ones they have are chosen from a list)."""
    try:
        _api("GET", f"/groups/{group_id}/clusters/{CLUSTER_NAME}", token=token)
        return CLUSTER_NAME
    except ValueError:
        pass
    others = [] if exact else _api("GET", f"/groups/{group_id}/clusters", token=token).get("results") or []
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
        _api("GET", f"/groups/{group_id}/databaseUsers/admin/{db_username()}", token=token)
    except ValueError:
        _api("POST", f"/groups/{group_id}/databaseUsers", {
            "username": db_username(), "password": password, "databaseName": "admin",
            "roles": [{"roleName": "readWriteAnyDatabase", "databaseName": "admin"}],
        }, token=token)
        return
    # It is already there (an earlier attempt, or the same cluster chosen again): the connection string needs a
    # password that is known, so set one rather than keep a string whose password is not the user's.
    _api("PATCH", f"/groups/{group_id}/databaseUsers/admin/{db_username()}", {"password": password}, token=token)


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
    return {"atlas_connected": credentials_saved() or bool(cli_account()),
            "studio_cluster": str(config.setting(CLUSTER_NAME_SETTING) or ""),
            "connection_string_saved": bool(config.setting("deploy_mongodb_uri", "") or "MONGODB_URI" in saved)}


_provision_lock = threading.Lock()


def ensure_for_project(project: str, log=None) -> dict:
    """The database a MongoDB-stack build or deployment runs on, made without asking anyone.

    The customer's connected cluster gives every project databases of its own (`deploy_vars.build_databases`), so when a
    connection string is saved there is nothing to make. When none is saved but an Atlas account is signed in, the cluster
    (and its database user and access list) is made now and the connection string it gives is saved where every command, the
    preview and the deployment read it - the way a Supabase project is made for a project the first time it builds. With
    neither, nothing is made and the caller says so: the customer connects Atlas in Settings, never in a question.

    Blocking (a new cluster takes a few minutes) and never raises: {"status": "ready" | "created" | "not_connected" | "failed",
    "database": the project's database name, "reason": why it failed}."""
    say = log or (lambda _line: None)
    from . import deploy_vars

    created = False
    with _provision_lock:
        if not str(config.setting("deploy_mongodb_uri", "") or ""):
            if not credentials_saved() and not cli_account():
                return {"status": "not_connected", "database": "", "reason": ""}
            try:
                group, name = str(config.setting(GROUP_ID_SETTING) or ""), str(config.setting(CLUSTER_NAME_SETTING) or "")
                if group and name:
                    use_cluster(group, name, log=say)       # the cluster is known, only its connection string is gone
                else:
                    ensure_cluster(log=say)
                created = True
            except Exception as exc:  # noqa: BLE001 - a cluster that cannot be made is a line in the chat, never a failed build
                return {"status": "failed", "database": "", "reason": str(exc)[:300]}
            if not str(config.setting("deploy_mongodb_uri", "") or ""):
                return {"status": "failed", "database": "", "reason": "Atlas did not give a connection string for the cluster."}
    app, _tests = deploy_vars.build_databases(project)
    return {"status": "created" if created else "ready", "database": urlsplit(app).path.strip("/"), "reason": ""}


def can_repair(uri: str = "") -> bool:
    """Whether a connection string that Atlas refuses can be replaced by the studio: it made the string itself (its database user
    is an `agentforge_` one, not a person's own), it knows the cluster, and an Atlas account is signed in to make a new user with."""
    uri = str(uri or "").strip() or str(config.setting("deploy_mongodb_uri", "") or "")
    user = urlsplit(uri).username or ""
    saved = str(config.setting("deploy_mongodb_uri", "") or "")
    return bool(user.startswith("agentforge_") and (not saved or urlsplit(saved).username == user)
                and config.setting(GROUP_ID_SETTING) and config.setting(CLUSTER_NAME_SETTING)
                and (credentials_saved() or cli_account()))


def repair_connection(log=None) -> dict:
    """The saved connection string's password is refused: give this installation a database user of its own on the cluster it
    already uses and save the new string. What other computers, the desktop app or a deployed application hold is not touched
    (their user and its password stay as they are); the studio no longer sets a shared user's password again."""
    say = log or (lambda _line: None)
    if not can_repair():
        raise ValueError("This connection cannot be fixed from here: it was not made by AgentForge, or no Atlas account is signed in. "
                         "Sign in to MongoDB Atlas below and choose the cluster again, or paste a connection string that works.")
    with _provision_lock:
        say("Atlas refused the saved database password: making this computer a database user of its own…")
        return use_cluster(str(config.setting(GROUP_ID_SETTING) or ""), str(config.setting(CLUSTER_NAME_SETTING) or ""), log=say)


def _refuse_paused(cluster: dict, name: str) -> None:
    if cluster.get("paused"):
        raise ValueError(f"The {name} cluster is paused. Resume it in Atlas, then choose it again.")


def _finish_cluster_api(token: str, group_id: str, cluster_name: str, say) -> dict:
    """Everything after the cluster is known, with a Service Account: wait for it, a database user whose password is
    set here, an open access list, and the connection string kept."""
    cluster = _wait_idle(token, group_id, cluster_name, say)
    _refuse_paused(cluster, cluster_name)
    password = _db_password()
    say("Creating the database user…")
    _ensure_db_user(token, group_id, password)
    say("Opening the cluster to the deployed application…")
    _ensure_access_list(token, group_id)
    return _keep_cluster(cluster, group_id, cluster_name, password, say)


def ensure_cluster(log=None, region: str = "", create: bool = False) -> dict:
    """The studio's one Atlas cluster: the existing one, or a freshly provisioned one. Blocking
    (cluster creation takes a few minutes) - called from a background job (routes_deploy.py), the
    same way the Deploy panel already runs anything slow. `create`: make the studio's own cluster even when one is
    already in use (what "create a new cluster" asks for); the ones a person has are chosen with `use_cluster`."""
    say = log or (lambda _line: None)
    if not credentials_saved() and not cli_account():
        raise ValueError("Sign in to MongoDB Atlas first.")
    if config.setting(CLUSTER_NAME_SETTING) and not create:
        return status()  # already provisioned by this flow; the manual box can still override it
    if not credentials_saved():
        return _ensure_cluster_cli(say, region, exact=create)

    token = _token()
    say("Finding or creating the Atlas project…")
    group_id = _ensure_group(token, exact=create) if create else _ensure_group(token)
    cluster_name = (_ensure_cluster(token, group_id, say, region, exact=True) if create
                    else _ensure_cluster(token, group_id, say, region))
    return _finish_cluster_api(token, group_id, cluster_name, say)


# --- choosing one of the clusters the account already has ----------------------------------------------

def _cluster_row(group_id: str, project: str, cluster: dict) -> dict:
    """One cluster as the picker shows it: the project it is in, its state, size and region. The Atlas API and the CLI
    word the size and region differently across versions, so both shapes are read."""
    provider = cluster.get("providerSettings") if isinstance(cluster.get("providerSettings"), dict) else {}
    specs = cluster.get("replicationSpecs") if isinstance(cluster.get("replicationSpecs"), list) else []
    regions = (specs[0].get("regionConfigs") if specs and isinstance(specs[0], dict) else None) or []
    first = regions[0] if regions and isinstance(regions[0], dict) else {}
    elect = first.get("electableSpecs") if isinstance(first.get("electableSpecs"), dict) else {}
    return {"group_id": group_id, "project": project, "name": str(cluster.get("name") or ""),
            "state": "PAUSED" if cluster.get("paused") else str(cluster.get("stateName") or ""),
            "tier": str(provider.get("instanceSizeName") or elect.get("instanceSize") or ""),
            "region": str(provider.get("regionName") or first.get("regionName") or "")}


def _clusters_cli() -> list[dict]:
    projects: list[tuple[str, str]] = []
    for org in _rows(_atlas(["organizations", "list"])):
        for project in _rows(_atlas(["projects", "list", "--orgId", str(org.get("id") or "")])):
            projects.append((str(project.get("id") or ""), str(project.get("name") or "")))

    def of(item: tuple[str, str]) -> list[dict]:
        group_id, name = item
        try:
            found = _rows(_atlas(["clusters", "list", "--projectId", group_id]))
        except ValueError:
            return []        # a project this account may not look inside has nothing to offer
        return [_cluster_row(group_id, name, cluster) for cluster in found]

    if not projects:
        return []
    with ThreadPoolExecutor(max_workers=min(6, len(projects))) as pool:
        return [row for rows in pool.map(of, projects) for row in rows]


def _clusters_api() -> list[dict]:
    token = _token()
    rows: list[dict] = []
    for org in _api("GET", "/orgs", token=token).get("results") or []:
        for group in _api("GET", f"/groups?orgId={org.get('id')}", token=token).get("results") or []:
            try:
                found = _api("GET", f"/groups/{group['id']}/clusters", token=token).get("results") or []
            except ValueError:
                continue
            rows += [_cluster_row(str(group["id"]), str(group.get("name") or ""), c) for c in found if isinstance(c, dict)]
    return rows


def list_clusters() -> dict:
    """Every cluster the account in use can see, project by project, and which one this studio uses now.
    `missing` says the cluster the studio has on record is no longer among them (deleted, or another account's)."""
    if not credentials_saved() and not cli_account():
        raise ValueError("Sign in to MongoDB Atlas first.")
    rows = [row for row in (_clusters_api() if credentials_saved() else _clusters_cli()) if row["name"]]
    group, name = str(config.setting(GROUP_ID_SETTING) or ""), str(config.setting(CLUSTER_NAME_SETTING) or "")
    for row in rows:
        row["selected"] = bool(name) and row["name"] == name and row["group_id"] == group
    rows.sort(key=lambda row: (not row["selected"], row["project"].lower(), row["name"].lower()))
    return {"clusters": rows, "selected": {"group_id": group, "name": name},
            "missing": bool(name) and not any(row["selected"] for row in rows)}


def use_cluster(group_id: str, cluster_name: str, log=None) -> dict:
    """Use a cluster the account already has: the database user and open access list this studio needs are added to
    its project, and the connection string for it replaces the one saved."""
    say = log or (lambda _line: None)
    group_id, cluster_name = str(group_id or "").strip(), str(cluster_name or "").strip()
    if not group_id or not cluster_name:
        raise ValueError("Say which cluster to use.")
    if not credentials_saved() and not cli_account():
        raise ValueError("Sign in to MongoDB Atlas first.")
    if not credentials_saved():
        return _finish_cluster_cli(say, group_id, cluster_name)
    return _finish_cluster_api(_token(), group_id, cluster_name, say)


def _keep_cluster(cluster: dict, group_id: str, cluster_name: str, password: str, say) -> dict:
    """Write the connection string for `cluster` where every deployment reads it, and remember which cluster it is."""
    srv = str((cluster.get("connectionStrings") or {}).get("standardSrv") or "")
    if not srv:
        raise ValueError("Atlas did not return a connection string for the cluster.")
    # standardSrv is a bare mongodb+srv://<cluster-host> (no path, no query, confirmed live) -
    # credentials are ours to add, never Atlas's to generate. No database is named: every project gets databases of its own
    # on the cluster, named after the project (`deploy_vars.build_databases`), so two projects never share one.
    scheme, _, rest = srv.partition("://")
    host = rest.split("/", 1)[0].split("?", 1)[0]
    uri = f"{scheme}://{db_username()}:{password}@{host}/?retryWrites=true&w=majority"

    config.save_settings({"deploy_mongodb_uri": uri, GROUP_ID_SETTING: group_id, CLUSTER_NAME_SETTING: cluster_name})
    _wait_until_accepted(uri, say)
    say("Cluster ready.")
    return status()


def _wait_until_accepted(uri: str, say, seconds: int = 75) -> dict:
    """A database user Atlas has only just made is refused for a few seconds, whatever its password: the same string that is
    right is answered with "refused the username or password" until Atlas has applied it. The connection is called ready once it
    is accepted (or, if it is not within `seconds`, the way it is: the person is told by the next check, not by silence)."""
    from . import mongo_check

    deadline = time.time() + seconds
    told = False
    while True:
        result = mongo_check.check(uri)
        if result.get("stage") != "auth" or time.time() >= deadline:
            return result
        if not told:
            say("Waiting for Atlas to start accepting the new database user…")
            told = True
        time.sleep(5)


# --- the same cluster, made with the Atlas CLI the person signed in with -----------------------------

def _atlas(args: list[str], timeout: int = 90) -> Any:
    """One Atlas CLI command as the account in use, its JSON answer parsed. A failure is the CLI's own message."""
    tool = cli_signin._where("atlas")  # noqa: SLF001 - the one finder every tool here shares
    if not tool:
        raise ValueError("The MongoDB Atlas command line tool is not installed on this computer.")
    done = cli_signin._run([tool, *args, *cli_signin.atlas_profile_args(), "-o", "json"], timeout=timeout)  # noqa: SLF001
    text = (done.stdout or "").strip()
    if done.returncode != 0:
        said = (done.stderr or "").strip() or text
        raise ValueError(said.removeprefix("Error:").strip()[:300] or f"atlas {args[0]} failed.")
    if not text:
        return {}
    try:
        return json.loads(text)
    except ValueError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        if start < 0:
            raise ValueError(f"atlas {args[0]} answered with something that is not JSON.") from None
        return json.loads(text[start:])


def _rows(body: Any) -> list[dict]:
    """The list in a CLI answer, which is `{"results": [...]}` for a list command."""
    rows = body.get("results") if isinstance(body, dict) else body
    return [row for row in rows or [] if isinstance(row, dict)]


def _ensure_cluster_cli(say, region: str = "", exact: bool = False) -> dict:
    """What `ensure_cluster` does with a Service Account, with the commands of the CLI the person signed in with: the
    project, one free M0 cluster, a database user whose password is set here, and an open access list. `exact`: only
    the studio's own project and cluster, made if they are not there, never one that is someone else's."""
    say("Finding or creating the Atlas project…")
    orgs = _rows(_atlas(["organizations", "list"]))
    if not orgs:
        raise ValueError("This Atlas account has no organisation to make a project in.")
    org_id = str(orgs[0].get("id") or "")
    projects = _rows(_atlas(["projects", "list", "--orgId", org_id]))
    named = next((p for p in projects if p.get("name") == GROUP_NAME), None) \
        or (projects[0] if projects and not exact else None)
    if named:
        group_id = str(named.get("id") or "")
    else:
        group_id = str(_atlas(["projects", "create", GROUP_NAME, "--orgId", org_id]).get("id") or "")
    if not group_id:
        raise ValueError("Atlas did not return the project's id.")

    clusters = _rows(_atlas(["clusters", "list", "--projectId", group_id]))
    # A free-tier project allows one M0 cluster: an existing one is used rather than failing to make a second.
    cluster_name = next((c["name"] for c in clusters if c.get("name") == CLUSTER_NAME), "") \
        or (str(clusters[0].get("name") or "") if clusters and not exact else "")
    if not cluster_name:
        say(f"Creating the {CLUSTER_NAME} cluster (free tier)…")
        _atlas(["clusters", "create", CLUSTER_NAME, "--projectId", group_id, "--provider", "AWS",
                "--region", region or DEFAULT_REGION, "--tier", "M0"], timeout=180)
        cluster_name = CLUSTER_NAME
    return _finish_cluster_cli(say, group_id, cluster_name)


def _finish_cluster_cli(say, group_id: str, cluster_name: str) -> dict:
    """Everything after the cluster is known, with the Atlas CLI: wait for it, a database user whose password is set
    here, an open access list, and the connection string kept."""
    say(f"Waiting for {cluster_name} to come up…")
    cluster: dict = {}
    for _ in range(60):  # ~5 minutes
        cluster = _atlas(["clusters", "describe", cluster_name, "--projectId", group_id])
        if cluster.get("stateName") == "IDLE":
            break
        time.sleep(5)
    else:
        raise ValueError(f"The {cluster_name} cluster did not finish provisioning in time. "
                         "Check the Atlas UI and try again.")
    _refuse_paused(cluster, cluster_name)

    say("Creating the database user…")
    password = _db_password()
    try:
        _atlas(["dbusers", "describe", db_username(), "--projectId", group_id])
    except ValueError:
        _atlas(["dbusers", "create", "readWriteAnyDatabase", "--username", db_username(), "--password", password,
                "--projectId", group_id])
    else:
        # It is already there (an earlier attempt that did not finish): the connection string needs a password
        # that is known, so set one rather than guess.
        _atlas(["dbusers", "update", db_username(), "--password", password, "--projectId", group_id])

    say("Opening the cluster to the deployed application…")
    entries = _rows(_atlas(["accessLists", "list", "--projectId", group_id]))
    if not any(e.get("cidrBlock") == "0.0.0.0/0" for e in entries):
        # Every MongoDB-stack deployment target needs to reach this cluster; the connection string's own
        # username and password are the real access control (see `_ensure_access_list`).
        _atlas(["accessLists", "create", "0.0.0.0/0", "--type", "cidrBlock", "--projectId", group_id,
                "--comment", "AgentForge-managed cluster: open, password-protected"])
    return _keep_cluster(cluster, group_id, cluster_name, password, say)
