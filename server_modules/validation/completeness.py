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

# Evidence in the document that makes a diagram answerable. A diagram marked
# not-applicable while its evidence is present is a diagram that was skipped.
DIAGRAM_EVIDENCE = {
    "erd": ("database_design.tables", 1),
    "system_context": ("roles", 1),
    "use_case": ("roles", 1),
    "activity": ("business_workflows", 1),
    "sequence": ("business_workflows", 1),
    "dfd": ("database_design.tables", 1),
}


class Gaps(ValueError):
    """What is missing, phrased as the repair instructions for the agent."""


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


def diagram_coverage(doc: dict) -> list[str]:
    """Diagrams marked not-applicable while their own evidence is in the document."""
    drawn = {str(d.get("kind")): d for d in _dig(doc, "diagrams") if isinstance(d, dict)}
    gaps = []
    for kind, (path, floor) in DIAGRAM_EVIDENCE.items():
        evidence = len(_dig(doc, path))
        if evidence < floor:
            continue
        diagram = drawn.get(kind)
        if diagram is None:
            gaps.append(f"there is no {kind} diagram, though the document has "
                        f"{evidence} {path.split('.')[-1]} to draw it from")
        elif diagram.get("applicable") is False:
            gaps.append(f"the {kind} diagram is marked not applicable, but the document "
                        f"has {evidence} {path.split('.')[-1]} — draw it")
        elif not str(diagram.get("source") or "").strip():
            gaps.append(f"the {kind} diagram has no mermaid `source`")
    return gaps


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


def prototype_coverage(doc: dict, routes: list[dict], pages: dict[str, str],
                       tokens: dict | None = None) -> list[str]:
    """Whether the prototype is the product the specification describes.

    The same three failures as the wireframes, one layer up: a screen that was
    never drawn, a screen drawn as a stub, and a design contract that was agreed
    and then ignored.
    """
    gaps: list[str] = []
    drawn = {str(r.get("route") or "").rstrip("/") or "/" for r in routes}

    for page in _dig(doc, "public_pages") + _dig(doc, "protected_pages"):
        route = str(page.get("route") or "").rstrip("/") or "/"
        if route not in drawn:
            gaps.append(f"the specification's page {page.get('page_name')!r} ({route}) "
                        f"has no prototype screen and no entry in routes.json")

    for row in routes:
        route = str(row.get("route") or "")
        html = pages.get(str(row.get("file") or ""), "")
        if not html:
            gaps.append(f"routes.json points {route} at {row.get('file')!r}, "
                        f"which is not in the prototype folder")
            continue
        weight = _page_weight(doc, route)
        expected = max(900, weight * 400)
        if len(html) < expected:
            gaps.append(f"the prototype screen for {route} is {len(html)} characters, but "
                        f"the specification gives that page {weight} section(s) and "
                        f"function(s) — draw the whole screen: its working views, its "
                        f"table with real rows, its form with validation states, and its "
                        f"loading, empty and error states")

    # Every link between screens has to land somewhere, or the reviewer clicks
    # into nothing and learns the product is broken when it is not.
    known_files = set(pages)
    for row in routes:
        html = pages.get(str(row.get("file") or ""), "")
        for href in re.findall(r'href\s*=\s*"([^"#?:]+\.html)"', html):
            target = href.split("/")[-1]
            if target not in known_files:
                gaps.append(f"the prototype screen for {row.get('route')} links to "
                            f"{href!r}, which does not exist")

    # The kit turns `data-go="/route"` into a link, so a route that is not in routes.json is as dead as a missing file.
    for row in routes:
        html = pages.get(str(row.get("file") or ""), "")
        for go in sorted(set(re.findall(r'data-go\s*=\s*"([^"]*)"', html))):
            if (go.rstrip("/") or "/") not in drawn:
                gaps.append(f"the prototype screen for {row.get('route')} goes to {go!r} (data-go), "
                            f"which is not a route in routes.json")

    palette = (tokens or {}).get("light") or (tokens or {}).get("dark") or {}
    if palette:
        stylesheet = pages.get("assets/app.css", "")
        missing = [name for name in list(palette)[:6]
                   if f"--{name}" not in stylesheet and str(palette[name]) not in stylesheet]
        if stylesheet and missing:
            gaps.append("assets/app.css does not carry the approved design tokens "
                        f"({', '.join(missing)}) — apply the design spec literally, "
                        "because what the customer approves here is what the build must match")
    return gaps


def check_document(doc: dict, plan: dict) -> list[str]:
    """Plan coverage and traceability, before any diagrams or pages are drawn."""
    gaps: list[str] = []
    gaps += page_coverage(doc, plan)
    gaps += table_coverage(doc, plan)
    gaps += requirement_coverage(doc, plan)
    gaps += traceability_coverage(doc)
    return gaps


def check(doc: dict, plan: dict, pages: list[tuple[str, str]]) -> list[str]:
    """Every gap between the plan, the specification and the drawings."""
    gaps = check_document(doc, plan)
    gaps += diagram_coverage(doc)
    gaps += wireframe_depth(pages, doc)
    return gaps


def as_instructions(gaps: list[str]) -> str:
    return "\n".join(f"- {gap}" for gap in gaps)
