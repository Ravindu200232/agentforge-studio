"""A minimal, genuinely read-only tool loop for `llm.py`'s focused calls.

`complete()`/`complete_json()`/`complete_html()` are one call, one answer, no
history and no tools — deliberately, so a stage writing many artifacts never
spends its whole output budget on the first one. But the context those calls
need was, until now, read off disk by Python and pasted into the prompt
string, which never shows up in the studio's chat stream the way a real tool
call does. This gives those calls an opt-in, read-only escape hatch: the same
Ollama SDK tool-calling mechanism the main agent already uses
(`src/ollama_terminal/agent.py`), restricted to `list_files`/`read_file`/
`search_text`/`web_search`/`web_fetch`/`browser_inspect` — nothing that changes
application source or runs a command (browser inspection saves QA evidence) — with every call reported the same way
`StudioTools` already reports the main agent's own.

Kept out of `llm.py` itself so its common no-tools path carries no extra
import cost, and so this dispatcher is testable on its own. Never imports
`llm.py` (the caller injects its own bound `chat` function and client), so
there is no import cycle.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import ollama

from ollama_terminal.tools import MAX_OUTPUT, TOOL_SCHEMAS, WorkspaceTools, describe_call, tools_unsupported

from . import bus

READ_ONLY_NAMES = ("list_files", "read_file", "search_text", "web_search", "web_fetch", "browser_inspect")
READ_ONLY_SCHEMAS = [schema for schema in TOOL_SCHEMAS
                     if schema["function"]["name"] in READ_ONLY_NAMES]
MAX_TOOL_ROUNDS = 6

_SENSITIVE_NAMES = {".env", ".env.local", ".env.production"}

# Models that rejected a tools= call this process, so later calls for the same
# model skip straight to the tools-less path instead of failing again first.
# These calls worked with zero tools before this existed, so the model just
# gets that behavior back rather than losing the whole generation stage.
_UNSUPPORTED_MODELS: set[str] = set()


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
    `tool_search_text`/`tool_web_search`/`tool_web_fetch`/`tool_browser_inspect`
    directly — it never
    goes through `WorkspaceTools.execute()`'s generic name-based dispatch, so
    there is no code path to `write_file`/`replace_text`/`run_command` at
    all, even if a model hallucinates one of those names.
    """

    def __init__(self, workspace: Path, project: str = "", role: str = "", client: Any = None,
                 use_local_web: bool = True, web_host: str = "http://localhost:11434"):
        self._tools = WorkspaceTools(workspace, client, approve=lambda _question: False,
                                     web_host=web_host, use_local_web=use_local_web)
        self.project = project
        self.role = role or bus.DEVELOPER
        self.rounds = 0
        # Focused LLM calls use WorkspaceTools rather than StudioTools, so
        # provide the same managed-preview lookup explicitly.
        self._tools.browser_url = self._browser_url

    def _browser_url(self) -> str:
        if not self.project:
            return ""
        from . import preview_runtime

        state = preview_runtime.status(self.project)
        return str(state.get("url") or "") if state.get("status") in {"starting", "running"} else ""

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
            bus.log(self.project, "WARN", f"{describe_call(name, args)} — {result}", agent=self.role)
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
        elif name == "web_search":
            bus.log(self.project, "INFO", f'Searched the web for "{args.get("query", "")}"', agent=self.role)
        elif name == "web_fetch":
            bus.log(self.project, "INFO", f'Fetched {args.get("url", "")}', agent=self.role)
        elif name == "browser_inspect":
            bus.log(self.project, "INFO",
                    f'Inspected local browser page {args.get("url") or "managed preview"}', agent=self.role)


def _stream_chat(chat: Callable[..., Any], kwargs: dict[str, Any],
                 on_token: Callable[[str], None],
                 on_usage: Callable[[Any], None] | None = None) -> Any:
    """One `chat(**kwargs, stream=True)` call, forwarding each content delta
    to `on_token` as it arrives, returning the same shape a non-streamed call
    returns (one assembled message) so every caller downstream — the tool-call
    loop above, `llm.py`'s own repair loops — reads it identically either way.

    Ollama's streaming chunks carry a delta in `.message.content`, not a
    running total, and `.message.tool_calls` on whichever chunk actually
    carries them (not necessarily the last one) — both are accumulated here.
    """
    content: list[str] = []
    thinking: list[str] = []
    calls: list[Any] = []
    final = None
    for chunk in chat(**{**kwargs, "stream": True}):
        final = chunk
        delta = chunk.message
        if delta.content:
            content.append(delta.content)
            on_token(delta.content)
        if delta.thinking:
            thinking.append(delta.thinking)
        if delta.tool_calls:
            calls.extend(delta.tool_calls)
    if final is not None and on_usage is not None:
        on_usage(final)
    return ollama.Message(role="assistant", content="".join(content),
                          thinking="".join(thinking) or None, tool_calls=calls or None)


def run_chat(chat: Callable[..., Any], kwargs: dict[str, Any],
             tools: "ReadOnlyTools | None", max_rounds: int = MAX_TOOL_ROUNDS,
             on_stream_start: Callable[[], None] | None = None,
             on_stream_token: Callable[[str], None] | None = None,
             on_usage: Callable[[Any], None] | None = None) -> Any:
    """Drive one `chat(**kwargs)` call through read-only tool round trips.

    Returns the final message. `chat` is the caller's own bound `client().chat`,
    injected so this module never has to import `llm.py`. With `tools=None`,
    or a model already known this process not to support tool calling at all,
    this is exactly `chat(**kwargs).message` — today's behavior, unchanged.

    `on_stream_token`, when given, streams every round through it live rather
    than waiting for each call to finish — including a tool round's own
    narration before its tool call, which is real model output but not "the
    file". `on_stream_start` fires before each round's first token, which a
    caller uses to reset what it's showing: a round that turns out to want a
    tool is superseded by the next round's reset the moment it starts, so
    what is left on screen once the loop returns is always the true final
    content, never a stale tool-round narration.
    """
    def call(round_kwargs: dict[str, Any]) -> Any:
        # Cloud's terminal stream is where it reliably provides token counts.
        # A caller may also ask to stream visible text. In both cases preserve
        # the same assembled Message contract for the read-only tool loop.
        if on_stream_token is None and not round_kwargs.get("stream"):
            response = chat(**round_kwargs)
            if on_usage is not None:
                on_usage(response)
            return response.message
        if on_stream_start is not None:
            on_stream_start()
        return _stream_chat(chat, round_kwargs, on_stream_token or (lambda _token: None), on_usage)

    model = kwargs.get("model")
    if tools is None or model in _UNSUPPORTED_MODELS:
        return call(kwargs)
    tool_kwargs = {**kwargs, "tools": READ_ONLY_SCHEMAS}
    messages = tool_kwargs["messages"]
    for _ in range(max(1, max_rounds)):
        try:
            message = call(tool_kwargs)
        except Exception as exc:  # noqa: BLE001 - re-raised unless it's the one case handled
            if not tools_unsupported(exc):
                raise
            _UNSUPPORTED_MODELS.add(model)
            if tools.project:
                bus.log(tools.project, "WARN",
                        f"{model} does not support tool calling; continuing without "
                        f"a read tool for this and later calls to it.", agent=tools.role)
            return call(kwargs)   # the original, tools-less kwargs
        calls = message.tool_calls or []
        messages.append(message.model_dump(exclude_none=True))
        if not calls:
            return message
        for call_ in calls:
            name, args = call_.function.name, (call_.function.arguments or {})
            messages.append({"role": "tool", "tool_name": name, "content": tools.call(name, args)})
    # Rounds exhausted: force a final answer, with no more reads offered.
    tool_kwargs.pop("tools", None)
    return call(tool_kwargs)
