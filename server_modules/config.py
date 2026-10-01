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
    # The multi-level control "agent_think" alone can't express: "" (unset)
    # means a settings.json saved before this existed, so agent_think's own
    # boolean still decides — see thinking() below. Once set, it is the one
    # source of truth and agent_think is kept only for older readers.
    "thinking_level": "",
    "mongodb_uri": "",
    # Every other value the customer saved for a deployment run, by name (see deploy_vars.py). A
    # generated app's own Supabase project is a separate, per-project record (supabase_connect.py),
    # not a studio-wide setting like this.
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
    # The one Supabase account this studio is connected as (server_modules/supabase_connect.py):
    "supabase_client_id": "",
    "supabase_client_secret": "",
    "supabase_oauth_access_token": "",
    "supabase_oauth_refresh_token": "",
    "supabase_oauth_expires_at": 0,
    "supabase_org": "",
    "aws_start_url": "",
    "aws_sso_region": "",
    "aws_profile": "",
    "aws_region": "",
    "max_steps": 40,
    "language": "English",
    "stack": "nextjs-supabase",
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


# ``xhigh`` is intentionally a distinct setting rather than an alias for
# ``high``.  Ollama itself only accepts think on/off, but the agent can still
# turn the extra choice into useful work by requiring a separate final
# verification pass (see ProjectSession._system()).
THINKING_LEVELS = ("off", "low", "high", "xhigh")


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
    if "thinking_level" in clean:
        if clean["thinking_level"] not in THINKING_LEVELS:
            raise ValueError(f"thinking_level must be one of {', '.join(THINKING_LEVELS)}")
        # A reader that still only knows the old boolean gets a coherent
        # answer: agent_think was always "does it reason", so both high
        # levels map to true for older readers that only understand a boolean.
        clean["agent_think"] = clean["thinking_level"] in ("high", "xhigh")
    current.update(clean)
    _write(SETTINGS_FILE, current)
    return settings()


def setting(name: str, fallback: Any = None) -> Any:
    return settings().get(name, fallback)


def thinking(saved: dict[str, Any] | None = None) -> str:
    """The multi-level thinking/tool-use setting.

    A settings.json saved before this existed has no `thinking_level` — its
    `agent_think` boolean still decides, so nobody's existing preference
    silently changes on upgrade.
    """
    saved = saved if saved is not None else settings()
    level = str(saved.get("thinking_level") or "").strip().lower()
    if level in THINKING_LEVELS:
        return level
    return "high" if saved.get("agent_think") else "off"


def thinking_enabled(saved: dict[str, Any] | None = None) -> bool:
    """Whether the model reasons before answering (Ollama's native `think`).
    "high" and "xhigh" do — "low" is deliberately reasoning-free, see
    `thinking_encourages_tools()` for what it does get."""
    return thinking(saved) in ("high", "xhigh")


def thinking_encourages_tools(saved: dict[str, Any] | None = None) -> bool:
    """Whether the customer asked for extra encouragement to verify with a
    read tool rather than guess — "low" gets this without paying for
    reasoning tokens; both high levels get reasoning as well."""
    return thinking(saved) in ("low", "high", "xhigh")


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
    "prototype/input", "prototype/assets/uploads",
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
