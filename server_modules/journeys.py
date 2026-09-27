"""The workflows as journeys, each step tied to the page it happens on.

Ported from RP-SE-009 `srs-agent/srs_agent/app/generators/wireframes.py`. The
steps are the specification's own; what is added is which screen each one lands
on, so a journey reads as a path through the wireframes rather than as a
paragraph beside them.
"""
from __future__ import annotations

import re
from typing import Any


def _pages_of(doc: dict) -> list[dict[str, str]]:
    return [{"route": str(p.get("route") or ""), "page_name": str(p.get("page_name") or "")}
            for p in ((doc.get("public_pages") or []) + (doc.get("protected_pages") or []))
            if isinstance(p, dict)]


def _actors_of(doc: dict) -> set[str]:
    actors: set[str] = set()
    for role in (doc.get("roles") or []):
        if isinstance(role, dict):
            for value in (role.get("role_key"), role.get("role_name"), role.get("name")):
                actors |= {w for w in re.findall(r"[a-z]{4,}", str(value or "").lower())}
    return actors


def _route_for_step(step: str, pages: list[dict], actors: set[str]) -> str:
    """The page whose name this step's words point at, or ""."""
    low = step.lower()
    best, best_score = "", 0
    for page in pages:
        words = [w for w in re.findall(r"[a-z]{3,}", page["page_name"].lower())
                 if w not in actors]
        if not words:
            continue
        # A five-character stem, so "schedule" matches "scheduled".
        score = sum(len(w) for w in words if re.search(rf"\b{re.escape(w[:5])}", low))
        if score > best_score:
            best, best_score = page["route"], score
    return best if best_score else ""


def _carry_routes(steps: list[dict]) -> None:
    """A step that names no screen happens on the one before it.

    Workflow steps are sequential and a person stays where they are until
    something moves them, so "the system checks the pickup date is free" happens
    on the page the order was placed from. Carried rather than guessed, and
    marked `named: False` so the studio can show an inherited route as the weaker
    claim it is.
    """
    for index, step in enumerate(steps):
        if step["route"]:
            continue
        step["named"] = False
        backward = next((s["route"] for s in reversed(steps[:index]) if s["route"]), "")
        forward = next((s["route"] for s in steps[index + 1:] if s["route"]), "")
        step["route"] = backward or forward


def user_journeys_for(doc: dict) -> list[dict[str, Any]]:
    """Every business workflow, as a path through the pages."""
    pages = _pages_of(doc)
    actors = _actors_of(doc)
    out: list[dict[str, Any]] = []
    for flow in (doc.get("business_workflows") or []):
        if not isinstance(flow, dict):
            continue
        steps = [{"step": str(step), "route": _route_for_step(str(step), pages, actors),
                  "named": True} for step in (flow.get("steps") or [])]
        _carry_routes(steps)
        out.append({"workflow_name": str(flow.get("workflow_name") or "Workflow"),
                    "who": str(flow.get("who") or "") or None,
                    "steps": steps})
    return out
