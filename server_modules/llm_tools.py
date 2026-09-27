"""A minimal, genuinely read-only tool loop for `llm.py`'s focused calls.

`complete()`/`complete_json()`/`complete_html()` are one call, one answer, no
history and no tools — deliberately, so a stage writing many artifacts never
spends its whole output budget on the first one. But the context those calls
need was, until now, read off disk by Python and pasted into the prompt
string, which never shows up in the studio's chat stream the way a real tool
call does. This gives those calls an opt-in, read-only escape hatch: the same
Ollama SDK tool-calling mechanism the main agent already uses
(`src/ollama_terminal/agent.py`), restricted to `list_files`/`read_file`/
`search_text`, with every read reported the same way `StudioTools` already
reports the main agent's reads.

Kept out of `llm.py` itself so its common no-tools path carries no extra
import cost, and so this dispatcher is testable on its own. Never imports
`llm.py` (the caller injects its own bound `chat` function), so there is no
import cycle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ollama_terminal.tools import MAX_OUTPUT, TOOL_SCHEMAS, WorkspaceTools

from . import bus

READ_ONLY_NAMES = ("list_files", "read_file", "search_text")
READ_ONLY_SCHEMAS = [schema for schema in TOOL_SCHEMAS
                     if schema["function"]["name"] in READ_ONLY_NAMES]
MAX_TOOL_ROUNDS = 6

_SENSITIVE_NAMES = {".env", ".env.local", ".env.production"}


def _sensitive(relative: str) -> bool:
    name = Path(relative).name
    return name in _SENSITIVE_NAMES or name.endswith(".secret")


def tag_effort(tools: "ReadOnlyTools | None", think: bool, label: str) -> None:
    """Log this call's effort level — only possible when it was made with a
    project to log against (`tools` is `None` for the many tool-less callers
    that never opted into the read-only tool in the first place)."""
    if tools is None or not tools.project:
        return
    bus.log(tools.project, "INFO",
            f"[effort:{effort_level(think, tools.rounds)}] {label}", agent=tools.role)


def effort_level(think: bool, tool_rounds: int) -> str:
    """A rough, informational four-level read on one call's weight.

    Ollama has no native "effort" concept — only `think` (reasoning on/off).
    This combines it with how many tool round trips the call needed before
    answering: low (a plain completion), medium (looked something up first),
    high (reasoned, at most one lookup), ultra (reasoned and looked up more
    than once — the heaviest calls, e.g. a full SRS document or build plan).
    """
    if think:
        return "ultra" if tool_rounds >= 2 else "high"
    return "medium" if tool_rounds >= 1 else "low"


class ReadOnlyTools:
    """Workspace-rooted, read-only dispatcher.

    `call()` only ever invokes `tool_list_files`/`tool_read_file`/
    `tool_search_text` directly — it never goes through
    `WorkspaceTools.execute()`'s generic name-based dispatch, so there is no
    code path to `write_file`/`replace_text`/`run_command` at all, even if a
    model hallucinates one of those names.
    """

    def __init__(self, workspace: Path, project: str = "", role: str = ""):
        self._tools = WorkspaceTools(workspace, client=None, approve=lambda _question: False)
        self.project = project
        self.role = role or bus.DEVELOPER
        self.rounds = 0

    def call(self, name: str, args: dict[str, Any]) -> str:
        if name not in READ_ONLY_NAMES:
            return f"Tool error: {name} is not offered to this call (read-only)."
        self.rounds += 1
        try:
            result = str(getattr(self._tools, f"tool_{name}")(**args))[:MAX_OUTPUT]
        except Exception as exc:  # noqa: BLE001 - mirrors WorkspaceTools.execute()'s own wrapping
            result = f"Tool error: {exc}"
        if self.project:
            self._announce(name, args, result)
        return result

    def _announce(self, name: str, args: dict[str, Any], result: str) -> None:
        if result.startswith("Tool error"):
            bus.log(self.project, "WARN", result, agent=self.role)
            return
        if name == "read_file":
            try:
                relative = self._tools._path(str(args.get("path") or "")).relative_to(self._tools.root).as_posix()
            except Exception:  # noqa: BLE001 - a bad path is reported by the result itself
                return
            if _sensitive(relative):
                bus.log(self.project, "INFO", f"Read {relative} (content hidden)", agent=self.role)
                return
            bus.file_read(self.project, relative, result, agent=self.role)
            bus.log(self.project, "INFO",
                    f"Read {relative} ({len(result.splitlines())} lines)", agent=self.role)
        elif name == "list_files":
            bus.log(self.project, "INFO", f"Listed {args.get('path') or '.'}", agent=self.role)
        elif name == "search_text":
            bus.log(self.project, "INFO",
                    f'Searched for "{args.get("query", "")}" in {args.get("path", ".")}', agent=self.role)


def run_chat(chat: Callable[..., Any], kwargs: dict[str, Any],
             tools: "ReadOnlyTools | None", max_rounds: int = MAX_TOOL_ROUNDS) -> Any:
    """Drive one `chat(**kwargs)` call through read-only tool round trips.

    Returns the final message. `chat` is the caller's own bound `client().chat`,
    injected so this module never has to import `llm.py`. With `tools=None`
    this is exactly `chat(**kwargs).message` — today's behavior, unchanged.
    """
    if tools is None:
        return chat(**kwargs).message
    kwargs = {**kwargs, "tools": READ_ONLY_SCHEMAS}
    messages = kwargs["messages"]
    for _ in range(max(1, max_rounds)):
        message = chat(**kwargs).message
        calls = message.tool_calls or []
        messages.append(message.model_dump(exclude_none=True))
        if not calls:
            return message
        for call in calls:
            name, args = call.function.name, (call.function.arguments or {})
            messages.append({"role": "tool", "tool_name": name, "content": tools.call(name, args)})
    # Rounds exhausted: force a final answer, with no more reads offered.
    kwargs.pop("tools", None)
    return chat(**kwargs).message
