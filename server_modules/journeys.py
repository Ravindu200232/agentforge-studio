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


# Role words that mean "someone who never signs in".
_PUBLIC_ROLES = {"visitor", "guest", "anonymous", "public", "anyone", "everyone"}


def _norm(value: Any) -> str:
    """A role or page name compared loosely: `store_owner`, `Store Owner` and `store-owner` are one name."""
    return re.sub(r"[\s_-]+", " ", str(value or "")).strip().lower()


def _items(value: Any) -> list[str]:
    """Names given as a list, or as one string separated by commas, semicolons or bars."""
    items = value if isinstance(value, (list, tuple, set)) else re.split(r"[,;|\n]+", str(value or ""))
    return [str(item).strip() for item in items if str(item).strip()]


def _route_key(route: Any) -> str:
    return str(route or "").strip().rstrip("/") or "/"


def _pages_of(doc: dict) -> list[dict[str, Any]]:
    return [{"route": str(p.get("route") or ""), "page_name": str(p.get("page_name") or ""),
             "login_required": bool(p.get("login_required")),
             "roles": {_norm(role) for role in _items(p.get("allowed_roles"))}}
            for p in ((doc.get("public_pages") or []) + (doc.get("protected_pages") or []))
            if isinstance(p, dict) and str(p.get("route") or "").strip()]


def _role_names(doc: dict, who: Any) -> tuple[set[str], bool]:
    """Every name of the role(s) a workflow's `who` refers to, and whether that is only someone who never signs in.

    An empty set means `who` names no declared role, so nothing about access can be assumed from it.
    """
    parts = {_norm(part) for part in re.split(r"[,/;&]|\bor\b|\band\b", str(who or ""), flags=re.I)} - {""}
    if not parts:
        return set(), False
    names: set[str] = set()
    for role in doc.get("roles") or []:
        if not isinstance(role, dict):
            continue
        known = {_norm(role.get(key)) for key in ("role_key", "role_name", "name")} - {""}
        if known & parts or {name + "s" for name in known} & parts:
            names |= known
    if not names:
        visitors = parts & _PUBLIC_ROLES
        return visitors, bool(visitors) and parts <= _PUBLIC_ROLES
    return names, names <= _PUBLIC_ROLES


def open_to(doc: dict, who: Any, pages: list[dict] | None = None) -> list[dict]:
    """The pages a workflow's role can open: every page without sign-in, and the signed-in pages that name the role.

    A signed-in page that names no role is open to every signed-in role. Someone who never signs in opens only the pages
    without sign-in. A `who` that names no declared role can open every page, since nothing says otherwise.
    """
    pages = _pages_of(doc) if pages is None else pages
    names, public = _role_names(doc, who)
    if not names:
        return pages
    return [page for page in pages if not page["login_required"] or (
        not public and (not page["roles"] or names & page["roles"] or page["roles"] & {"anyone", "all", "everyone"}))]


def _phrase(name: str) -> re.Pattern[str] | None:
    """A page name as a phrase in a sentence, singular or plural: `My Orders` matches "my order" and "my orders"."""
    words = re.findall(r"[a-z0-9]+", name.lower())
    if not words:
        return None
    stems = [re.sub(r"(?:es|s)$", "", word) if len(word) > 3 else word for word in words]
    return re.compile(r"\b" + r"\W+".join(re.escape(stem) + r"(?:e?s)?" for stem in stems) + r"\b", re.I)


def _route_for_step(step: str, pages: list[dict]) -> str:
    """The page a step names, or "" when it names none.

    Only a page named in the step counts — the first one it mentions, the longest name when two start at the same place.
    A step that names no page happens where the person already is; `_carry_routes` puts it there rather than guessing
    from a single shared word.
    """
    best, best_at, best_len = "", None, 0
    for page in pages:
        pattern = _phrase(page["page_name"])
        found = pattern.search(step) if pattern else None
        if not found:
            continue
        if best_at is None or found.start() < best_at or (found.start() == best_at and len(found.group(0)) > best_len):
            best, best_at, best_len = page["route"], found.start(), len(found.group(0))
    return best


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


def trim_step_routes(doc: dict) -> int:
    """Drop `step_routes` beyond a workflow's steps: a route for a step that does not exist names nothing."""
    trimmed = 0
    for flow in doc.get("business_workflows") or []:
        if isinstance(flow, dict) and isinstance(flow.get("step_routes"), list):
            extra = len(flow["step_routes"]) - len(flow.get("steps") or [])
            if extra > 0:
                flow["step_routes"] = flow["step_routes"][:len(flow.get("steps") or [])]
                trimmed += extra
    return trimmed


def journey_issues(doc: dict) -> list[dict[str, Any]]:
    """Every step whose SRS route is missing, is no page, or is a page the workflow's role cannot open — one row per step."""
    pages = _pages_of(doc)
    known = {_route_key(page["route"]) for page in pages}
    issues: list[dict[str, Any]] = []
    for number, flow in enumerate(doc.get("business_workflows") or [], 1):
        if not isinstance(flow, dict):
            continue
        name = str(flow.get("workflow_name") or f"Workflow {number}")
        who = str(flow.get("who") or "")
        given = [str(route or "").strip() for route in flow.get("step_routes") or []]
        allowed = {_route_key(page["route"]) for page in open_to(doc, who, pages)}
        for index, step in enumerate(flow.get("steps") or [], 1):
            route = given[index - 1] if index <= len(given) else ""
            if not route:
                why = "has no route"
            elif _route_key(route) not in known:
                why = f"is on {route}, which is not a page"
            elif _route_key(route) not in allowed:
                why = f"is on {route}, which {who or 'its role'} cannot open"
            else:
                continue
            issues.append({"workflow": name, "who": who, "step": index, "text": str(step), "route": route,
                           "problem": f'"{name}" step {index} {why}'})
    return issues


def journey_contract_for(doc: dict) -> dict[str, Any]:
    """The stable, product-only journey contract derived from the final SRS.

    This deliberately has no instructions for wireframes, prototypes, builds or
    test runners. It says only who takes which product actions and where. The
    QA stage uses its stable IDs to prove that every specified journey has a
    real E2E test rather than trusting a generic test count.

    Each step's page is the SRS's own `step_routes` entry when that is a page the workflow's role can open; otherwise the
    page the step names, among the pages that role can open; otherwise the page the person is already on.
    """
    pages = _pages_of(doc)
    out: list[dict[str, Any]] = []
    for number, flow in enumerate(doc.get("business_workflows") or [], 1):
        if not isinstance(flow, dict):
            continue
        journey_id = f"UJ-{number:03d}"
        allowed = open_to(doc, flow.get("who"), pages)
        by_key = {_route_key(page["route"]): page["route"] for page in allowed}
        given = [str(route or "") for route in flow.get("step_routes") or []]
        steps = []
        for index, step in enumerate(flow.get("steps") or [], 1):
            declared = by_key.get(_route_key(given[index - 1])) if index <= len(given) and given[index - 1] else ""
            steps.append({"id": f"{journey_id}-S{index:02d}", "step": str(step),
                          "route": declared or _route_for_step(str(step), allowed), "named": True})
        _carry_routes(steps)
        out.append({"id": journey_id,
                    "workflow_name": str(flow.get("workflow_name") or f"Workflow {number}"),
                    "who": str(flow.get("who") or "") or None,
                    "steps": steps})
    return {"schema": JOURNEY_SCHEMA, "journeys": out}


def fill_step_routes(doc: dict) -> int:
    """Write every workflow's validated `step_routes` back into the SRS; how many steps changed."""
    changed = 0
    flows = [flow for flow in doc.get("business_workflows") or [] if isinstance(flow, dict)]
    for flow, journey in zip(flows, journey_contract_for(doc)["journeys"]):
        routes = [step["route"] for step in journey["steps"]]
        before = [str(route or "") for route in flow.get("step_routes") or []]
        changed += sum(1 for index, route in enumerate(routes) if index >= len(before) or before[index] != route)
        flow["step_routes"] = routes
    return changed


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
                     "who": journey.get("who") or "",
                     "steps": [str(step.get("step") or "") for step in journey.get("steps") or []
                               if isinstance(step, dict)],
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
