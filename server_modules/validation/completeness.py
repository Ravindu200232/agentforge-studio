"""Does the specification actually cover the plan it came from?

The schema says the document is the right shape and the standards review says the
requirements are well written. Neither of them notices that a seven-screen
product was specified with three requirements, that a database with two tables
has no entity-relationship diagram, or that every wireframe is four lines long.

Those are the failures that survive both other gates, because each artifact is
individually valid. What catches them is counting: the plan says what exists, so
anything the plan has and the specification does not is a gap with a name.
"""
from __future__ import annotations

import re
from typing import Any

# A wireframe here is one complete, self-contained HTML document: doctype, head,
# an inline stylesheet and a body that holds the whole screen.
WIREFRAME_MARKERS = ("<!doctype", "<html")

# How much page one section is worth. These are calibrated against the reference
# implementation's own output, where a real page runs from fifteen to
# thirty-four thousand characters — a sign-in screen at the bottom of that range
# and an admin table at the top. The floors below sit deliberately under those
# numbers: they catch the page that was abandoned half-drawn, not the page that
# is merely compact.
#
# Sections and functions overlap — a page's "form" section and its "sign in"
# function are one thing on screen, not two — so functions count half.
WIREFRAME_CHARS_PER_SECTION = 1500
WIREFRAME_FLOOR = 6000


def _dig(doc: dict, path: str) -> list:
    node: Any = doc
    for part in path.split("."):
        node = (node or {}).get(part) if isinstance(node, dict) else None
    return node if isinstance(node, list) else []


def _words(text: str) -> set[str]:
    return {w for w in re.split(r"[^a-z0-9]+", str(text).lower()) if len(w) > 3}


def _singular_word(word: str) -> str:
    """Normalize ordinary English plurals used in plan record labels."""
    if len(word) < 4:
        return word
    if word.endswith("statuses"):
        return word[:-2]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith(("ss", "us", "is")):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def _entity_words(text: str) -> tuple[str, ...]:
    return tuple(_singular_word(word) for word in
                 re.split(r"[^a-z0-9]+", str(text).lower()) if word)


def _covered(needle: str, haystacks: list[str]) -> bool:
    """Whether some requirement plausibly speaks to this plan item.

    Deliberately generous: this is looking for the feature nobody wrote a
    requirement for, not grading how well the wording matches.
    """
    wanted = _words(needle)
    if not wanted:
        return True
    for text in haystacks:
        shared = wanted & _words(text)
        if len(shared) >= max(1, min(2, len(wanted))):
            return True
    return False


def requirement_coverage(doc: dict, plan: dict) -> list[str]:
    """Plan items with no requirement that mentions them."""
    requirements = [str(f.get("requirement", "")) for f in _dig(doc, "functional_requirements")]
    requirements += [str(w.get("workflow_name", "")) + " " + " ".join(w.get("steps") or [])
                     for w in _dig(doc, "business_workflows")]
    if not requirements:
        return ["the specification has no functional requirements at all"]

    gaps: list[str] = []
    for feature in [str(f) for f in (plan.get("features") or []) if str(f).strip()]:
        if not _covered(feature, requirements):
            gaps.append(f"no functional requirement covers the plan feature: {feature!r}")
    for flow in (plan.get("workflows") or []):
        name = str(flow.get("name") or "")
        if name and not _covered(name, requirements):
            gaps.append(f"no functional requirement or workflow covers the plan journey: {name!r}")
    for user in (plan.get("users") or []):
        role = str(user.get("role") or "")
        for action in (user.get("can_do") or []):
            if role and not _covered(f"{role} {action}", requirements):
                gaps.append(f"no functional requirement covers what {role} can do: {action!r}")
                break
    return gaps


def page_coverage(doc: dict, plan: dict) -> list[str]:
    """Screens the plan promised that the specification does not have."""
    routes = {str(p.get("route") or "").rstrip("/") or "/"
              for p in _dig(doc, "public_pages") + _dig(doc, "protected_pages")}
    names = {str(p.get("page_name") or "").lower()
             for p in _dig(doc, "public_pages") + _dig(doc, "protected_pages")}
    gaps = []
    for screen in (plan.get("screens") or []):
        route = str(screen.get("route") or "").rstrip("/") or "/"
        name = str(screen.get("name") or "")
        if route not in routes and name.lower() not in names:
            gaps.append(f"the plan's screen {name!r} ({route}) is not in the specification's pages")
    return gaps


def table_coverage(doc: dict, plan: dict) -> list[str]:
    """Records the plan promised that the database design does not have."""
    tables = {_entity_words(str(t.get("table_name") or ""))
              for t in _dig(doc, "database_design.tables")}
    gaps = []
    for record in (plan.get("records") or []):
        name = _entity_words(str(record.get("name") or ""))
        if not name:
            continue
        if name not in tables:
            gaps.append(f"the plan's record {record.get('name')!r} has no table in database_design")
    return gaps

# Optional-in-the-schema sections a well-formed SRS is still expected to
# carry — every one of them can be legitimately empty for a given product (an
# app with one role has no interesting access matrix), so this is a readout
# the reviewer weighs alongside its own judgement, never a gate on its own.
STRUCTURAL_SECTIONS = (
    ("security_requirements", "security requirements"),
    ("acceptance_criteria", "acceptance criteria"),
    ("validation_rules", "field validation rules"),
    ("risk_priority", "risk and priority ranking"),
    ("assumptions", "assumptions"),
    ("constraints", "constraints"),
    ("role_access_matrix", "role access matrix"),
    ("api_design", "API design"),
)


def section_completeness(doc: dict) -> dict:
    """Which structurally-expected sections carry real content."""
    populated = [label for key, label in STRUCTURAL_SECTIONS if _dig(doc, key)]
    empty = [label for key, label in STRUCTURAL_SECTIONS if not _dig(doc, key)]
    return {"populated": populated, "empty": empty,
            "ratio": round(len(populated) / len(STRUCTURAL_SECTIONS), 2)}


def ambiguity_resolution(doc: dict) -> dict:
    """How many identified ambiguities are still open.

    Nobody is in the room to answer a lingering question once generation is
    done, so a specification that flagged its own ambiguities should resolve
    nearly all of them (each already carries `assumption_made`, so resolving
    one means standing behind that assumption, not deleting the entry).
    """
    ambiguities = _dig(doc, "ambiguities")
    if not ambiguities:
        return {"total": 0, "resolved": 0, "rate": 1.0}
    resolved = sum(1 for a in ambiguities if not a.get("needs_clarification"))
    return {"total": len(ambiguities), "resolved": resolved,
            "rate": round(resolved / len(ambiguities), 2)}


def traceability_coverage(doc: dict) -> list[str]:
    """Requirements that trace to nothing."""
    traced = {str(row.get("requirement_id")) for row in
              _dig(doc, "requirement_traceability_matrix")}
    missing = [str(f.get("id")) for f in _dig(doc, "functional_requirements")
               if str(f.get("id")) not in traced]
    if missing:
        return [f"these requirements are in no traceability row: {', '.join(missing[:8])}"]
    return []


def _page_weight(doc: dict, route: str) -> int:
    """How much page the specification says this route carries."""
    for page in _dig(doc, "public_pages") + _dig(doc, "protected_pages"):
        if str(page.get("route") or "").rstrip("/") == route.rstrip("/"):
            return max(1, len(page.get("sections") or [])
                       + len(page.get("functions") or []) // 2)
    return 3


def wireframe_depth(pages: list[tuple[str, str]], doc: dict | None = None) -> list[str]:
    """Wireframes drawn without the skill's design system, or without a page on them."""
    doc = doc or {}
    gaps = []
    for route, html in pages:
        text = (html or "").strip()
        weight = _page_weight(doc, route)
        expected = max(WIREFRAME_FLOOR, weight * WIREFRAME_CHARS_PER_SECTION)

        if not text.lower().startswith(WIREFRAME_MARKERS):
            gaps.append(f"the wireframe for {route} is not a complete HTML document — "
                        f"it must open with <!DOCTYPE html> and carry its own <head> "
                        f"and inline <style>")
            continue
        if len(text) < expected:
            gaps.append(f"the wireframe for {route} is {len(text):,} characters, but the "
                        f"specification gives that page {weight} section(s) and "
                        f"function(s) to draw — draw the whole screen: its shell, every "
                        f"section, every control its functions need, and its loading, "
                        f"empty and error states, with realistic sample content "
                        f"throughout (aim for {expected:,}+)")
        if "<style" not in text.lower():
            gaps.append(f"the wireframe for {route} has no inline <style> block, so it "
                        f"renders unstyled — the document must carry its own CSS")
    return gaps


def check_document(doc: dict, plan: dict) -> list[str]:
    """Plan coverage and traceability, before any diagrams or pages are drawn."""
    gaps: list[str] = []
    gaps += page_coverage(doc, plan)
    gaps += table_coverage(doc, plan)
    gaps += requirement_coverage(doc, plan)
    gaps += traceability_coverage(doc)
    return gaps


def as_instructions(gaps: list[str]) -> str:
    return "\n".join(f"- {gap}" for gap in gaps)
