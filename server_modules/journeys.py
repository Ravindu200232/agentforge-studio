"""The workflows as journeys, each step tied to the page it happens on.

Ported from RP-SE-009 `srs-agent/srs_agent/app/generators/wireframes.py`. The
steps are the specification's own; what is added is which screen each one lands
on, so a journey reads as a path through the wireframes rather than as a
paragraph beside them.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


JOURNEY_SCHEMA = "agentforge.user-journeys/v1"
JOURNEY_ARTIFACT = ".agentforge/srs/user-journeys.json"


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


def journey_contract_for(doc: dict) -> dict[str, Any]:
    """The stable, product-only journey contract derived from the final SRS.

    This deliberately has no instructions for wireframes, prototypes, builds or
    test runners. It says only who takes which product actions and where. The
    QA stage uses its stable IDs to prove that every specified journey has a
    real E2E test rather than trusting a generic test count.
    """
    pages = _pages_of(doc)
    actors = _actors_of(doc)
    out: list[dict[str, Any]] = []
    for number, flow in enumerate(doc.get("business_workflows") or [], 1):
        if not isinstance(flow, dict):
            continue
        journey_id = f"UJ-{number:03d}"
        steps = [{"id": f"{journey_id}-S{index:02d}", "step": str(step),
                  "route": _route_for_step(str(step), pages, actors), "named": True}
                 for index, step in enumerate(flow.get("steps") or [], 1)]
        _carry_routes(steps)
        out.append({"id": journey_id,
                    "workflow_name": str(flow.get("workflow_name") or f"Workflow {number}"),
                    "who": str(flow.get("who") or "") or None,
                    "steps": steps})
    return {"schema": JOURNEY_SCHEMA, "journeys": out}


def user_journeys_for(doc: dict) -> list[dict[str, Any]]:
    """Every business workflow, as a path through the pages."""
    return journey_contract_for(doc)["journeys"]


def read_journey_contract(workspace: Path) -> dict[str, Any] | None:
    """Read a generated journey contract without treating a malformed file as valid."""
    path = workspace / JOURNEY_ARTIFACT
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict) or raw.get("schema") != JOURNEY_SCHEMA:
        return None
    rows = raw.get("journeys")
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not row.get("id") for row in rows):
        return None
    return raw


def e2e_coverage(workspace: Path, tests: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Map real Playwright result titles to the generated journey IDs.

    The builder must name each user-journey test with its UJ id (for example,
    ``[UJ-001] Customer places an order``). Generic route smoke, visual and
    accessibility tests are intentionally not substitutes for this proof.
    """
    contract = read_journey_contract(workspace)
    if contract is None:
        return None

    rows: list[dict[str, Any]] = []
    for journey in contract["journeys"]:
        journey_id = str(journey["id"])
        matcher = re.compile(rf"(?<![A-Z0-9-]){re.escape(journey_id)}(?![A-Z0-9-])", re.I)
        # A suite name is part of Playwright's displayed test title, while a
        # filename is not enough: `UJ-001.spec.js` with an unrelated test
        # body must not be accepted as real journey coverage.
        matched = [test for test in tests if matcher.search(" ".join(
            str(test.get(part) or "") for part in ("suite", "title")))]
        statuses = [str(test.get("status") or "unknown") for test in matched]
        status = "passed" if matched and all(value == "passed" for value in statuses) else "failed"
        rows.append({"id": journey_id, "workflow_name": journey.get("workflow_name") or journey_id,
                     "status": status, "tests": [{"file": test.get("file") or "",
                                                      "title": test.get("title") or "",
                                                      "status": test.get("status") or "unknown"}
                                                     for test in matched]})

    missing = [row["id"] for row in rows if not row["tests"]]
    failed = [row["id"] for row in rows if row["tests"] and row["status"] != "passed"]
    return {"required": len(rows), "covered": len(rows) - len(missing),
            "passed": sum(row["status"] == "passed" for row in rows),
            "missing": missing, "failed": failed, "journeys": rows,
            "status": "passed" if not missing and not failed else "failed"}
