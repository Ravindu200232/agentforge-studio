"""What the agent may do without asking: the permission modes, the way Claude Code has them.

A project is in one mode, picked beside the chat input and beside the first input of a new project:

    auto           the agent edits files and runs its commands on its own; only a risky command (sudo, a download piped into
                   a shell, Invoke-Expression, Start-Process, a credential sent out) is asked about in the chat
    manual         every edit and every command is asked about first
    accept_edits   edits and the usual web-development commands (npm, node, git, next, vercel...) go ahead; any other
                   command is asked about
    bypass         nothing is asked and nothing is refused; it has to be turned on in the mode menu first

Planning is not a mode: a change typed into a project that has a specification is planned first and carried out once the plan
is approved (`changes.py`), whatever the mode. The mode is what the carrying out may do without asking.

A question is a card in the chat stream (`bus.ask_and_wait`, kind "permission") with three answers: allow, allow and do not ask
again this session (for edits, or for that program), and deny (with a note for the agent, if the person wants to give one). The run
holds still until it is answered; Stop ends the wait. A risky command is always asked, and has no "do not ask again".
"""
from __future__ import annotations

import threading
from typing import Any, Callable

from ollama_terminal import tools

from . import bus, config, store

MODES = ("auto", "manual", "accept_edits", "bypass")
DEFAULT_MODE = "auto"                    # what every project did before there were modes: edits and the usual commands on its own
LABELS = {"auto": "Auto", "manual": "Manual", "accept_edits": "Accept edits", "bypass": "Bypass permissions"}

_lock = threading.Lock()
_grants: dict[str, set[str]] = {}        # project -> what the person said not to ask about again, until the mode changes


def bypass_enabled() -> bool:
    return bool(config.setting("bypass_permissions", False))


def default_mode() -> str:
    mode = str(config.setting("permission_mode", DEFAULT_MODE) or DEFAULT_MODE)
    return mode if mode in MODES and (mode != "bypass" or bypass_enabled()) else DEFAULT_MODE


def mode_of(project: str) -> str:
    """The mode a project is in: the one picked for it, else the default."""
    mode = str((store.get(project) or {}).get("permission_mode") or "")
    if mode in MODES:
        return mode if mode != "bypass" or bypass_enabled() else DEFAULT_MODE
    return default_mode()


def set_mode(project: str, mode: str) -> str:
    """Put a project in `mode`. What was allowed for the rest of the session in the old mode is asked about again."""
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        raise ValueError(f"the mode must be one of: {', '.join(MODES)}")
    if mode == "bypass" and not bypass_enabled():
        raise ValueError("turn on bypass permissions first: it lets the agent run any command and change any file without asking")
    store.update(project, permission_mode=mode)
    with _lock:
        _grants.pop(project, None)
    return mode


def set_default(mode: str) -> str:
    """The mode a new project starts in (what is picked beside the first input)."""
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        raise ValueError(f"the mode must be one of: {', '.join(MODES)}")
    if mode == "bypass" and not bypass_enabled():
        raise ValueError("turn on bypass permissions first")
    config.save_settings({"permission_mode": mode})
    return mode


def start_project(project: str, wanted: str = "") -> str:
    """A new project starts in the mode picked beside the first input (`wanted`), else in the default one."""
    wanted = str(wanted or "").strip().lower()
    mode = wanted if wanted in MODES and (wanted != "bypass" or bypass_enabled()) else default_mode()
    return set_mode(project, mode)


def enable_bypass(on: bool) -> bool:
    """Allow (or stop allowing) the bypass mode. Turning it off puts every project that was in it back to the default mode."""
    config.save_settings({"bypass_permissions": bool(on)})
    if not on:
        for record in store.listing():
            project = str(record.get("name") or "")
            if project and (store.get(project) or {}).get("permission_mode") == "bypass":
                store.update(project, permission_mode=DEFAULT_MODE)
        if config.setting("permission_mode") == "bypass":
            config.save_settings({"permission_mode": DEFAULT_MODE})
    return bypass_enabled()


def status(project: str = "") -> dict[str, Any]:
    return {"mode": mode_of(project) if project else default_mode(), "default": default_mode(),
            "bypass_enabled": bypass_enabled(), "modes": [{"id": m, "label": LABELS[m]} for m in MODES]}


# --- the question ---------------------------------------------------------------------------------------------------------

def _summary(action: dict[str, Any]) -> str:
    return (f"Edit {action.get('file')}" if action.get("kind") == "edit" else f"Run {action.get('command')}")[:300]


def _keys(action: dict[str, Any]) -> set[str]:
    """What an "allow again" would cover: all edits, or each program in the command."""
    if action.get("kind") == "edit":
        return {"edits"}
    programs = tools.command_programs(str(action.get("command") or ""))
    return {f"cmd:{program}" for program in programs} or {"cmd:"}


def needs_asking(mode: str, action: dict[str, Any], granted: set[str]) -> bool:
    """Whether the person is asked about this action in this mode.

    auto           nothing is asked but a risky command (`level` "danger": sudo, a download piped into a shell, Invoke-Expression,
                   Start-Process, a credential file sent out, a drive formatted)
    accept_edits   edits and the usual web-development commands (npm, node, git, next, vercel... - `level` "") go ahead; a
                   command outside them (`level` "unusual") is asked, and so is a risky one
    manual         every edit and every command is asked"""
    if mode == "bypass":
        return False
    level = str(action.get("level") or "")
    danger = level == "danger"
    if action.get("kind") == "edit":
        asked = mode == "manual"
    elif mode == "manual":
        asked = True
    elif mode == "accept_edits":
        asked = bool(level) and not tools.read_only(str(action.get("command") or ""))
    else:                                                                    # auto
        asked = danger
    if asked and not danger and _keys(action) <= granted:
        asked = False
    return asked


def gate_for(project: str, cancelled: Callable[[], bool], role_of: Callable[[], str]) -> Callable[[dict[str, Any]], str]:
    """The `permission` hook of a project's tools (see `tools.WorkspaceTools.permission`)."""
    def check(action: dict[str, Any]) -> str:
        mode = mode_of(project)
        with _lock:
            granted = set(_grants.get(project, ()))
        if not needs_asking(mode, action, granted):
            return ""
        return _ask(project, action, cancelled, role_of())
    return check


def _ask(project: str, action: dict[str, Any], cancelled: Callable[[], bool], role: str) -> str:
    edit = action.get("kind") == "edit"
    danger = action.get("level") == "danger"
    program = str(action.get("program") or "")
    again = ("Yes, and do not ask again for edits in this session" if edit
             else f"Yes, and do not ask again for {program or 'these'} commands in this session")
    reply = bus.ask_and_wait(
        project, "permission", "Edit this file?" if edit else "Run this command?", options=["allow", "always", "deny"],
        agent=role or bus.DEVELOPER, cancelled=cancelled, action=action.get("kind"),
        detail=str(action.get("file") if edit else action.get("command") or "")[:2000], extra_detail=str(action.get("detail") or ""),
        reason=str(action.get("why") or ""), danger=danger, always_label="" if danger else again)
    if reply is None:
        return "Stopped before the person answered."
    verdict, _, note = str(reply).strip().partition(":")
    allowed = verdict in ("allow", "always")
    if verdict == "always" and not danger:
        with _lock:
            _grants.setdefault(project, set()).update(_keys(action))
    bus.agent_msg(project, f"{'Allowed' if allowed else 'Not allowed'} · {_summary(action)}", title="Permission", kind="permission",
                  agent=role or bus.DEVELOPER)
    if allowed:
        return ""
    return (f"The person did not allow this {'edit' if edit else 'command'}."
            + (f" They said: {note.strip()}" if note.strip() else "")
            + " Do not try the same thing again: take another approach, or say what you need and why.")
