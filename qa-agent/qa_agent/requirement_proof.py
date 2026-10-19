"""Whether each requirement is met, decided by the Studio from the journey tests' own results, never by what the builder wrote.

The builder records every requirement in `build/report.json` while it builds, before a single test has run; one store's 116
requirements stayed "untested" after all its unit and journey tests had passed, and the Testing screen said 0/116 met. Each
requirement's row in the specification's traceability matrix names the pages it lives on, and each journey of the journey
contract names the page of every step. A requirement is:

- met: every page it names is passed through by a journey whose desktop test passed;
- failed: a page it names is passed through only by journeys that failed (or have no test);
- untested: a page it names is on no journey at all.

A test that names the requirement in its title (`[FR-031] lists the suppliers`, the tests the build writes for a page no
journey goes through) decides it on its own: met when it passed at desktop width, failed when it did not.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from server_modules import journeys as journey_contracts
from server_modules.validation.completeness import route_key

SRS = Path(".agentforge") / "srs" / "srs.json"


def _trace(workspace: Path) -> dict[str, list[str]]:
    try:
        data = json.loads((workspace / SRS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    doc = data.get("srs_document", data) if isinstance(data, dict) else {}
    rows = doc.get("requirement_traceability_matrix") if isinstance(doc, dict) else None
    out: dict[str, list[str]] = {}
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get("requirement_id"):
            out[str(row["requirement_id"])] = [str(p) for p in row.get("pages") or [] if str(p).strip()]
    return out


_NAMED = re.compile(r"\bFR-\d+\b")


def _named(tests: list[dict[str, Any]] | None) -> dict[str, list[dict[str, Any]]]:
    """The desktop tests that name a requirement in their title (`[FR-031] lists the suppliers`), by requirement."""
    out: dict[str, list[dict[str, Any]]] = {}
    for test in tests or []:
        if re.search(r"mobile|phone", str(test.get("project") or ""), re.I):
            continue
        for found in set(_NAMED.findall(f"{test.get('suite') or ''} {test.get('title') or ''}")):
            out.setdefault(found, []).append(test)
    return out


def statuses(workspace: Path, coverage: dict[str, Any] | None,
             tests: list[dict[str, Any]] | None = None) -> dict[str, dict[str, str]]:
    """{requirement id: {"status", "evidence"}} for every requirement the traceability matrix names; {} without a journey
    contract or journey results to judge by. A test that names the requirement itself decides it; otherwise the journeys
    through its pages do."""
    contract = journey_contracts.read_journey_contract(workspace)
    if not contract or not isinstance(coverage, dict):
        return {}
    named = _named(tests)
    result = {str(row.get("id")): str(row.get("status")) if row.get("tests") else "missing"
              for row in coverage.get("journeys") or [] if isinstance(row, dict)}
    through: dict[str, list[str]] = {}
    for journey in contract.get("journeys") or []:
        for step in journey.get("steps") or []:
            if isinstance(step, dict) and step.get("route"):
                ids = through.setdefault(route_key(step["route"]), [])
                if journey["id"] not in ids:
                    ids.append(str(journey["id"]))
    out: dict[str, dict[str, str]] = {}
    for requirement, pages in _trace(workspace).items():
        own = named.get(requirement) or []
        if own:
            bad = [t for t in own if str(t.get("status")) != "passed"]
            shown = "; ".join(f"{t.get('file')}: {t.get('title')}" for t in (bad or own)[:3])
            out[requirement] = ({"status": "failed", "evidence": f"Its own test failed: {shown}."} if bad else
                                {"status": "met", "evidence": f"Its own test passed (desktop): {shown}."})
            continue
        proved, failing, untouched = {}, {}, []
        for page in pages:
            ids = through.get(route_key(page), [])
            passed = [j for j in ids if result.get(j) == "passed"]
            if passed:
                proved[page] = passed
            elif ids:
                failing[page] = ids
            else:
                untouched.append(page)
        if not pages:
            out[requirement] = {"status": "untested", "evidence": "Its traceability row names no page, so no journey can prove it."}
        elif failing:
            out[requirement] = {"status": "failed", "evidence": "; ".join(
                f"{page}: {', '.join(f'{j} ({result.get(j, 'missing')})' for j in ids)}" for page, ids in failing.items())
                + " — no journey through it passed."}
        elif untouched:
            out[requirement] = {"status": "untested", "evidence": f"No journey passes through {', '.join(untouched)}."}
        else:
            out[requirement] = {"status": "met", "evidence": "Passed journey tests (desktop) through each of its pages: " + "; ".join(
                f"{page} by {', '.join(ids[:3])}" for page, ids in proved.items()) + "."}
    return out


def apply(workspace: Path, build: dict[str, Any], coverage: dict[str, Any] | None,
          tests: list[dict[str, Any]] | None = None) -> int:
    """Set each requirement of the build report from the test results (in place); returns how many changed."""
    found = statuses(workspace, coverage, tests)
    changed = 0
    for row in build.get("requirements") or []:
        if isinstance(row, dict) and str(row.get("id")) in found:
            new = found[str(row["id"])]
            if row.get("status") != new["status"] or row.get("evidence") != new["evidence"]:
                row.update(new, decided_by="studio")
                changed += 1
    return changed
