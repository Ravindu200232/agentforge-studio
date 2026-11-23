"""Direct hosted model discovery and Chat Completions transport for Studio."""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import Any, Iterator
from urllib.parse import urlsplit

import httpx
import ollama

from . import config, connection, ollama_cloud

PROVIDERS = {
    "deploy": ("Deploy", "https://api.deploy.com/api/v1"),
    "openai": ("OpenAI", "https://api.openai.com/v1"),
    "anthropic": ("Claude", "https://api.anthropic.com/v1"),
    "deepseek": ("DeepSeek", "https://api.deepseek.com"),
    "gemini": ("Gemini", "https://generativelanguage.googleapis.com/v1beta/openai"),
    "custom": ("OpenAI-compatible", ""),
}

# Deploy's /models supplies IDs; its public catalog supplies input modalities.
DEPLOY_MODELS = {
    "deepseek-ai/deepseek-v4.1-flash-1017": "DeepSeek V4.1 Flash",
    "zai-org/glm-5.3-flash": "GLM 5.3 Flash",
}
CACHE_SECONDS = 300
_lock = threading.Lock()
_catalogs: dict[tuple[str, str, str], tuple[float, list[dict], str]] = {}


def split_model(model: str) -> tuple[str, str]:
    provider, _, name = model.partition("/")
    return (provider, name) if provider in PROVIDERS and name else ("", model)


def ollama_remote_name(model: str) -> bool:
    return model.strip().lower().endswith((":cloud", "-cloud"))


def is_remote(model: str, saved: dict) -> bool:
    return bool(split_model(model)[0] or config.engine(saved) == "built-in" or ollama_remote_name(model))


def connection_key(saved: dict) -> tuple:
    return (config.engine(saved), saved.get("ollama_host"), saved.get("account_token"), saved.get("custom_api_url"),
            *(config.ai_key(provider, saved) for provider in config.AI_KEY_SETTINGS))


def clean_custom_url(value: Any) -> str:
    url = str(value or "").strip().rstrip("/")
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        secure = parts.scheme == "https"
        local = parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}
        if ((secure or local) and parts.hostname and not parts.username and parts.password is None
                and not parts.query and not parts.fragment and not any(c.isspace() for c in url)):
            _ = parts.port
            return url
    except ValueError:
        pass
    raise ValueError("Enter an HTTPS API base URL, or an HTTP URL on localhost, without credentials or a query.")


def _base_url(provider: str, saved: dict) -> str:
    return clean_custom_url(saved.get("custom_api_url")) if provider == "custom" else PROVIDERS[provider][1]


def _chat_model(provider: str, name: str) -> bool:
    if provider == "openai":
        return (name.startswith(("gpt-", "o1", "o3", "o4", "chatgpt-"))
                and not any(part in name for part in ("embedding", "audio", "realtime", "transcribe", "tts",
                                                     "gpt-image", "moderation", "search-preview", "-codex")))
    if provider == "gemini":
        return (name.startswith(("gemini-", "gemma-"))
                and not any(part in name for part in ("embedding", "image", "tts", "audio", "live", "aqa",
                                                     "robotics", "computer-use", "deep-research")))
    return True


def _model_row(provider: str, row: dict) -> dict:
    name = row["id"]
    architecture = row.get("architecture") or {}
    modalities = row.get("input_modalities")
    if modalities is None and isinstance(architecture, dict):
        modalities = architecture.get("input_modalities")
    capabilities = row.get("capabilities") or {}
    image_input = capabilities.get("image_input") if isinstance(capabilities, dict) else None
    vision = None
    if isinstance(modalities, list):
        vision = "image" in modalities
    elif isinstance(image_input, dict):
        vision = image_input.get("supported")
    elif provider == "deploy":
        vision = True if name in DEPLOY_MODELS else None
    elif provider == "openai":
        vision = not name.startswith(("gpt-3", "gpt-4-", "o1-mini", "o1-preview", "o3-mini"))
        vision = vision or name.startswith("gpt-4-turbo")
    elif provider == "gemini":
        vision = name.startswith("gemini-")
    limit = row.get("context_window") or row.get("max_input_tokens") or row.get("context_length")
    if not limit and provider == "deploy" and name in DEPLOY_MODELS:
        limit = 1_000_000
    return {"id": f"{provider}/{name}", "provider": provider,
            "label": row.get("display_name") or row.get("name") or
                     (DEPLOY_MODELS.get(name) if provider == "deploy" else None) or name,
            "tag": "cloud", "vision": vision if isinstance(vision, bool) else None,
            "context": limit if isinstance(limit, int) and limit > 0 else 0}


def _discover(provider: str, url: str, key: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    if provider == "anthropic":
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    found: dict[str, dict] = {}
    params = {}
    with httpx.Client(headers=headers, timeout=6) as client:
        while True:
            response = client.get(f"{url}/models", params=params)
            response.raise_for_status()
            payload = response.json()
            for row in payload["data"]:
                if isinstance(row, dict) and isinstance(row.get("id"), str):
                    row = {**row, "id": row["id"].removeprefix("models/")} if provider == "gemini" else row
                    if row["id"] and _chat_model(provider, row["id"]):
                        entry = _model_row(provider, row)
                        found[entry["id"]] = entry
            after = payload.get("last_id")
            if provider != "anthropic" or not payload.get("has_more") or not after or after == params.get("after_id"):
                return list(found.values())
            params = {"after_id": after}


def _catalog(provider: str, saved: dict) -> tuple[list[dict], str]:
    key = config.ai_key(provider, saved)
    if not key and provider != "custom":
        return [], ""
    try:
        url = _base_url(provider, saved)
    except ValueError as exc:
        return [], str(exc)
    if not url:
        return [], ""
    cache_key = (provider, url, hashlib.sha256(key.encode()).hexdigest())
    with _lock:
        expiry, rows, error = _catalogs.get(cache_key, (0, [], ""))
        if expiry > time.monotonic():
            return rows, error
    try:
        rows, error = _discover(provider, url, key), ""
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in (401, 403):
            rows, error = [], f"API key or access was refused (HTTP {status})."
        else:
            error = f"Could not load models (HTTP {status})."
    except (httpx.HTTPError, KeyError, TypeError, ValueError):
        error = "Could not load models from this provider."
    with _lock:
        for old in [item for item in _catalogs if item[0] == provider and item != cache_key]:
            _catalogs.pop(old, None)
        _catalogs[cache_key] = (time.monotonic() + (15 if error else CACHE_SECONDS), rows, error)
    return rows, error


def catalogs(saved: dict) -> tuple[list[dict], dict[str, str]]:
    active = [provider for provider in PROVIDERS
              if (saved.get("custom_api_url") if provider == "custom" else config.ai_key(provider, saved))]
    rows, errors = [], {}
    if active:
        with ThreadPoolExecutor(max_workers=len(active)) as pool:
            for provider, (found, error) in zip(active, pool.map(lambda item: _catalog(item, saved), active)):
                rows.extend(found)
                if error:
                    errors[provider] = error
    return rows, errors


def vision_for(model: str, saved: dict) -> bool | None:
    provider, _ = split_model(model)
    if provider:
        return next((row["vision"] for row in _catalog(provider, saved)[0] if row["id"] == model), None)
    return None


def _image_url(image: str | bytes) -> str:
    if isinstance(image, str) and image.startswith(("https://", "http://", "data:image/")):
        return image
    try:
        if isinstance(image, bytes):
            head = image[:12]
            image = base64.b64encode(image).decode("ascii")
        else:
            head = base64.b64decode(image[:16], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("The attached image is not valid base64.") from None
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "png"
    elif head.startswith(b"\xff\xd8\xff"):
        mime = "jpeg"
    elif head.startswith((b"GIF87a", b"GIF89a")):
        mime = "gif"
    elif head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        mime = "webp"
    else:
        raise ValueError("Use a PNG, JPEG, GIF or WebP image with this AI provider.")
    return f"data:image/{mime};base64,{image}"


class ProviderToolCall(ollama.Message.ToolCall):
    id: str | None = None
    extra_content: dict | None = None


class ProviderMessage(ollama.Message):
    tool_calls: list[ProviderToolCall] | None = None


class ProviderResponse(ollama.ChatResponse):
    message: ProviderMessage


def _messages(messages: list[dict], provider: str, reasoning: bool) -> list[dict]:
    history: list[dict] = []
    pending: deque[str] = deque()
    for index, original in enumerate(messages):
        row = original if isinstance(original, dict) else original.model_dump(exclude_none=True)
        role, content = row["role"], row.get("content") or ""
        if role == "tool":
            if pending:
                history.append({"role": "tool", "tool_call_id": pending.popleft(), "content": content})
            continue
        while pending:
            history.append({"role": "tool", "tool_call_id": pending.popleft(), "content": "Tool result unavailable."})
        message = {"role": role, "content": content}
        if row.get("images") and role == "user":
            message["content"] = ([{"type": "text", "text": content}] if content else []) + [
                {"type": "image_url", "image_url": {"url": _image_url(image)}} for image in row["images"]
            ]
        if role == "assistant":
            calls = []
            for position, call in enumerate(row.get("tool_calls") or []):
                call_id = call.get("id") or f"call_agentforge_{index}_{position}"
                pending.append(call_id)
                function = call["function"]
                tool = {"id": call_id, "type": "function", "function": {
                    "name": function["name"], "arguments": json.dumps(function.get("arguments") or {}, ensure_ascii=False)}}
                if provider == "gemini" and call.get("extra_content"):
                    tool["extra_content"] = call["extra_content"]
                calls.append(tool)
            if calls:
                message["tool_calls"] = calls
            if reasoning:
                message["reasoning_content"] = row.get("thinking") or ""
            if not content and not calls:
                continue
        history.append(message)
    while pending:
        history.append({"role": "tool", "tool_call_id": pending.popleft(), "content": "Tool result unavailable."})
    return history


def _response(message: dict, *, calls: list[dict] | None = None, done: bool,
              usage: dict | None = None) -> ProviderResponse:
    tool_calls = []
    for call in calls or []:
        function = call.get("function") or {}
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                raise ValueError("The model returned invalid tool arguments.") from None
        if not function.get("name") or not isinstance(arguments, dict):
            raise ValueError("The model returned an invalid tool call.")
        tool_calls.append(ProviderToolCall(id=call.get("id"), extra_content=call.get("extra_content"),
                                         function={"name": function["name"], "arguments": arguments}))
    usage = usage or {}
    return ProviderResponse(message=ProviderMessage(role="assistant", content=message.get("content"),
                            thinking=message.get("reasoning_content") or message.get("reasoning"),
                            tool_calls=tool_calls or None), done=done,
                            prompt_eval_count=usage.get("prompt_tokens"), eval_count=usage.get("completion_tokens"))


class HostedClient:
    def __init__(self, provider: str, saved: dict):
        self.provider = provider
        self.label = PROVIDERS[provider][0]
        self.key = config.ai_key(provider, saved)
        self.url = _base_url(provider, saved)
        if not self.url or (not self.key and provider != "custom"):
            raise ValueError(f"Configure {self.label} in Settings → AI Providers to use this model.")
        self._http = httpx.Client(headers={"Authorization": f"Bearer {self.key}"} if self.key else {},
                                  timeout=connection.model_timeout())

    def _error(self, error: Any, status: int) -> None:
        if status in (401, 403):
            detail = "API key or model access was refused"
        else:
            detail = error.get("message") if isinstance(error, dict) else error
            detail = str(detail or f"HTTP {status}")
            if self.key:
                detail = detail.replace(self.key, "<hidden>")
        if self.provider == "deploy" and status == 400 and detail.lower().strip() == "request deadline exceeded":
            # Deploy can report a gateway deadline as 400. Let the normal model retry policy handle it.
            status = 504
        raise ollama.ResponseError(f"{self.label}: {detail[:450]}", status)

    def _check(self, response: httpx.Response) -> None:
        if response.is_success:
            return
        response.read()
        try:
            error = response.json().get("error")
        except (AttributeError, ValueError):
            error = None
        self._error(error, response.status_code)

    def chat(self, *, model: str, messages: list[dict], stream: bool = False, think: bool = False,
             tools: list[dict] | None = None, options: dict | None = None, **_kwargs: Any) -> Any:
        _, name = split_model(model)
        reasoning = self.provider == "deepseek" and think
        payload: dict[str, Any] = {"model": name, "messages": _messages(messages, self.provider, reasoning),
                                   "stream": bool(stream)}
        if tools:
            payload["tools"] = list(tools)
        limit = (options or {}).get("num_predict")
        if isinstance(limit, int) and limit > 0:
            payload["max_completion_tokens" if self.provider == "openai" else "max_tokens"] = limit
        if self.provider == "deploy" and name in DEPLOY_MODELS:
            # GLM always reasons. DeepSeek's Deploy variant can disable it.
            payload["reasoning_effort"] = "high" if think else ("low" if name.startswith("zai-org/") else "none")
        elif self.provider == "deepseek":
            payload["thinking"] = {"type": "enabled" if think else "disabled"}
        if stream:
            if self.provider in {"deploy", "openai", "deepseek"}:
                payload["stream_options"] = {"include_usage": True}
            return self._stream(payload)
        response = self._http.post(f"{self.url}/chat/completions", json=payload)
        self._check(response)
        packet = response.json()
        if packet.get("error"):
            self._error(packet["error"], 400)
        choices = packet.get("choices") or []
        if not choices:
            raise ValueError(f"{self.label} returned no model response.")
        message = choices[0]["message"]
        return _response(message, calls=message.get("tool_calls"), usage=packet.get("usage"), done=True)

    def _stream(self, payload: dict) -> Iterator[ProviderResponse]:
        calls: dict[int, dict] = {}
        usage = None
        finished = False
        with self._http.stream("POST", f"{self.url}/chat/completions", json=payload,
                               headers={"Accept": "text/event-stream"}) as response:
            self._check(response)
            for line in response.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    finished = True
                    break
                packet = json.loads(data)
                if packet.get("error"):
                    self._error(packet["error"], 400)
                usage = packet.get("usage") or usage
                choices = packet.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                delta = choice.get("delta") or {}
                for part in delta.get("tool_calls") or []:
                    slot = calls.setdefault(part["index"], {"function": {"name": "", "arguments": ""}})
                    for field in ("id", "extra_content"):
                        if part.get(field):
                            slot[field] = part[field]
                    for field in ("name", "arguments"):
                        fragment = (part.get("function") or {}).get(field)
                        if fragment:
                            slot["function"][field] += fragment
                if choice.get("finish_reason"):
                    finished = True
                if delta.get("content") or delta.get("reasoning_content") or delta.get("reasoning"):
                    yield _response(delta, done=False)
        if not finished:
            raise ConnectionError(f"{self.label} closed the model stream before completion.")
        yield _response({}, calls=[calls[index] for index in sorted(calls)], usage=usage, done=True)


class Client:
    """Route each role's model to its provider while retaining Ollama's native API."""

    def __init__(self, saved: dict):
        self.saved = saved
        self.engine = config.engine(saved)
        self._lock = threading.Lock()
        self._clients: dict[str, Any] = {}

    def _client(self, provider: str) -> Any:
        with self._lock:
            if provider not in self._clients:
                if provider in PROVIDERS:
                    inner = HostedClient(provider, self.saved)
                elif provider == "local":
                    inner = ollama.Client(host=self.saved.get("ollama_host") or "http://localhost:11434",
                                          timeout=connection.model_timeout())
                else:
                    inner = ollama_cloud.for_engine({**self.saved, "engine": provider})
                self._clients[provider] = inner
            return self._clients[provider]

    def _route(self, model: str) -> str:
        provider, _ = split_model(model)
        if provider:
            return provider
        if self.engine == "built-in":
            return self.engine
        if ollama_remote_name(model) and config.ai_key("ollama", self.saved):
            return "cloud"
        return "local"

    def chat(self, *, model: str, **kwargs: Any) -> Any:
        return self._client(self._route(model)).chat(model=model, **kwargs)

    def show(self, model: str) -> Any:
        provider, _ = split_model(model)
        if not provider:
            return self._client(self._route(model)).show(model)
        rows, _ = _catalog(provider, self.saved)
        row = next((row for row in rows if row["id"] == model), {})
        return SimpleNamespace(modelinfo={"provider.context_length": row["context"]} if row.get("context") else {})

    def web_search(self, **kwargs: Any) -> Any:
        return self._client(self.engine).web_search(**kwargs)

    def web_fetch(self, **kwargs: Any) -> Any:
        return self._client(self.engine).web_fetch(**kwargs)
