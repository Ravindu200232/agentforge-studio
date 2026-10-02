"""Focused model calls.

A stage that writes fourteen pages in one agentic conversation spends its output
budget on the first few and truncates the rest, and every later call drags the
whole history behind it. So the artifacts are not written by the agent: each one
is its own call, with only the context it needs, and independent ones run at the
same time.

This is the difference between a wireframe of four hundred characters and a
wireframe of twenty thousand. `ProjectSession` still owns the conversation, and
still owns anything that needs tools — the build, the tests, the deployment, and
a change typed into the chat stream. Everything that is simply *written* comes
through here.
"""
from __future__ import annotations

import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar

import httpx
import ollama

from . import bus, config

T = TypeVar("T")

# How many calls run at once. Quality is the point, so this is about not holding
# the model's whole queue rather than about finishing quickly.
LANES = 3

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(.+?)```", re.DOTALL)


class LLMUnavailable(RuntimeError):
    """Ollama could not be reached, or no model is selected."""


class LLMRepairFailed(ValueError):
    """The model could not produce something that passes, after retries."""

    def __init__(self, label: str, raw: str, reason: str):
        super().__init__(f"{label}: {reason}")
        self.label = label
        self.raw = raw


def extract_json(text: str) -> Any:
    """The JSON value in a model reply, however it was wrapped."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("the model returned nothing")
    fenced = _JSON_BLOCK.search(raw)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        return json.loads(raw)
    except ValueError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = raw.find(opener), raw.rfind(closer)
        if start >= 0 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except ValueError:
                continue
    raise ValueError("the model did not return JSON")


def extract_html(text: str) -> str:
    """The HTML document in a model reply, without its commentary or fence."""
    raw = (text or "").strip()
    fenced = re.search(r"```(?:html)?\s*(.+?)```", raw, re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    start = raw.lower().find("<!doctype")
    if start < 0:
        start = raw.lower().find("<html")
    if start > 0:
        raw = raw[start:]
    end = raw.lower().rfind("</html>")
    if end > 0:
        raw = raw[:end + len("</html>")]
    return raw.strip()


_local = threading.local()


def bind_stop(event: threading.Event | None) -> None:
    """The Stop of the run working on this thread. Every model call made here - and in the lanes it opens -
    honours it, so Stop ends a page being drawn or a document being written at once rather than when it is done."""
    _local.stop = event


def _stop_event() -> threading.Event | None:
    return getattr(_local, "stop", None)


def _stopped() -> bool:
    event = _stop_event()
    return bool(event is not None and event.is_set())


def _wait_for_stop(seconds: float) -> bool:
    event = _stop_event()
    if event is None:
        time.sleep(seconds)
        return False
    return event.wait(seconds)


def client() -> Any:
    """One Ollama client per thread, so parallel lanes do not share a socket."""
    saved = config.settings()
    key = (config.engine(saved), saved.get("ollama_host"), saved.get("ollama_api_key"))
    if getattr(_local, "key", None) != key or getattr(_local, "client", None) is None:
        if saved.get("cloud"):
            from . import ollama_cloud

            try:
                inner = ollama_cloud.for_engine(saved)
            except ValueError as exc:
                raise LLMUnavailable(str(exc)) from exc
        else:
            inner = ollama.Client(host=saved.get("ollama_host") or "http://localhost:11434")
        from .session import RetryingClient
        _local.client = RetryingClient(inner, cancelled=_stopped, wait_for_cancel=_wait_for_stop)
        _local.key = key
    return _local.client


def _model(override: str = "") -> str:
    chosen = (override or config.setting("model") or "").strip()
    if not chosen:
        raise LLMUnavailable("No model is selected. Pick one in the studio.")
    return chosen


_context_cache: dict[str, int] = {}
_context_lock = threading.Lock()
_usage_lock = threading.Lock()
_usage_by_run: dict[tuple[str, int], dict[str, int]] = {}
# The largest single request each project's focused calls have needed. The interview, the SRS and
# the wireframes are many independent calls of very different sizes, so "this request's" size jumps
# up and down and read as the context being lost; the largest so far only ever holds or grows.
_peak_by_project: dict[str, int] = {}


def _peak_seed(project: str) -> int:
    """After a restart, start from the largest focused figure already recorded, not from zero."""
    for event in reversed(bus.history(project)):
        if event.get("type") == "memory" and event.get("context_scope") == "focused":
            return int(event.get("used") or 0)
    return 0


def _context_for(model: str) -> int:
    """`local_num_ctx` when the customer set one; otherwise the model's own
    advertised maximum, read once per model and cached for this process."""
    override = int(config.setting("context") or 0)
    if override:
        return override
    with _context_lock:
        if model in _context_cache:
            return _context_cache[model]
    from ollama_terminal.agent import model_context_length
    found = model_context_length(client(), model) or 0
    with _context_lock:
        _context_cache[model] = found
    return found


def _tools_for(project: str, workspace: Path | None, role: str) -> Any:
    """A `ReadOnlyTools` for this call, or `None` when no project/workspace was given.

    Opt-in only: a caller that doesn't pass `project`/`workspace` gets exactly
    today's tool-less behavior.
    """
    if not project or workspace is None:
        return None
    from . import llm_tools
    saved = config.settings()
    return llm_tools.ReadOnlyTools(workspace, project=project, role=role, client=client(),
                                   use_local_web=not saved.get("cloud"),
                                   web_host=saved.get("ollama_host") or "http://localhost:11434")


def _usage_count(response: Any, *names: str) -> int:
    """Read an exact provider usage field, including hosted API aliases."""
    for container in (response, getattr(response, "usage", None)):
        for name in names:
            value = (container.get(name) if isinstance(container, dict)
                     else getattr(container, name, None))
            if isinstance(value, int) and value > 0:
                return value
    return 0


def _run_started_at(project: str) -> int:
    """The active run id is the boundary for a focused-call usage total."""
    for event in reversed(bus.history(project)):
        if event.get("type") != "run_state":
            continue
        if event.get("status") in {"queued", "running"}:
            return int(event.get("at") or 0)
        return 0
    return 0


def _focused_usage(project: str, model: str, context: int, role: str) -> Callable[[Any], None] | None:
    """Report real token counts for focused SRS/prototype calls into chat."""
    if not project:
        return None

    def report(response: Any) -> None:
        prompt = _usage_count(response, "prompt_eval_count", "prompt_tokens", "input_tokens")
        generated = _usage_count(response, "eval_count", "completion_tokens", "output_tokens")
        # Do not turn a provider that supplied no accounting into a fake zero.
        if not prompt and not generated:
            return
        started = _run_started_at(project)
        key = (project, started)
        seed = _peak_seed(project) if project not in _peak_by_project else 0
        with _usage_lock:
            totals = _usage_by_run.setdefault(key, {"sent": 0, "received": 0})
            totals["sent"] += prompt
            totals["received"] += generated
            sent, received = totals["sent"], totals["received"]
            stale = [item for item in _usage_by_run if item[0] == project and item != key]
            for item in stale:
                _usage_by_run.pop(item, None)
            largest = max(_peak_by_project.get(project, seed), prompt)
            _peak_by_project[project] = largest
        bus.memory(project, model, largest, context, 0, agent=role or bus.DEVELOPER,
                   turn_started_at=started, turn_input_tokens=sent,
                   turn_output_tokens=received, context_scope="focused")

    return report


def complete(system: str, user: str, model: str = "", think: bool | None = None,
            project: str = "", workspace: Path | None = None, role: str = "",
            thinking_fallback: bool = True) -> str:
    """One call, one answer, no history — and, when `project`/`workspace` are
    given, a read-only tool the model can call instead of being handed
    pre-embedded file content.

    `thinking_fallback=False` is for an answer that must be the thing asked for and nothing else (a diagram's
    source): a reply with no content then comes back empty, never as the model's reasoning ("Let me read…").
    """
    from . import llm_tools
    kwargs: dict[str, Any] = {
        "model": _model(model),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "stream": bool(config.setting("cloud")),
    }
    kwargs["think"] = config.thinking_enabled() if think is None else think
    context = _context_for(kwargs["model"])
    if context and not config.setting("cloud"):
        kwargs["options"] = {"num_ctx": context}
    tools = _tools_for(project, workspace, role)
    message = llm_tools.run_chat(client().chat, kwargs, tools,
                                 on_usage=_focused_usage(project, kwargs["model"], context, role))
    llm_tools.tag_effort(tools, kwargs["think"], "completion")
    text = (getattr(message, "content", "") or "").strip()
    if not text and thinking_fallback:
        # A reasoning model can answer in `thinking` and leave `content` empty.
        text = (getattr(message, "thinking", "") or "").strip()
    return text


def complete_json(system: str, user: str, validator: Callable[[Any], Any] | None = None,
                  label: str = "json", model: str = "", attempts: int = 3,
                  project: str = "", workspace: Path | None = None, role: str = "") -> Any:
    """One call answered as JSON, repaired in place when it is not.

    The repair carries the model's own broken answer and what was wrong with it,
    which is what makes the second attempt different from the first. When
    `project`/`workspace` are given, the model gets a read-only tool instead
    of pre-embedded file content.
    """
    from . import llm_tools
    tools = _tools_for(project, workspace, role)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = ""
    for _ in range(max(1, attempts)):
        kwargs: dict[str, Any] = {"model": _model(model), "messages": messages,
                                  "stream": bool(config.setting("cloud"))}
        # Local Ollama supports JSON mode and returns syntactically valid JSON.
        # Ollama Cloud currently does not support constrained output, so keep
        # the existing prompt-and-validator repair path for hosted models.
        # Stacking constrained-JSON mode with tool-calling in one call is
        # unverified, so a tool-enabled call relies on the repair loop alone.
        selected = kwargs["model"].lower()
        if tools is None and not config.setting("cloud") and not selected.endswith(":cloud"):
            kwargs["format"] = "json"
        kwargs["think"] = config.thinking_enabled()
        context = _context_for(kwargs["model"])
        if context and not config.setting("cloud"):
            kwargs["options"] = {"num_ctx": context}
        message = llm_tools.run_chat(client().chat, kwargs, tools,
                                     on_usage=_focused_usage(project, kwargs["model"], context, role))
        llm_tools.tag_effort(tools, kwargs["think"], label)
        last = ((getattr(message, "content", "") or "")
                or (getattr(message, "thinking", "") or "")).strip()

        try:
            data = extract_json(last)
        except ValueError as exc:
            messages += [{"role": "assistant", "content": last[:2000]},
                         {"role": "user", "content":
                          f"That was not valid JSON ({exc}). Return ONLY the JSON this "
                          f"task asked for — no prose, no markdown fence."}]
            continue

        if validator is None:
            return data
        try:
            checked = validator(data)
        except Exception as exc:  # noqa: BLE001 - the message is the repair
            messages += [{"role": "assistant", "content": last[:2000]},
                         {"role": "user", "content":
                          f"That JSON did not pass validation: {exc}\n\nFix exactly "
                          f"that and return the corrected JSON in full."}]
            continue
        return data if checked is None else checked
    raise LLMRepairFailed(label, last, f"no valid JSON after {attempts} attempts")


def complete_html(system: str, user: str, model: str = "", minimum: int = 0,
                  label: str = "html", attempts: int = 2,
                  think: bool | None = None,
                  project: str = "", workspace: Path | None = None, role: str = "",
                  on_stream_start: Callable[[], None] | None = None,
                  on_stream_token: Callable[[str], None] | None = None) -> str:
    """One call answered as a complete HTML document. When `project`/`workspace`
    are given, the model gets a read-only tool instead of pre-embedded file content.

    `on_stream_start`/`on_stream_token`, when given, are called as the model
    writes — the caller decides what "streaming" means to it (a bus event, a
    log line); this module stays oblivious to that, same as it stays
    oblivious to `bus` everywhere else.
    """
    from . import llm_tools
    tools = _tools_for(project, workspace, role)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last = ""
    for _ in range(max(1, attempts)):
        kwargs: dict[str, Any] = {"model": _model(model), "messages": messages,
                                  "stream": bool(config.setting("cloud"))}
        kwargs["think"] = config.thinking_enabled() if think is None else think
        context = _context_for(kwargs["model"])
        if context and not config.setting("cloud"):
            kwargs["options"] = {"num_ctx": context}
        message = llm_tools.run_chat(client().chat, kwargs, tools,
                                     on_stream_start=on_stream_start, on_stream_token=on_stream_token,
                                     on_usage=_focused_usage(project, kwargs["model"], context, role))
        llm_tools.tag_effort(tools, kwargs["think"], label)
        last = ((getattr(message, "content", "") or "")
                or (getattr(message, "thinking", "") or "")).strip()
        html = extract_html(last)

        if html.lower().startswith(("<!doctype", "<html")) and len(html) >= minimum:
            return html

        why = ("it was not a complete HTML document starting with <!DOCTYPE html>"
               if not html.lower().startswith(("<!doctype", "<html"))
               else f"it was only {len(html)} characters, and this page needs at "
                    f"least {minimum} — you left the page half drawn")
        messages += [{"role": "assistant", "content": html[:1500]},
                     {"role": "user", "content":
                      f"That is not usable: {why}. Use the supplied project files again if "
                      f"you need to resolve a missing detail, then draw the whole page and "
                      f"return the complete HTML document and nothing else."}]
    raise LLMRepairFailed(label, last, "no complete HTML document")


def web_search(query: str, max_results: int = 4) -> list[dict[str, str]]:
    """Ollama's web search: `[{title, url, content}]`, empty when there is nothing or the search is not available.

    The same route the agents' `web_search` tool takes: the local Ollama server needs no key, Ollama Cloud needs the saved one.
    """
    saved = config.settings()
    query = " ".join(str(query or "").split())[:300]
    if not query:
        return []
    try:
        if saved.get("cloud"):
            found = client().web_search(query=query, max_results=max_results).model_dump()
        else:
            host = (saved.get("ollama_host") or "http://localhost:11434").rstrip("/")
            reply = httpx.post(f"{host}/api/experimental/web_search", json={"query": query, "max_results": max_results}, timeout=30)
            reply.raise_for_status()
            found = reply.json()
    except Exception:  # noqa: BLE001 - a search that cannot run is not a reason to stop drawing
        return []
    return [{"title": str(row.get("title") or "")[:200], "url": str(row.get("url") or ""), "content": str(row.get("content") or "")[:1500]}
            for row in (found.get("results") or []) if isinstance(row, dict)]


def in_lanes(items: Sequence[T], work: Callable[[T], Any], lanes: int = LANES,
             on_error: Callable[[T, Exception], Any] | None = None) -> list[Any]:
    """Run `work` over `items`, a few at a time, keeping their order.

    One item failing costs that item rather than the set — a page that does not
    draw should not take the other thirteen with it.
    """
    if not items:
        return []
    results: list[Any] = [None] * len(items)
    stop = _stop_event()

    def run(index: int, item: T) -> None:
        _local.stop = stop  # each lane honours the Stop of the run that opened it
        try:
            results[index] = work(item)
        except Exception as exc:  # noqa: BLE001 - reported per item
            if stop is not None and stop.is_set():
                raise  # stopped: no item is reported as failed, the run ends
            results[index] = on_error(item, exc) if on_error else None

    with ThreadPoolExecutor(max_workers=max(1, lanes)) as pool:
        list(pool.map(lambda pair: run(*pair), list(enumerate(items))))
    return results
