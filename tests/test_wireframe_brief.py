"""What a wireframe is given: the handoff without role access and login seeding, web ideas, and one shared layout."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import llm  # noqa: E402
from srs_agent import document, wireframe_brief  # noqa: E402

SITEMAP = """# Site Map

## Public Pages

| Page | Route | Sections | Functions |
|------|-------|----------|-----------|
| Sign in | `/login` | Sign-in form, Demo accounts panel | Sign in, Send each role to its own landing page |

## Protected Pages (Login Required)

| Page | Route | Allowed Roles | Sections | Functions |
|------|-------|---------------|----------|-----------|
| Orders | `/orders` | staff, admin | Order table, Filters | Filter orders |
"""

APP = """# Application Specification

## Identity

- **App name**: Shop

## Authentication

- Sign in with email and password.
- Accounts are seeded.

## Roles

- **staff** — takes orders.

## Access

| Role | Page | Allowed |
|---|---|---|
| staff | /orders | yes |

## Data

### `orders`

| Field | Type |
|---|---|
| id | uuid |
| status | enum |

## Functional requirements

- **FR-001** [high] The system shall list orders with their status.
- **FR-002** [high] The system shall be seeded with demo credentials for each role.
- **FR-003** [high] Access control: only staff may open the order page.

## Security

- Passwords are hashed.

## UI and UX

- **layout**: table on desktop
"""

DOCS = {"app.md": APP, "sitemap.md": SITEMAP, "builder.md": "# Builder\n\nBuild it all, seeded.", "prototype.md": "# Prototype\n"}
DOC = {"app_summary": {"app_name": "Shop"}}
PAGE = {"route": "/login", "page_name": "Sign in", "page_type": "auth", "login_required": False, "allowed_roles": ["Visitor"],
        "sections": ["Sign-in form", "Demo accounts panel"], "functions": ["Sign in", "Send each role to its own landing page"]}


class CleanTests(unittest.TestCase):
    def test_role_access_and_login_seeding_are_not_carried_into_a_wireframe(self):
        text = wireframe_brief.context(DOCS)
        lowered = text.lower()
        for gone in ("seed", "demo", "credential", "allowed roles", "## access", "## authentication", "## roles", "## security",
                     "access control", "each role", "hashed"):
            self.assertNotIn(gone, lowered, gone)
        for kept in ("Sign-in form", "/login", "/orders", "Order table", "Filters", "`orders`", "status", "FR-001", "table on desktop"):
            self.assertIn(kept, text, kept)

    def test_only_the_site_map_and_the_spec_are_read_and_in_that_order(self):
        text = wireframe_brief.context(DOCS)
        self.assertLess(text.index("sitemap.md"), text.index("app.md"))
        self.assertNotIn("builder.md", text)
        self.assertNotIn("prototype.md", text)

    def test_a_table_loses_the_column_but_keeps_its_other_cells(self):
        text = wireframe_brief.clean(SITEMAP)
        self.assertNotIn("staff", text)
        self.assertIn("| Orders | `/orders` | Order table, Filters | Filter orders |", text)

    def test_the_page_record_loses_role_fields_and_role_items(self):
        facts = wireframe_brief.page_facts(PAGE)
        self.assertNotIn("allowed_roles", facts)
        self.assertNotIn("login_required", facts)
        self.assertEqual(facts["sections"], ["Sign-in form"])
        self.assertEqual(wireframe_brief.page_lines(PAGE["functions"]), ["Sign in"])

    def test_in_the_approved_plan_a_screen_keeps_its_line_and_loses_only_the_clause_about_demo_accounts(self):
        plan = ("# Shop\n\nShop lists orders. Accounts are created by the admin; there is no public sign-up.\n\n"
                "## Who uses it\n\n- **Staff** — Sign in; take orders\n\n"
                "## Screens\n\n"
                "- **Sign in** (`/login`) — Lets staff sign in with email and password and shows the demo accounts.\n"
                "- **Orders** (`/orders`) — Lists orders, with filters. _[Staff, Admin]_\n\n"
                "## What it does\n\n- Seeded demo accounts and sample orders for each role\n- Order list with filters\n\n"
                "## Assumptions\n\n- Accounts are seeded.\n")
        text = wireframe_brief.clean(plan)
        self.assertIn("- **Sign in** (`/login`) — Lets staff sign in with email and password.", text)
        self.assertIn("- **Orders** (`/orders`) — Lists orders, with filters.", text)
        self.assertIn("- Order list with filters", text)
        self.assertIn("Shop lists orders.", text)
        for gone in ("demo", "seed", "Who uses it", "_[", "sign-up", "Assumptions", "Accounts are"):
            self.assertNotIn(gone, text, gone)

    def test_a_line_that_says_who_sees_only_their_own_records_is_an_access_rule_and_is_left_out(self):
        text = wireframe_brief.clean("## What it does\n\n- Members manage only their own tasks\n- Admin overview of every task with filters\n\n"
                                     "## Functional requirements\n\n- **FR-006** [high] (My tasks, member) The system shall show a member only their own tasks.\n")
        self.assertNotIn("only their own", text)
        self.assertIn("Admin overview of every task with filters", text)

    def test_a_requirement_whose_own_lead_is_about_seeding_goes_whole_and_never_leaves_a_stump(self):
        text = wireframe_brief.clean("## Functional requirements\n\n"
                                     "- **FR-010** [high] (Seed data, staff, admin) The system shall be seeded with one admin, two members and a few tasks.\n"
                                     "- **FR-011** [high] (Orders, staff) The system shall list orders, and show each one's status.\n")
        self.assertNotIn("FR-010", text)
        self.assertNotIn("two members", text)
        self.assertIn("**FR-011** [high] (Orders, staff) The system shall list orders, and show each one's status.", text)

    def test_the_handoff_text_passed_in_is_not_changed(self):
        before = dict(DOCS)
        wireframe_brief.context(DOCS)
        self.assertEqual(DOCS, before)


class PromptTests(unittest.TestCase):
    def instruction(self, **kw):
        with mock.patch.object(document.plan_stage, "markdown", lambda project: "PLAN"):
            return document._page_instruction("prj", DOC, PAGE, DOCS, **kw)

    def test_the_page_prompt_says_nothing_about_roles_or_seeding_and_carries_ideas_and_layout(self):
        text = self.instruction(ideas="IDEA-BOARD", layout="<!-- shell: main -->")
        for gone in ("Who may open", "Sign-in required", "Demo accounts", "seeded", "allowed_roles", "role access", "role rule"):
            self.assertNotIn(gone, text, gone)
        self.assertIn("IDEA-BOARD", text)
        self.assertIn("<!-- shell: main -->", text)
        self.assertIn("one job", text)                           # a page is one job: tables and forms are pages of their own
        self.assertIn("exactly as it is", text)                  # the shared layout is kept, not redrawn
        self.assertIn("never the component kit", text)           # and it is a reference: the kit is never copied into a page

    def test_a_missing_ideas_or_layout_is_said_rather_than_left_blank(self):
        text = self.instruction()
        self.assertIn("none gathered", text)
        self.assertIn("none drawn", text)
        self.assertNotIn("{{", text)

    def test_the_approval_prompt_asks_for_a_web_search_focused_pages_and_one_shared_layout(self):
        prompt = document.WIREFRAME_APPROVAL_PROMPT.lower()
        self.assertIn("search the web", prompt)
        self.assertIn("one job", prompt)
        self.assertIn("identical on every page", prompt)
        for gone in ("role rule", "builder.md", "prototype.md"):
            self.assertNotIn(gone, prompt)
        page = (ROOT / "studio/app/page.jsx").read_text(encoding="utf-8")
        self.assertIn("search the web", page)
        self.assertNotIn("role rule", page)


class PrepareTests(unittest.TestCase):
    def run_prepare(self, have=None, search=None, layout="<!DOCTYPE html><html><style></style></html>"):
        said = []
        search = [{"title": "T", "url": "https://x.example/a", "content": "a board with columns"}] if search is None else search
        with mock.patch.object(llm, "complete_json", lambda **kw: kw["validator"]({"queries": ["task board layout", "form page layout"]})), \
             mock.patch.object(llm, "web_search", lambda query, n=4: list(search)), \
             mock.patch.object(llm, "complete", lambda **kw: "IDEAS FROM RESULTS"), \
             mock.patch.object(llm, "complete_html", lambda **kw: layout):
            made = wireframe_brief.prepare(DOC, DOCS, have or {}, said.append)
        return made, said

    def test_it_searches_writes_the_ideas_up_and_draws_the_layout_once(self):
        made, said = self.run_prepare()
        self.assertEqual(made["ideas"], "IDEAS FROM RESULTS")
        self.assertTrue(made["layout"].startswith("<!DOCTYPE"))
        self.assertEqual(made["new"], ["ideas", "layout"])
        self.assertEqual([s for s in said if s.startswith("Searched")], ['Searched the web for "task board layout"', 'Searched the web for "form page layout"'])

    def test_what_is_already_kept_is_reused_and_not_made_again(self):
        made, said = self.run_prepare(have={"ideas": "KEPT IDEAS", "layout": "KEPT LAYOUT"})
        self.assertEqual((made["ideas"], made["layout"], made["new"]), ("KEPT IDEAS", "KEPT LAYOUT", []))
        self.assertEqual(said, [])

    def test_a_search_with_no_results_does_not_stop_the_drawing(self):
        made, said = self.run_prepare(search=[])
        self.assertEqual(made["ideas"], "")
        self.assertTrue(made["layout"])                            # the layout is still drawn
        self.assertTrue(any("without web ideas" in s for s in said))

    def test_a_layout_that_cannot_be_drawn_is_said_and_the_pages_go_on_without_it(self):
        with mock.patch.object(llm, "complete_html", side_effect=ValueError("boom")):
            said = []
            layout = wireframe_brief.draw_layout("{}", "", "", said.append)
        self.assertEqual(layout, "")
        self.assertTrue(any("shared layout" in s for s in said))


class SearchTests(unittest.TestCase):
    def test_the_local_ollama_search_is_asked_without_a_key_and_its_results_are_trimmed(self):
        reply = mock.Mock()
        reply.json.return_value = {"results": [{"title": "A", "url": "https://a.example", "content": "x" * 5000}, "junk"]}
        with mock.patch.object(llm.config, "settings", lambda: {"cloud": False, "ollama_host": "http://localhost:11434"}), \
             mock.patch.object(llm.httpx, "post", return_value=reply) as post:
            rows = llm.web_search("  a   query ", 3)
        self.assertEqual(post.call_args.args[0], "http://localhost:11434/api/experimental/web_search")
        self.assertEqual(post.call_args.kwargs["json"], {"query": "a query", "max_results": 3})
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["content"]), 1500)

    def test_a_search_that_fails_is_an_empty_answer(self):
        with mock.patch.object(llm.config, "settings", lambda: {"cloud": False}), \
             mock.patch.object(llm.httpx, "post", side_effect=OSError("offline")):
            self.assertEqual(llm.web_search("anything"), [])
        self.assertEqual(llm.web_search("   "), [])


if __name__ == "__main__":
    unittest.main()
