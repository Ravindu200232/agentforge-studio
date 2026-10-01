"""The interview's requirement-coverage taxonomy.

Unlike the fixed, ordered topic catalogue this replaces, there is no queue
here and no question order. The categories below are the *shape* of a
complete requirements picture — purpose, roles, workflows, data, and so on —
hardcoded because that structure is what every project needs classified.
Which of them still need asking, in what order, and with what exact wording
is decided fresh each turn by the model, from the project's own accumulated
answers — that decision does not belong in code.
"""
from __future__ import annotations

from typing import Any

from . import prompts

STATUSES = ("KNOWN", "PARTIAL", "UNKNOWN", "NOT_APPLICABLE")


def categories() -> dict[str, dict[str, Any]]:
    try:
        return prompts.data("interview/categories").get("categories") or {}
    except prompts.MissingPrompt:
        return {}


def blank_coverage() -> dict[str, dict[str, Any]]:
    """One entry per category, seeded UNKNOWN — except a category marked
    `auto: not_applicable` in the taxonomy (deployment: decided elsewhere,
    never a question here), which starts NOT_APPLICABLE."""
    out: dict[str, dict[str, Any]] = {}
    for key, entry in categories().items():
        status = "NOT_APPLICABLE" if entry.get("auto") == "not_applicable" else "UNKNOWN"
        out[key] = {"status": status, "confidence": "low", "facts": [],
                    "source": "", "updated_at": 0.0}
    return out
