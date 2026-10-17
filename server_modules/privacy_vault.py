"""The real values behind the privacy filter's placeholders, kept on this computer, so the product is built with them.

The privacy filter (`privacy.py`) finds the personal data in what the person types: names, email addresses, phone numbers and
so on. A model must never see them, but the specification and the application must: a shop's own email address on its contact
page, the owner's name on the about page. So each value found is kept here, encrypted, for its project, under a placeholder
numbered for the whole project (`<PERSON_1>` is the same person in every message), and the one place every model call goes
through (`session.RetryingClient.chat`) swaps them:

- on the way to the model, every known value in every message becomes its placeholder (`hide_request`);
- on the way back, every placeholder in the answer, its reasoning and the arguments of the tools that act on this computer
  becomes the real value again (`reveal_response`, `reveal_stream`), so the files written, the records kept and the chat show
  the real values.

A tool that reaches outside this computer (web search, web fetch, a plugin's tool) is given its arguments as the model wrote
them, placeholders and all: a value revealed there would leave the computer. A screenshot shown to a model that can see
pictures shows the page as it is, real values included; that is the one way a value can reach a model.
"""
from __future__ import annotations

import json
import re
import threading
from typing import Any, Iterable, Iterator

from cryptography.fernet import Fernet, InvalidToken

from . import config

FOLDER = "privacy"
KEY_FILE = "privacy.key"
# The tools that act on this computer: their arguments are given the real values. Every other tool keeps the placeholders.
LOCAL_TOOLS = {"write_file", "replace_text", "run_command", "read_file", "search_text", "list_files", "browser_inspect",
               "screenshot"}
_PLACEHOLDER = re.compile(r"(?:<|&lt;)([A-Z][A-Z_]*?)_(\d+)(?:>|&gt;)")
_PARTIAL = re.compile(r"(?:<|&(?:l(?:t(?:;[A-Z_\d]*)?)?)?)[A-Z_\d]*$")      # what may be the start of a placeholder, at the end
_WORDY = {"PERSON"}                                                         # matched as whole words; the rest as written

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}


def _cipher() -> Fernet:
    key = config.STATE / KEY_FILE
    key.parent.mkdir(parents=True, exist_ok=True)
    if not key.is_file():
        key.write_bytes(Fernet.generate_key())
    return Fernet(key.read_bytes())


def _path(project: str):
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", project)
    return config.STATE / FOLDER / f"{safe}.vault"


def _load(project: str) -> dict[str, Any]:
    """{"entries": [{"entity", "number", "value"}]}, read once and kept."""
    if project in _cache:
        return _cache[project]
    data: dict[str, Any] = {"entries": []}
    path = _path(project)
    if path.is_file():
        try:
            data = json.loads(_cipher().decrypt(path.read_bytes()).decode("utf-8"))
        except (InvalidToken, ValueError, OSError):
            data = {"entries": []}
    _cache[project] = data
    return data


def _save(project: str, data: dict[str, Any]) -> None:
    path = _path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_cipher().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8")))


def _key(entity: str, value: str) -> str:
    text = " ".join(str(value).split())
    return text.casefold()


def remember(project: str, values: Iterable[tuple[str, str]]) -> dict[str, str]:
    """Keep these (entity, value) pairs for the project; returns {value: placeholder}. The same value keeps its placeholder."""
    if not project:
        return {}
    given: dict[str, str] = {}
    with _lock:
        data = _load(project)
        entries = data["entries"]
        changed = False
        for entity, value in values:
            entity, text = str(entity).upper(), " ".join(str(value).split())
            if len(text) < 2:
                continue
            found = next((e for e in entries if e["entity"] == entity and _key(entity, e["value"]) == _key(entity, text)), None)
            if found is None:
                number = 1 + max((e["number"] for e in entries if e["entity"] == entity), default=0)
                found = {"entity": entity, "number": number, "value": text}
                entries.append(found)
                changed = True
            given[text] = f"<{entity}_{found['number']}>"
        if changed:
            _save(project, data)
    return given


def entries(project: str) -> list[dict[str, Any]]:
    if not project:
        return []
    with _lock:
        return list(_load(project)["entries"])


def forget(project: str) -> None:
    """A deleted project's values go with it."""
    with _lock:
        _cache.pop(project, None)
        try:
            _path(project).unlink()
        except OSError:
            pass


def active(project: str) -> bool:
    return bool(project) and bool(entries(project))


# --- swapping -----------------------------------------------------------------------------------------------------------

def _hider(project: str):
    rows = sorted(entries(project), key=lambda e: -len(e["value"]))
    if not rows:
        return None
    parts, names = [], {}
    for index, row in enumerate(rows):
        group = f"v{index}"
        names[group] = f"<{row['entity']}_{row['number']}>"
        body = re.escape(row["value"]).replace(r"\ ", r"\s+")
        parts.append(f"(?P<{group}>{r'(?<![\w@.])' + body + r'(?![\w@])' if row['entity'] in _WORDY else body})")
    pattern = re.compile("|".join(parts), re.IGNORECASE)
    return lambda text: pattern.sub(lambda m: names[m.lastgroup], text)


def hide(project: str, text: str) -> str:
    """`text` with every value kept for the project replaced by its placeholder: what a model may see."""
    if not text or not isinstance(text, str):
        return text
    swap = _hider(project)
    return swap(text) if swap else text


def reveal(project: str, text: str) -> str:
    """`text` with every placeholder of the project replaced by its real value; an unknown placeholder is left as it is."""
    if not text or not isinstance(text, str) or "_" not in text:
        return text
    rows = {(e["entity"], int(e["number"])): e["value"] for e in entries(project)}
    if not rows:
        return text
    return _PLACEHOLDER.sub(lambda m: rows.get((m.group(1), int(m.group(2))), m.group(0)), text)


def _field(item: Any, name: str) -> Any:
    return item.get(name) if isinstance(item, dict) else getattr(item, name, None)


def _with(item: Any, **changes: Any) -> Any:
    if isinstance(item, dict):
        return {**item, **changes}
    if hasattr(item, "model_copy"):
        return item.model_copy(update=changes)
    for name, value in changes.items():
        setattr(item, name, value)
    return item


def _deep(value: Any, swap) -> Any:
    if isinstance(value, str):
        return swap(value)
    if isinstance(value, dict):
        return {k: _deep(v, swap) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep(v, swap) for v in value]
    return value


def _calls(calls: Any, swap, only_local: bool) -> Any:
    if not calls:
        return calls
    out = []
    for call in calls:
        function = _field(call, "function")
        name = str(_field(function, "name") or "") if function is not None else ""
        arguments = _field(function, "arguments") if function is not None else None
        if function is None or arguments is None or (only_local and name not in LOCAL_TOOLS):
            out.append(call)
            continue
        out.append(_with(call, function=_with(function, arguments=_deep(arguments, swap))))
    return out


def _message(message: Any, swap, only_local: bool) -> Any:
    changes = {}
    for name in ("content", "thinking"):
        value = _field(message, name)
        if isinstance(value, str) and value:
            changes[name] = swap(value)
    calls = _field(message, "tool_calls")
    if calls:
        changes["tool_calls"] = _calls(calls, swap, only_local)
    return _with(message, **changes) if changes else message


def hide_request(project: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    """The chat request with every message's text, reasoning and tool arguments hidden (images are left as they are)."""
    messages = kwargs.get("messages")
    swap = _hider(project)
    if not messages or swap is None:
        return kwargs
    return {**kwargs, "messages": [_message(m, swap, only_local=False) for m in messages]}


def reveal_response(project: str, answer: Any) -> Any:
    """The model's answer with the real values back in its text, its reasoning and its local tools' arguments."""
    message = _field(answer, "message")
    if message is None or not active(project):
        return answer
    return _with(answer, message=_message(message, lambda text: reveal(project, text), only_local=True))


def reveal_stream(project: str, stream: Iterable[Any]) -> Iterator[Any]:
    """A streamed answer with the real values back. A placeholder split across two chunks is held until it is whole."""
    if not active(project):
        yield from stream
        return
    held = {"content": "", "thinking": ""}

    def text_of(chunk: Any, name: str, last: bool) -> str | None:
        message = _field(chunk, "message")
        value = _field(message, name) if message is not None else None
        if value is None and not held[name]:
            return None
        whole = held[name] + (value or "")
        tail = "" if last else (_PARTIAL.search(whole).group(0) if _PARTIAL.search(whole) else "")
        held[name] = tail
        return reveal(project, whole[: len(whole) - len(tail)] if tail else whole)

    def fixed(chunk: Any, last: bool) -> Any:
        message = _field(chunk, "message")
        if message is None:
            return chunk
        changes = {}
        for name in ("content", "thinking"):
            text = text_of(chunk, name, last)
            if text is not None:
                changes[name] = text
        calls = _field(message, "tool_calls")
        if calls:
            changes["tool_calls"] = _calls(calls, lambda text: reveal(project, text), only_local=True)
        return _with(chunk, message=_with(message, **changes)) if changes else chunk

    previous = None
    for chunk in stream:
        if previous is not None:
            yield fixed(previous, last=False)
        previous = chunk
    if previous is not None:
        yield fixed(previous, last=True)
