"""A readable journey brief and its matching browser-runner input."""
from __future__ import annotations

from server_modules import journeys

from . import journey_walk

SNAPSHOT = "journeys.json"
GUIDE = "journeys.md"


def from_spec(session, doc: dict) -> list[dict]:
    saved = session.read_record("srs", "user-journeys.json", fallback=None)
    contract = saved if isinstance(saved, dict) else journeys.journey_contract_for(doc)
    return journey_walk.normalize_journeys(contract, bounded=False)


def markdown(planned: list[dict], rows: list[dict]) -> str:
    files = {row["route"]: row["file"] for row in rows}
    parts = ["# Prototype journeys", "",
             "The prototype and its browser walkthrough use these approved roles, steps and routes. "
             "For each step, verify the described action and the resulting visible state.", ""]
    if not planned:
        parts.append("The approved specification contains no user journeys.")
    for journey in planned:
        parts.extend([f"## {journey['id']} · {journey['name']}", "", f"Role: {journey['who'] or 'Unspecified'}", ""])
        for number, step in enumerate(journey["steps"], 1):
            where = step["route"] or "Route unspecified"
            file = files.get(journey_walk.page_route(step["route"], rows)) if step["route"] else None
            source = f" · `{file}`" if file else ""
            parts.append(f"{number}. **{step['id']}** · `{where}`{source} · {step['step']}")
            if step.get("expected_outcome"):
                parts.append(f"   - Expected: {step['expected_outcome']}")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def for_page(planned: list[dict], row: dict, rows: list[dict]) -> str:
    blocks = []
    for journey in planned:
        steps = journey["steps"]
        matches = [i for i, step in enumerate(steps)
                   if step["route"] and journey_walk.page_route(step["route"], rows) == row["route"]]
        if not matches:
            continue
        blocks.append(f"- **{journey['id']} · {journey['name']}** · {journey['who'] or 'Role unspecified'}")
        for i in matches:
            step = steps[i]
            expected = f" Expected outcome: {step['expected_outcome']}" if step.get("expected_outcome") else ""
            next_route = steps[i + 1]["route"] if i + 1 < len(steps) else ""
            onward = f" Next step is on `{next_route}`." if next_route and next_route != row["route"] else ""
            blocks.append(f"  - {step['id']}: {step['step']}{expected}{onward}")
    return "\n".join(blocks) or "This screen has no mapped journey steps. Implement its approved SRS requirements."
