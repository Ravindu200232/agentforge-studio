"""What a deployment needs from the customer that is a secret or a value only they know.

A deployment may need an administrator's first password, a mail provider's key, or a production
value the customer wants to override entirely (a different Supabase project than the one the build
already connected to — see `supabase_connect.py` for the one every project gets automatically). None
of these may travel through the chat (it is sent to a model and kept in logs), and none may be typed
into a command the agent shows. So the customer saves them here, in Settings, once; a deployment run
receives them in the environment of its own commands under the names it asked for, and no other run
does.

Values are never returned to the studio: only the names and the last four characters, as for every other
saved credential.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any
from urllib.parse import unquote, urlparse, urlsplit, urlunsplit

from . import config

_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
# Names that would change how the agent's own tools run, not what the deployed application is told.
_RESERVED = {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "HOME", "USERPROFILE", "TEMP", "TMP", "SHELL",
             "NODE_OPTIONS", "NODE_PATH", "PYTHONPATH", "PYTHONHOME", "LD_PRELOAD", "LD_LIBRARY_PATH",
             "NPM_CONFIG_USERCONFIG", "GIT_SSH_COMMAND", "GIT_ASKPASS", "VERCEL_TOKEN", "NETLIFY_AUTH_TOKEN",
             "GH_TOKEN", "GITHUB_TOKEN", "AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
MAX_VARIABLES = 50
MAX_BYTES = 8192
_LOOPBACK = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "host.docker.internal"}


def valid_name(name: str) -> str:
    """The variable's name, or why it cannot be one."""
    name = str(name or "").strip()
    if not _NAME.match(name):
        raise ValueError("a variable name is capital letters, digits and underscores, starting with a letter "
                         "(for example ADMIN_EMAIL)")
    if name in _RESERVED or name.startswith("AGENTFORGE_"):
        raise ValueError(f"{name} is used by the machine itself and cannot be set here")
    return name


def names() -> list[dict[str, Any]]:
    """The saved variables as names and hints. Never the values."""
    saved = config.setting("deploy_env", {}) or {}
    return [{"name": name, "hint": str(value)[-4:] if len(str(value)) > 8 else ""}
            for name, value in sorted(saved.items())]


def save(name: str, value: str, secret: bool = True) -> list[dict[str, Any]]:
    """Save one variable; an empty value removes it. `secret` is whether it was asked for as one."""
    name = valid_name(name)
    value = str(value or "")
    if len(value.encode("utf-8")) > MAX_BYTES:
        raise ValueError(f"a value can be at most {MAX_BYTES} bytes")
    saved = dict(config.setting("deploy_env", {}) or {})
    kinds = dict(config.setting("deploy_env_secret", {}) or {})
    if not value.strip():
        saved.pop(name, None)
        kinds.pop(name, None)
    else:
        if name not in saved and len(saved) >= MAX_VARIABLES:
            raise ValueError(f"at most {MAX_VARIABLES} variables can be saved")
        saved[name], kinds[name] = value, bool(secret)
    config.save_settings({"deploy_env": saved, "deploy_env_secret": kinds})
    return names()


_SECRET_NAME = re.compile(r"PASS|SECRET|TOKEN|KEY|URI|CRED", re.IGNORECASE)


def secret_values() -> list[str]:
    """The saved values that are secrets, for hiding them wherever a tool might print one. A plain value (a name, an
    email) is not hidden: it would garble ordinary words. One saved before the kind was recorded goes by its name."""
    kinds = config.setting("deploy_env_secret", {}) or {}
    found = []
    for name, value in (config.setting("deploy_env", {}) or {}).items():
        secret = kinds.get(name)
        if secret is None:
            secret = bool(_SECRET_NAME.search(str(name)))
        if secret and isinstance(value, str) and len(value) >= 8:
            found.append(value)
    database = config.setting("deploy_mongodb_uri", "") or ""
    if not database:
        return found
    # The databases a build is handed are this string with another name in it, so the password is hidden on its own too.
    password = unquote(urlparse(database).password or "")
    return [*found, database, *(uri for uri in build_databases() if uri), *([password] if len(password) >= 8 else [])]


# What a question may ask the studio to try before it accepts a value. Supabase needs none - the
# connection a build gets is already verified by `supabase_connect.py` fetching real keys, not typed
# in and checked after the fact. A MongoDB connection string is typed in (by hand, or by
# `mongo_connect.py` once an Atlas account is linked), so it is the one value worth trying for real
# before it is kept - a typo or an unreachable cluster is far cheaper to catch here than mid-deploy.
CHECKS: tuple[str, ...] = ("mongodb",)


def accept(question: dict, value: str) -> str:
    """Take the value a question asked for: try it if the question says how, keep it by name. Returns why not, or ''.

    The value goes straight to the saved variables. It is never returned, and the model is told only that it was saved.
    """
    try:
        name = valid_name(question.get("variable", ""))
    except ValueError as exc:
        return str(exc)
    value = str(value or "")
    if not value.strip():
        return "Type a value first."
    if question.get("check") == "mongodb":
        from . import mongo_check

        result = mongo_check.check(value)
        if not result.get("ok"):
            return str(result.get("message") or "That connection string could not be used.")
    try:
        save(name, value, secret=bool(question.get("secret", True)))
    except ValueError as exc:
        return str(exc)
    return ""


def check_database_uri(uri: str, allow_local: bool = False) -> str:
    """The production database connection string, or why it cannot be one (a hosted app cannot reach this computer).

    `allow_local` exists only for a build's own short-lived local test database, never for a saved production value.
    """
    uri = str(uri or "").strip()
    if not uri:
        return ""
    parsed = urlparse(uri)
    if parsed.scheme not in ("mongodb", "mongodb+srv"):
        raise ValueError("a MongoDB connection string starts with mongodb:// or mongodb+srv://")
    if allow_local:
        return uri
    hosts = (parsed.netloc.rsplit("@", 1)[-1]).split(",")
    for host in hosts:
        name = host.strip("[]").rsplit(":", 1)[0].strip("[]").lower() if not host.startswith("[") else host.strip("[]").lower()
        if not name or name in _LOOPBACK or name.endswith((".local", ".localhost")):
            raise ValueError("that address points at this computer: a deployed application cannot reach it. "
                             "Use a database that is reachable from the internet (for example MongoDB Atlas), "
                             "never a local MongoDB.")
    return uri


# --- the database a build runs on ---------------------------------------------------------------------------------------

BUILD_CHECK_SECONDS = 120          # how long "the connected cluster answers" (or does not) is remembered
NOTE_SECONDS = 600                 # how often the customer is told, per project, that it does not
_checked: dict[str, tuple[float, bool, str]] = {}
_noted: dict[str, float] = {}
_check_lock = threading.Lock()


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")[:30]


def with_database(uri: str, database: str) -> str:
    """`uri` pointed at `database` on the same cluster, its credentials and options as they were."""
    parts = urlsplit(uri)
    return urlunsplit((parts.scheme, parts.netloc, "/" + database, parts.query, ""))


def build_databases(project: str = "") -> tuple[str, str]:
    """The connected cluster's databases for a build, (the app's, the tests'), or ("", "") when no cluster is connected.

    They are databases of their own on the cluster the customer connected - `<name>_build`, which the seed fills and the
    preview and the end-to-end tests use, and `<name>_test`, which the unit tests empty between tests (the templates refuse any
    name that does not end in `_test`) - so a build neither needs a MongoDB on this computer nor touches the data of the
    database the deployed application will use. `<name>` is the database the saved string names, else the project's own name."""
    uri = str(config.setting("deploy_mongodb_uri", "") or "")
    if not uri:
        return "", ""
    base = _slug(unquote(urlsplit(uri).path.strip("/")))
    if not base:
        from . import store

        base = _slug((store.get(project) or {}).get("name")) if project else ""
        base = base or _slug(project) or "app"
    return with_database(uri, f"{base}_build"), with_database(uri, f"{base}_test")


def cluster_answers(uri: str) -> tuple[bool, str]:
    """Whether the connected cluster answers right now, and if not what it said (a paused cluster has no address, a wrong
    password is refused). Asked for real - the same driver the app uses - and remembered for a couple of minutes, because a build
    asks on every command."""
    with _check_lock:
        seen = _checked.get(uri)
        if seen and time.time() - seen[0] < BUILD_CHECK_SECONDS:
            return seen[1], seen[2]
        from . import mongo_check

        try:
            result = mongo_check.check(uri)
            answer = (bool(result.get("ok")), str(result.get("message") or ""))
        except Exception as exc:  # noqa: BLE001 - a check that cannot run is not an answer from the cluster either way
            answer = (False, f"it could not be checked ({str(exc)[:120]})")
        _checked[uri] = (time.time(), *answer)
        return answer


def _tell_unreachable(project: str, why: str) -> None:
    """Say, once in a while, that the connected cluster cannot be used and what the build is doing instead."""
    if not project or time.time() - _noted.get(project, 0) < NOTE_SECONDS:
        return
    _noted[project] = time.time()
    from . import bus

    text = (f"The MongoDB cluster you connected could not be reached ({why or 'no answer'}), so this build's database commands "
            "use a MongoDB on this computer (localhost:27017), which may not be running. If the cluster is paused, resume it in "
            "MongoDB Atlas: the next command uses it again.")
    bus.log(project, "WARN", text)
    bus.agent_msg(project, text, title="MongoDB cluster not reachable", kind="narration")


def environment(build: bool = False, project: str = "") -> dict[str, str]:
    """What a deployment run's commands are given, beyond its project's own Supabase connection
    (see `supabase_connect.env_for`, merged in separately since it is per-project, not a studio-wide
    setting): every variable the customer saved here by name, overriding that connection's own values
    if they chose to point production at a different Supabase project, plus the saved production
    MongoDB connection, when this project uses one.

    That connection is the same one the build ran on: the cluster the customer connected (`deploy_mongodb_uri`) with the database
    the build's seed filled (`build_databases`), never the saved string as it stands, so the deployed application finds the data the
    build made, and what looks at the deployed data (the database monitors, the data viewer) looks at the same database.

    `build`: for the commands of a build, and for the preview of what it built, which also get `TEST_MONGODB_URI`: a database
    for the unit tests, which empty it between tests. The cluster is asked first whether it answers - never a MongoDB on this
    computer that may not exist is what they run on. When it does not answer (paused, deleted, no network) the customer is told,
    and the build goes on with the app's own default, a local MongoDB. A deployment is not asked: it is handed the connection and
    says itself what it could not reach. A `MONGODB_URI` or `TEST_MONGODB_URI` the customer saved by name is handed over as it is."""
    env = {str(name): str(value) for name, value in (config.setting("deploy_env", {}) or {}).items()}
    database = str(config.setting("deploy_mongodb_uri", "") or "")
    if not database:
        return env
    if not build:
        env.setdefault("MONGODB_URI", build_databases(project)[0])
        return env
    answers, why = cluster_answers(database)
    if answers:
        app, tests = build_databases(project)
        env.setdefault("MONGODB_URI", app)
        env.setdefault("TEST_MONGODB_URI", tests)
    else:
        _tell_unreachable(project, why)
    return env
