"""Paths, ports and settings.

Nothing here is a product decision. Every value is either a path derived from
where this file sits, or a setting read from `settings.json` at call time, so a
change to a setting never needs a change to code.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
PROMPTS = ROOT / "prompts"
WORKSPACES = ROOT / "workspaces"
STATE = ROOT / ".agentforge-server"
SETTINGS_FILE = STATE / "settings.json"
PROJECTS_FILE = STATE / "projects.json"

# The studio's next.config.js proxies /__agentforge/api to the first and
# /__agentforge/ws to the second. Both are overridable from the environment so a
# second instance can run beside this one.
API_PORT = int(os.environ.get("AGENTFORGE_API_PORT", "7824"))
WS_PORT = int(os.environ.get("AGENTFORGE_WS_PORT", "7825"))
API_PREFIX = "/__agentforge/api"

# Where the project's own record lives, inside each workspace.
RECORD_DIR = ".agentforge"

DEFAULTS: dict[str, Any] = {
    "ollama_host": os.environ.get("OLLAMA_HOST", "http://localhost:11434"),
    "ollama_api_key": "",
    "cloud": False,
    "model": "",
    "context": 0,
    "local_num_ctx": 0,
    "agent_think": False,
    "mongodb_uri": "",
    # What a deployment run is given (see deploy_vars.py): the production database, and every other value
    # the customer saved for it by name. Kept apart from `mongodb_uri`, which is the studio's own.
    "deploy_mongodb_uri": "",
    "deploy_env": {},
    "deploy_env_secret": {},        # for each name in deploy_env: whether it was asked for as a secret
    "github_token": "",
    "vercel_token": "",
    "netlify_token": "",
    "cloudflare_api_token": "",
    "cloudflare_account_id": "",
    "azure_token": "",
    "azure_credentials": "",
    "azure_account": "",
    "github_login": "",
    "github_client_id": "",
    "aws_start_url": "",
    "aws_sso_region": "",
    "aws_profile": "",
    "aws_region": "",
    "max_steps": 40,
    "language": "English",
    "stack": "nextjs-mongo",
    # The SRS already passes a deterministic schema + approved-plan coverage
    # gate before diagrams. Run one standards audit by default without asking a
    # model to rewrite a very large document in full; callers may opt into
    # additional review-repair rounds in settings.
    "srs_review_max_iterations": 0,
    # A requirements session with a customer is bounded. Without a ceiling the
    # interview follows one thread — payment, then refunds, then the refund
    # email, then who receives it — until nobody remembers what was being built.
    "interview_max_questions": 25,
    # External MCP (Model Context Protocol) servers the agent can also draw
    # tools from, each {"id", "command", "args", "env", "enabled"} — additive
    # to the built-in tool set, never a replacement for it.
    "mcp_servers": [],
}


def _read(path: Path, fallback: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return fallback


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def settings() -> dict[str, Any]:
    """The saved settings, over the defaults."""
    saved = _read(SETTINGS_FILE, {})
    return {**DEFAULTS, **(saved if isinstance(saved, dict) else {})}


def save_settings(patch: dict[str, Any]) -> dict[str, Any]:
    current = _read(SETTINGS_FILE, {})
    if not isinstance(current, dict):
        current = {}
    clean = {k: v for k, v in (patch or {}).items() if k in DEFAULTS or k.endswith("_model")}
    if "local_num_ctx" in clean:
        try:
            clean["context"] = max(0, int(clean["local_num_ctx"] or 0))
            clean["local_num_ctx"] = clean["context"]
        except (TypeError, ValueError):
            raise ValueError("context length must be a number") from None
    current.update(clean)
    _write(SETTINGS_FILE, current)
    return settings()


def setting(name: str, fallback: Any = None) -> Any:
    return settings().get(name, fallback)


def workspace_for(project: str) -> Path:
    """One directory per project, always inside `workspaces/`."""
    safe = "".join(c for c in str(project) if c.isalnum() or c in "-_") or "project"
    path = (WORKSPACES / safe).resolve()
    if not path.is_relative_to(WORKSPACES.resolve()):
        raise ValueError("project name escapes the workspace root")
    return path


def record_dir(project: str) -> Path:
    return workspace_for(project) / RECORD_DIR


# The empty stage-folder skeleton every new project starts with, so a read
# tool can list its way around before any stage has written into it. A
# workspace layout fact, not a setting — kept here for the same reason
# `workspace_for()` and `record_dir()` are.
SCAFFOLD_DIRS = (
    "srs/handoff", "srs/wireframes", "srs/diagrams", "srs/diagram-context",
    "srs/reviews", "srs/wireframe-system",
    "design",
    "prototype/context", "prototype/kit", "prototype/assets/uploads", "prototype/skills",
    "build/guides", "build/plan",
    "qa/guides",
    "deploy/skills", "deploy/runs",
    "changes",
)


def scaffold_workspace(project: str) -> Path:
    """The project's workspace, with its predictable empty stage-folder
    skeleton, so a read tool can find its way around before any stage has run."""
    workspace = workspace_for(project)
    workspace.mkdir(parents=True, exist_ok=True)
    record = workspace / RECORD_DIR
    for relative in SCAFFOLD_DIRS:
        (record / relative).mkdir(parents=True, exist_ok=True)
    return workspace
