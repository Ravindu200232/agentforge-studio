"""Try a MongoDB connection string for real: address, network, credentials, ping.

The check runs in Node, because that is what a deployed application uses to connect: the same driver, the same
TLS, the same answers. The string goes in the environment, never on a command line, and nothing is returned that
contains it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from . import config, deploy_vars

SCRIPT = Path(__file__).resolve().parent / "scripts" / "mongo-ping.mjs"
TIMEOUT = 45


def _driver_base() -> str:
    """A folder whose node_modules holds the MongoDB driver: any project that has been built has one."""
    root = config.WORKSPACES
    if root.is_dir():
        for folder in sorted(root.iterdir()):
            if (folder / "node_modules" / "mongodb" / "package.json").is_file():
                return str(folder)
    return ""


def _scrub(text: str, uri: str) -> str:
    """Whatever came back, without the string or its password in it."""
    clean = str(text or "")
    password = (re.match(r"^[a-z+]+://[^:@/]+:([^@/]+)@", uri, re.IGNORECASE) or [None, ""])[1]
    for secret in (uri, password):
        if secret and (secret == uri or len(secret) >= 6):       # a one-letter password would garble every word
            clean = clean.replace(secret, "<hidden>")
    return re.sub(r"//[^/@\s]+:[^@\s]+@", "//<credentials>@", clean)


def check(uri: str = "", allow_local: bool = False) -> dict[str, Any]:
    """The connection string typed in, or the saved one when none is given."""
    uri = str(uri or "").strip() or str(config.setting("deploy_mongodb_uri", "") or "")
    if not uri:
        return {"ok": False, "stage": "empty", "message": "Type or save a connection string first."}
    if not allow_local:
        try:
            deploy_vars.check_database_uri(uri)
        except ValueError as exc:
            return {"ok": False, "stage": "address", "message": str(exc)}
    node = shutil.which("node")
    if not node:
        return {"ok": False, "stage": "tool", "message": "Node.js is not installed on this computer, so the check cannot run."}
    try:
        done = subprocess.run([node, str(SCRIPT)], capture_output=True, text=True, timeout=TIMEOUT, errors="replace",
                              env={**os.environ, "CHECK_URI": uri, "DRIVER_BASE": _driver_base()},
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return {"ok": False, "stage": "timeout", "message": f"The cluster did not answer within {TIMEOUT} seconds."}
    lines = [line for line in (done.stdout or "").splitlines() if line.strip().startswith("{")]
    try:
        result = json.loads(lines[-1])
    except (IndexError, ValueError):
        return {"ok": False, "stage": "tool", "message": "The check did not finish: " + _scrub((done.stderr or "")[-200:], uri)}
    result["message"] = _scrub(result.get("message", ""), uri)
    result["warnings"] = [_scrub(item, uri) for item in result.get("warnings") or []]
    return result
