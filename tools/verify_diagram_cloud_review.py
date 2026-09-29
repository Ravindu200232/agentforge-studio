"""Run one real, isolated cloud-model diagram-review smoke test.

It creates only a temporary workspace, renders a small valid UML class diagram,
then exercises the same `_review_diagram()` call used by SRS generation.  It
does not access customer workspaces or print model credentials.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in ("", "src", "srs-agent", ".deps"):
    candidate = str(ROOT / folder) if folder else str(ROOT)
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from server_modules import mermaid
from srs_agent import document


SOURCE = '''classDiagram
class Booking {
  + id: UUID
  + customer_id: UUID
}
class Customer {
  + id: UUID
}
Customer "1" --> "0..*" Booking : places
'''


def main() -> int:
    problems = mermaid.problems("class_object", SOURCE)
    if problems:
        raise ValueError("test diagram did not satisfy static guard: " + "; ".join(problems))
    if not mermaid.available():
        raise RuntimeError("Mermaid CLI is unavailable; install the existing project dependency first")

    with tempfile.TemporaryDirectory(prefix="agentforge-diagram-review-") as temp:
        workspace = Path(temp)
        context = workspace / ".agentforge" / "srs" / "diagram-context" / "class_object.json"
        context.parent.mkdir(parents=True)
        context.write_text(json.dumps({
            "app_summary": {"app_name": "Booking service"},
            "roles": [{"role_name": "Customer"}],
            "database_design": {"tables": [
                {"table_name": "customers", "fields": [{"name": "id", "type": "uuid"}]},
                {"table_name": "bookings", "fields": [
                    {"name": "id", "type": "uuid"}, {"name": "customer_id", "type": "uuid"}]}
            ], "relationships": [{"from": "bookings.customer_id", "to": "customers.id", "type": "many_to_one"}]}
        }, indent=2), encoding="utf-8")
        svg = workspace / "class-object.svg"
        rendered, reason = mermaid.render(SOURCE, svg)
        if not rendered:
            raise RuntimeError(reason)
        review = document._review_diagram("diagram-review-smoke", workspace,
                                          "class_object", SOURCE, context)
    print(json.dumps({"rendered": True, "review": review}, indent=2))
    return 0 if review.get("verdict") == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
