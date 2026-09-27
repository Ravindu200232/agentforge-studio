"""The interview's question queue.

RP-SE-009 asks a fixed, ordered catalogue of topics, filtered by which kind of
product this is and by what the customer has already said, with a few topics
repeating once per role or per record. That ordering is what makes its interview
feel like a requirements session rather than a conversation that wanders, so this
reproduces it — from `prompts/interview/topics.json`, which is the catalogue
itself rather than a description of one.

Code picks the next topic. The model only phrases it.
"""
from __future__ import annotations

from typing import Any

from . import prompts

CRUD = "fullstack-crud"
LANDING = "landing-single-page"
TOOL = "single-tool"

TRUTHY = {True, "true", "yes", "y", 1, "1"}


def catalogue() -> dict[str, Any]:
    try:
        return prompts.data("interview/topics")
    except prompts.MissingPrompt:
        return {"topics": [], "max_questions": 25, "record_profiles": []}


def by_key() -> dict[str, dict]:
    return {t["key"]: t for t in catalogue().get("topics", []) if t.get("key")}


def max_questions() -> int:
    return max(3, int(catalogue().get("max_questions") or 25))


# --- what the session has said so far ---------------------------------------

def answer_for(answers: dict, key: str) -> Any:
    """One topic's answer, whether it was asked once or once per subject."""
    entry = answers.get(key)
    if entry is None:
        for stored_key, stored in answers.items():
            if str(stored_key).split(":", 1)[0] == key:
                entry = stored
                break
    if not isinstance(entry, dict):
        return None
    picked = entry.get("selected_values") or []
    return picked if picked else entry.get("value")


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    return [str(value)] if str(value).strip() else []


def _is_yes(value: Any) -> bool:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "y", "1"}
    return value in TRUTHY


def archetype_of(app_type: str, types: dict[str, Any]) -> str:
    return str((types.get(app_type) or {}).get("archetype") or CRUD)


def has_auth(answers: dict, archetype: str) -> bool:
    """Whether this product has accounts.

    A record-based product is assumed to until the roles question says
    otherwise; a landing page or a single tool is assumed not to.
    """
    roles = _as_list(answer_for(answers, "auth_roles"))
    if roles:
        return True
    explicit = answer_for(answers, "auth")
    if explicit is not None:
        return _is_yes(explicit)
    return archetype == CRUD


def registration_mode(answers: dict) -> str:
    for key in ("account_creation", "saas_signup"):
        value = answer_for(answers, key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value:
            return str(value).lower()
    return ""


def _matches(topic: dict, answers: dict, profile: str, archetype: str) -> bool:
    profiles = topic.get("profiles") or []
    if profiles and profile not in profiles:
        return False

    when = topic.get("when") or {}
    if "archetype" in when and when["archetype"] != archetype:
        return False
    if "auth" in when and bool(when["auth"]) is not has_auth(answers, archetype):
        return False
    if "registration_mode" in when and registration_mode(answers) != when["registration_mode"]:
        return False
    if "answered_yes" in when and not _is_yes(answer_for(answers, when["answered_yes"])):
        return False
    return True


def _subjects(topic: dict, answers: dict) -> list[str]:
    """What a repeating topic repeats over — each role, or each record."""
    over = topic.get("repeats_over")
    return _as_list(answer_for(answers, over)) if over else []


def build_queue(answers: dict, profile: str, types: dict[str, Any]) -> list[dict]:
    """Every question still to ask, in the catalogue's own order."""
    archetype = archetype_of(profile, types)
    queue: list[dict] = []
    for topic in catalogue().get("topics", []):
        key = topic.get("key")
        if not key or not _matches(topic, answers, profile, archetype):
            continue
        if topic.get("repeats_over"):
            for subject in _subjects(topic, answers):
                asked_key = f"{key}:{subject}"
                if asked_key not in answers:
                    queue.append({"topic": key, "key": asked_key, "subject": subject})
        elif key not in answers:
            queue.append({"topic": key, "key": key, "subject": None})
    return queue


def total_estimate(answers: dict, profile: str, types: dict[str, Any]) -> int:
    """Asked so far plus still queued, for the progress the studio shows."""
    return len(answers) + len(build_queue(answers, profile, types))
