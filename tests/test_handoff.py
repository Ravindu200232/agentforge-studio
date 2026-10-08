"""The handoff: a small app.md in the customer's words and a technical builder.md, and nothing else."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from srs_agent import document as srs_document  # noqa: E402
from srs_agent import handoff  # noqa: E402

DOC = {
    "project_name": "Bakery",
    "app_summary": {"app_name": "Sweet Crumbs", "short_description": "Order cakes online and collect them in the shop.",
                    "business_goal": "Take orders without phone calls.", "target_users": ["Shoppers", "Bakery staff"]},
    "roles": [{"role_key": "customer", "role_name": "Customer", "description": "Orders cakes"},
              {"role_key": "baker", "role_name": "Baker", "description": "Prepares the orders"}],
    "public_pages": [{"page_name": "Home", "route": "/", "sections": ["hero", "cake list"], "functions": ["browse cakes"]}],
    "protected_pages": [{"page_name": "Orders", "route": "/orders", "allowed_roles": ["baker"],
                         "sections": ["order table"], "functions": ["mark an order ready"]}],
    "business_workflows": [{"workflow_name": "Ordering a cake", "who": "Customer",
                            "steps": ["open Home", "see the orders"], "step_routes": ["/", "/orders"]}],
    "database_design": {"tables": [{"table_name": "cake_orders", "description": "One row per order",
                                    "fields": [{"name": "id", "type": "uuid", "primary_key": True}]}]},
    "api_design": [{"method": "GET", "path": "/api/orders", "auth_required": True, "allowed_roles": ["baker"],
                    "description": "List orders"}],
    "functional_requirements": [{"id": "FR-001", "requirement": "A customer can order a cake", "module": "orders",
                                 "priority": "high"}],
    "non_functional_requirements": [{"id": "NFR-001", "category": "speed", "requirement": "Pages open in two seconds"}],
    "acceptance_criteria": [{"criterion": "An order shows up for the baker"}],
}
IDEA = "I want a site where people order birthday cakes and pick them up."
SAID = "Q: Who uses it?\nA: Shoppers and the two bakers"


class AppMdTests(unittest.TestCase):
    def test_there_are_two_handoff_files_and_no_prototype_or_sitemap_file(self):
        self.assertEqual(handoff.HANDOFF_FILES, ("app.md", "builder.md"))
        self.assertEqual(sorted(handoff.render_all(DOC, "nextjs-mongo", IDEA, SAID)), ["app.md", "builder.md"])

    def test_it_holds_what_the_customer_said_in_their_own_words(self):
        text = handoff.app_md(DOC, IDEA, SAID)
        self.assertIn("# Sweet Crumbs", text)
        self.assertIn("## What the customer asked for\n\n" + IDEA, text)
        self.assertIn("## What the customer said when asked\n\n" + SAID, text)
        self.assertIn("- **Baker** — Prepares the orders", text)

    def test_it_holds_the_site_map_and_how_people_move_through_it(self):
        text = handoff.app_md(DOC, IDEA, SAID)
        self.assertIn("## Site map", text)
        self.assertIn("| Home | `/` | hero, cake list | browse cakes |", text)
        self.assertIn("| Orders | `/orders` | baker | order table | mark an order ready |", text)
        self.assertIn("1. open Home — on `/`", text)
        self.assertIn("2. see the orders — on `/orders`", text)

    def test_nothing_technical_is_in_it(self):
        text = handoff.app_md(DOC, IDEA, SAID)
        for technical in ("cake_orders", "/api/orders", "FR-001", "NFR-001", "uuid", "## Data", "## API",
                          "Functional requirements", "Acceptance criteria", "`customer`"):
            self.assertNotIn(technical, text)

    def test_it_is_a_small_document(self):
        self.assertLess(len(handoff.app_md(DOC, IDEA, SAID)), len(handoff.builder_md(DOC, "nextjs-mongo")) // 2)

    def test_without_the_customers_words_it_has_no_empty_sections(self):
        for said in ("", "(nothing yet)"):
            text = handoff.app_md(DOC, "", said)
            self.assertNotIn("What the customer asked for", text)
            self.assertNotIn("What the customer said when asked", text)
        self.assertIn("## Site map", text)


class BuilderMdTests(unittest.TestCase):
    def test_it_carries_the_whole_specification(self):
        text = handoff.builder_md(DOC, "nextjs-mongo")
        self.assertIn("**Selected stack**: nextjs-mongo.", text)
        for technical in ("# The specification", "## Data", "`cake_orders`", "## API", "/api/orders", "FR-001", "NFR-001",
                          "## Roles", "## Done means"):
            self.assertIn(technical, text)

    def test_it_sends_the_developer_to_app_md_and_the_react_prototype(self):
        text = handoff.builder_md(DOC, "nextjs-mongo")
        self.assertIn("`app.md`", text)
        self.assertIn(".agentforge/prototype/app/", text)
        self.assertNotIn("sitemap.md", text)
        self.assertNotIn("HTML", text)


class WritingTheHandoffTests(unittest.TestCase):
    def test_the_idea_and_the_interview_reach_app_md_and_both_files_are_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            session = SimpleNamespace(
                workspace=workspace,
                record_path=lambda *parts: (workspace / ".agentforge" / Path(*parts)).resolve(),
                write_record=lambda *parts, data=None: (workspace / ".agentforge" / Path(*parts)))
            for folder in ("srs/handoff", "srs"):
                (workspace / ".agentforge" / folder).mkdir(parents=True, exist_ok=True)
            with mock.patch.object(srs_document.bus, "file_written"), mock.patch.object(srs_document.bus, "log"), \
                    mock.patch.object(srs_document.llm, "complete", return_value="Build it."), \
                    mock.patch("srs_agent.interview.full_transcript", return_value=SAID):
                srs_document._write_handoff(session, "prj", DOC, {"stack": "nextjs-mongo", "idea": IDEA, "name": "Bakery"})
            folder = workspace / ".agentforge" / "srs" / "handoff"
            self.assertEqual(sorted(path.name for path in folder.iterdir()), ["app.md", "builder.md"])
            app = (folder / "app.md").read_text(encoding="utf-8")
            self.assertIn(IDEA, app)
            self.assertIn(SAID, app)


if __name__ == "__main__":
    unittest.main()
