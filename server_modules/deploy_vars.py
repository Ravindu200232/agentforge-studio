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
from typing import Any
from urllib.parse import urlparse

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
    return [*found, database] if database else found


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


def environment() -> dict[str, str]:
    """What a deployment run's commands are given, beyond its project's own Supabase connection
    (see `supabase_connect.env_for`, merged in separately since it is per-project, not a studio-wide
    setting): every variable the customer saved here by name, overriding that connection's own values
    if they chose to point production at a different Supabase project, plus the saved production
    MongoDB connection string (`deploy_mongodb_uri`), when this project uses one."""
    env = {str(name): str(value) for name, value in (config.setting("deploy_env", {}) or {}).items()}
    database = str(config.setting("deploy_mongodb_uri", "") or "")
    if database:
        env.setdefault("MONGODB_URI", database)
    return env
