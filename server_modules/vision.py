"""Which models can look at a picture.

Ollama says so itself: `POST /api/show` answers with the model's `capabilities` (for example "completion", "tools",
"thinking", "vision"), for a model on this computer and for ollama.com's own, through the built-in engine as well. That is
asked once per model and remembered (a week, and on disk across restarts); the model picker shows it as a "vision" mark, and
the prototype's visual review uses it to decide whether the model chosen can be shown screenshots at all.

An older Ollama that answers without `capabilities` is read by what else it says (the families and model info of a vision
model name an image encoder). A model that cannot be asked - the server is down, the key is missing - is unknown, never
"no": nothing is remembered about it, and it is asked again a little later.
"""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from . import config

TTL_SECONDS = 7 * 24 * 3600
RETRY_SECONDS = 120          # a model that could not be asked is asked again after this
LANES = 6                    # models asked about at once (each is a small request)
FILE = config.STATE / "model-capabilities.json"

# What an Ollama too old to list capabilities still shows for a model that reads images.
_VISION_FAMILIES = {"clip", "mllama", "siglip"}

_lock = threading.Lock()
_known: dict[str, dict[str, Any]] = {}      # model -> {"vision": bool, "at": float}
_failed: dict[str, float] = {}              # model -> when it last could not be asked
_pending: set[str] = set()
_pool: ThreadPoolExecutor | None = None
_loaded = False


def _load() -> None:
    global _loaded
    with _lock:
        if _loaded:
            return
        _loaded = True
        try:
            saved = json.loads(FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(saved, dict):
            for model, entry in saved.items():
                if isinstance(entry, dict) and isinstance(entry.get("vision"), bool):
                    _known[str(model)] = {"vision": entry["vision"], "at": float(entry.get("at") or 0)}


def _save() -> None:
    with _lock:
        snapshot = dict(_known)
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        temporary = FILE.with_suffix(".tmp")
        temporary.write_text(json.dumps(snapshot, indent=1), encoding="utf-8")
        temporary.replace(FILE)
    except OSError:
        pass  # remembered for this run only


def _read(info: Any, key: str) -> Any:
    return info.get(key) if isinstance(info, dict) else getattr(info, key, None)


def from_show(info: Any) -> bool | None:
    """Whether what `/api/show` answered describes a model that reads images (None: it says nothing either way)."""
    capabilities = _read(info, "capabilities")
    if isinstance(capabilities, (list, tuple, set)):
        return "vision" in {str(item).lower() for item in capabilities}
    details = _read(info, "details")
    families = {str(item).lower() for item in (_read(details, "families") or [])} if details else set()
    if families & _VISION_FAMILIES:
        return True
    model_info = _read(info, "modelinfo") or _read(info, "model_info") or {}
    if any(".vision." in str(key) or str(key).startswith("clip.") for key in model_info):
        return True
    return False if (families or model_info) else None


def _ask(model: str) -> bool | None:
    from . import llm

    try:
        return from_show(llm.client().show(model))
    except Exception:  # noqa: BLE001 - a server that cannot say is "unknown", not "no"
        return None


def _remember(model: str, vision: bool | None) -> None:
    with _lock:
        if vision is None:
            _failed[model] = time.time()
        else:
            _known[model] = {"vision": vision, "at": time.time()}
            _failed.pop(model, None)
    if vision is not None:
        _save()


def _fresh(entry: dict[str, Any] | None) -> bool:
    return bool(entry) and time.time() - float(entry.get("at") or 0) < TTL_SECONDS


def supports(model: str) -> bool | None:
    """Whether `model` reads images: True or False once Ollama has said, None when it cannot be asked right now."""
    model = str(model or "").strip()
    if not model:
        return None
    _load()
    with _lock:
        entry = _known.get(model)
        if _fresh(entry):
            return bool(entry["vision"])
    answer = _ask(model)
    _remember(model, answer)
    return answer


def _fill(model: str) -> None:
    try:
        _remember(model, _ask(model))
    finally:
        with _lock:
            _pending.discard(model)


def _executor() -> ThreadPoolExecutor:
    global _pool
    with _lock:
        if _pool is None:
            _pool = ThreadPoolExecutor(max_workers=LANES, thread_name_prefix="model-vision")
        return _pool


def capabilities(models: list[str]) -> dict[str, Any]:
    """What is known now about each of `models` ({"vision": bool}), starting to ask about the rest in the background.

    The studio asks again while `pending` is not zero, so the picker fills in as the answers arrive instead of
    waiting on every model at once."""
    _load()
    ids = [name for name in dict.fromkeys(str(item or "").strip() for item in models) if name]
    known: dict[str, dict[str, bool]] = {}
    todo: list[str] = []
    now = time.time()
    with _lock:
        for name in ids:
            entry = _known.get(name)
            if _fresh(entry):
                known[name] = {"vision": bool(entry["vision"])}
            elif name not in _pending and now - _failed.get(name, 0) > RETRY_SECONDS:
                todo.append(name)
        _pending.update(todo)
        pending = sum(1 for name in ids if name in _pending)
    for name in todo:
        _executor().submit(_fill, name)
    return {"capabilities": known, "pending": pending}


def forget() -> None:
    """Drop everything remembered (tests, and a changed engine)."""
    global _loaded
    with _lock:
        _known.clear()
        _failed.clear()
        _pending.clear()
        _loaded = True
