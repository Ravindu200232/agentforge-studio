"""ollama.com, reached directly with the saved API key: no Ollama app on this computer at all.

The Ollama app names its cloud models for itself (`deepseek-v4.1-flash:cloud`, `gpt-oss:120b-cloud`); ollama.com
names the same models plainly (`deepseek-v4.1-flash`, `gpt-oss:120b`). The studio keeps the app's names everywhere it
shows or saves one, so a project chosen either way keeps working, and `client()` turns them into ollama.com's names on
the way out.

ollama.com's model list is public (any key, or none, gets it), so it cannot say whether a key works: `test()` asks
for one token instead, which is what a wrong key is refused at.

AgentForge's built-in engine (engine-proxy/, config.built_in_engine) is ollama.com's API behind a server that holds
the key: `for_engine` gives the same client for it, sending the app's token to that server instead of a key.
"""
from __future__ import annotations

import threading
import time
from typing import Any

import httpx
import ollama
from ollama._types import WebFetchRequest, WebFetchResponse, WebSearchRequest, WebSearchResponse

from . import config

HOST = "https://ollama.com"
CACHE_SECONDS = 300
TIMEOUT = 30
# The smallest model ollama.com serves, for the one-token key check; the first listed model when it is gone.
CHECK_MODEL = "gpt-oss:20b"

_lock = threading.Lock()
_cache: dict[str, dict[str, Any]] = {}          # per host: {"at", "names"}


def remote_names(refresh: bool = False, host: str = HOST, token: str = "") -> list[str]:
    """The models ollama.com serves (directly, or through the built-in engine at `host`), as it names them.
    Briefly cached; the last good list when it cannot be read."""
    with _lock:
        cached = _cache.setdefault(host, {"at": 0.0, "names": []})
        if not refresh and cached["names"] and time.monotonic() - cached["at"] < CACHE_SECONDS:
            return list(cached["names"])
    try:
        answer = httpx.get(f"{host}/api/tags", timeout=TIMEOUT,
                           headers={"Authorization": f"Bearer {token}"} if token else None)
        answer.raise_for_status()
        found = [str(row.get("name") or row.get("model") or "") for row in answer.json().get("models") or []]
        found = [name for name in found if name]
    except (httpx.HTTPError, ValueError):
        with _lock:
            return list(cached["names"])
    with _lock:
        cached.update(at=time.monotonic(), names=found)
    return list(found)


def engine_names(saved: dict[str, Any] | None = None) -> list[str]:
    """The models the engine the settings choose serves: the built-in engine's, else ollama.com's."""
    built_in = config.built_in_engine()
    if config.engine(saved) == "built-in":
        return remote_names(host=built_in["url"], token=built_in["token"])
    return remote_names()


def studio_name(name: str) -> str:
    """ollama.com's name as the Ollama app writes it: `x` → `x:cloud`, `x:tag` → `x:tag-cloud`."""
    name = str(name or "").strip()
    if not name or name.endswith(":cloud") or name.endswith("-cloud"):
        return name
    return f"{name}-cloud" if ":" in name else f"{name}:cloud"


def remote_name(name: str, known: list[str] | None = None) -> str:
    """The Ollama app's name as ollama.com takes it: the `:cloud` / `-cloud` mark dropped, and a bare name matched
    to the one tagged model ollama.com lists for it (`deepseek-v4-pro` → `deepseek-v4-pro:0813`)."""
    plain = str(name or "").strip()
    if plain.endswith(":cloud"):
        plain = plain[: -len(":cloud")]
    elif plain.endswith("-cloud"):
        plain = plain[: -len("-cloud")]
    listed = known if known is not None else [n for cached in list(_cache.values()) for n in cached["names"]]
    if plain and listed and plain not in listed and ":" not in plain:
        tagged = [item for item in listed if item.startswith(plain + ":")]
        if len(tagged) == 1:
            return tagged[0]
    return plain


class _Names:
    """An ollama.com client (direct, or through the built-in engine at `host`) that takes the Ollama app's model
    names."""

    def __init__(self, inner: Any, host: str = HOST):
        self._inner = inner
        self._host = host

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def chat(self, **kwargs: Any) -> Any:
        if kwargs.get("model"):
            kwargs["model"] = remote_name(kwargs["model"])
        return self._inner.chat(**kwargs)

    def show(self, model: str, *args: Any, **kwargs: Any) -> Any:
        return self._inner.show(remote_name(model), *args, **kwargs)

    # The ollama library sends web search and fetch to ollama.com whatever its host is: through the built-in
    # engine they go to that host instead, which adds the key (its own `_request`, relative to the host).
    def web_search(self, query: str, max_results: int = 3) -> Any:
        if self._host == HOST:
            return self._inner.web_search(query=query, max_results=max_results)
        return self._inner._request(WebSearchResponse, "POST", "/api/web_search",  # noqa: SLF001
                                    json=WebSearchRequest(query=query, max_results=max_results).model_dump(exclude_none=True))

    def web_fetch(self, url: str) -> Any:
        if self._host == HOST:
            return self._inner.web_fetch(url=url)
        return self._inner._request(WebFetchResponse, "POST", "/api/web_fetch",  # noqa: SLF001
                                    json=WebFetchRequest(url=url).model_dump(exclude_none=True))


def client(key: str, host: str = HOST) -> Any:
    """An ollama.com client for `key` (at `host`, the built-in engine, the app's token), taking either naming."""
    if not key:
        raise ValueError("Add your ollama.com API key in Settings first.")
    remote_names(host=host, token=key if host != HOST else "")   # fills the list `remote_name` matches against
    return _Names(ollama.Client(host=host, headers={"Authorization": f"Bearer {key}"}), host)


def for_engine(saved: dict[str, Any]) -> Any:
    """The client for the engine the settings choose, when it is not the Ollama app here: the built-in engine, or
    ollama.com with the saved key."""
    if config.engine(saved) == "built-in":
        built_in = config.built_in_engine()
        return client(built_in["token"], host=built_in["url"])
    return client(str(saved.get("ollama_api_key") or ""))


def test(key: str, model: str = "") -> dict[str, Any]:
    """Whether ollama.com accepts `key`: one token from one model. Never returns the key."""
    key = str(key or "").strip()
    if not key:
        return {"ok": False, "models": 0, "message": "Paste your ollama.com API key first."}
    names = remote_names(refresh=True)
    probe = remote_name(model, names) if model else ""
    if probe not in names:
        probe = CHECK_MODEL if CHECK_MODEL in names or not names else names[0]
    try:
        answer = httpx.post(f"{HOST}/api/chat", timeout=TIMEOUT,
                            headers={"Authorization": f"Bearer {key}"},
                            json={"model": probe, "stream": False, "options": {"num_predict": 1},
                                  "messages": [{"role": "user", "content": "Reply with OK."}]})
    except httpx.HTTPError as exc:
        return {"ok": False, "models": len(names), "message": f"ollama.com could not be reached: {exc.__class__.__name__}."}
    if answer.status_code == 200:
        return {"ok": True, "models": len(names),
                "message": f"The key works · {len(names)} cloud model{'s' if len(names) != 1 else ''} available."}
    if answer.status_code == 401:
        return {"ok": False, "models": len(names),
                "message": "ollama.com refused this key. Copy the whole key again from ollama.com → Settings → Keys."}
    if answer.status_code == 429:
        return {"ok": True, "models": len(names),
                "message": "The key works, but its usage limit is reached right now; it will answer again later."}
    if answer.status_code == 403:
        return {"ok": False, "models": len(names),
                "message": "The key is valid but this account may not use cloud models (403). Check your plan on ollama.com."}
    return {"ok": False, "models": len(names), "message": f"ollama.com answered HTTP {answer.status_code}."}
