"""Load the prompt packs.

Every instruction this product gives a model lives in `prompts/` as markdown. No
stage embeds its own wording: it names a pack, fills the placeholders, and sends
what comes back. Changing how a stage behaves is editing a file, not editing
code.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from . import config

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}", re.IGNORECASE)


class MissingPrompt(FileNotFoundError):
    pass


def _raw(name: str) -> str:
    path = (config.PROMPTS / f"{name}.md").resolve()
    if not path.is_relative_to(config.PROMPTS.resolve()):
        raise MissingPrompt(f"prompt name escapes the prompt pack: {name}")
    if not path.is_file():
        raise MissingPrompt(f"no prompt pack at prompts/{name}.md")
    return path.read_text(encoding="utf-8")


def load(name: str, **values: Any) -> str:
    """One prompt, with its `{{placeholders}}` filled in.

    An unfilled placeholder is left as-is rather than blanked, so a missing value
    shows up in the transcript instead of silently becoming an empty instruction.
    """
    text = _raw(name)

    def swap(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            return match.group(0)
        value = values[key]
        return value if isinstance(value, str) else str(value)

    return _PLACEHOLDER.sub(swap, text)


def exists(name: str) -> bool:
    try:
        _raw(name)
        return True
    except MissingPrompt:
        return False


@lru_cache(maxsize=32)
def data(name: str) -> Any:
    """A JSON asset that sits beside the prompts, such as the app type catalogue.

    Kept in the pack rather than in code for the same reason the prompts are:
    changing the choices a customer is offered should be editing a file.
    """
    import json

    path = (config.PROMPTS / f"{name}.json").resolve()
    if not path.is_relative_to(config.PROMPTS.resolve()):
        raise MissingPrompt(f"asset name escapes the prompt pack: {name}")
    if not path.is_file():
        raise MissingPrompt(f"no asset at prompts/{name}.json")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise MissingPrompt(f"prompts/{name}.json is not valid JSON: {exc}") from exc


def skill(area: str, name: str) -> str:
    """One skill page, by area and slug — `srs`, `deployment`, `design`."""
    for candidate in (config.PROMPTS / area / "skills" / name / "SKILL.md",
                      config.PROMPTS / area / "themes" / name / "SKILL.md"):
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise MissingPrompt(f"no skill page for {area}/{name}")


def skills(area: str, only: tuple[str, ...] = (), budget: int = 0) -> str:
    """Several skill pages, joined, optionally trimmed to a character budget."""
    base = config.PROMPTS / area / "skills"
    if not base.is_dir():
        return ""
    chosen = sorted(p for p in base.iterdir() if p.is_dir()
                    and (not only or p.name in only))
    parts = []
    for folder in chosen:
        page = folder / "SKILL.md"
        if page.is_file():
            parts.append(page.read_text(encoding="utf-8"))
    joined = "\n\n---\n\n".join(parts)
    return joined[:budget] if budget else joined


def catalogue(area: str, kind: str = "skills") -> list[dict[str, str]]:
    """What is available in one area, as `{slug, title, summary}` rows."""
    base = config.PROMPTS / area / kind
    if not base.is_dir():
        return []
    rows = []
    for folder in sorted(p for p in base.iterdir() if p.is_dir()):
        page = folder / "SKILL.md"
        if not page.is_file():
            continue
        text = page.read_text(encoding="utf-8")
        title = next((line.lstrip("# ").strip() for line in text.splitlines()
                      if line.startswith("# ")), folder.name)
        summary = ""
        for line in text.splitlines():
            if line.lower().startswith("description:"):
                summary = line.split(":", 1)[1].strip()
                break
        rows.append({"slug": folder.name, "title": title, "summary": summary})
    return rows


def clear_cache() -> None:
    """Pick up an edited prompt without restarting the server."""
    data.cache_clear()
