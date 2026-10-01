"""Wireframes are planned before they are drawn, like the builder and the prototype: one plan, each page drawn from its part."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from srs_agent import document  # noqa: E402

PLAN = """Plan for the wireframes.

## Shared
- Shells: public (`/`, `/request`), member area (`/account/requests`) — nav: Overview `/`, My Requests `/account/requests`

## Pages
### `/` — Overview
- Job: show what the service offers.
- Actions: "Start a request" → `/request`

### `/request` — Request Form
- Content: name, email, details
- Actions: "Send" → `/request/[id]/done`

### `/account/requests/` — My Requests
- Content: table — number, date, status
"""

DOC = {
    "roles": [{"role_key": "member", "role_name": "Member"}],
    "public_pages": [{"page_name": "Overview", "route": "/"}, {"page_name": "Request Form", "route": "/request"}],
    "protected_pages": [{"page_name": "My Requests", "route": "/account/requests", "login_required": True,
                         "allowed_roles": ["Member"]}],
    "business_workflows": [{"workflow_name": "Send a request", "who": "Visitor",
                            "steps": ["Open the Overview", "Fill in the Request Form"]}],
}


class Session:
    def __init__(self, root):
        self.workspace = root
        self.record = root / ".agentforge"
        self.planned = []

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        return path.read_text(encoding="utf-8") if path.is_file() else fallback

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(data), encoding="utf-8")
        return path

    def plan_focused_task(self, request, subject=""):
        self.planned.append((request, subject))
        return PLAN


class WireframePlanTests(unittest.TestCase):
    def test_each_page_gets_the_shared_part_and_its_own_part(self):
        shared, pages = document._plan_sections(PLAN)
        self.assertIn("## Shared", shared)
        self.assertNotIn("### `/`", shared)
        self.assertEqual(set(pages), {"/", "/request", "/account/requests"})
        own = document._plan_for_page(PLAN, "/request")
        self.assertIn("Shells:", own)
        self.assertIn('"Send" → `/request/[id]/done`', own)
        self.assertNotIn("Start a request", own)
        # a page the plan forgot still gets the whole plan rather than nothing
        self.assertIn("Overview", document._plan_for_page(PLAN, "/missing"))
        self.assertEqual(document._plan_for_page("", "/"), "")

    def test_the_plan_is_made_once_saved_and_reused_for_one_page(self):
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(document.bus, "phase"), mock.patch.object(document.bus, "file_written"), \
             mock.patch.object(document.bus, "log"):
            session = Session(Path(folder))
            plan = document._wireframe_plan(session, "prj", DOC, {}, fresh=True)
            self.assertEqual(plan, PLAN)
            request, subject = session.planned[0]
            self.assertEqual(subject, "the wireframes")
            self.assertIn("`/account/requests` — My Requests — signed in: Member", request)
            self.assertIn("Send a request (Visitor)", request)
            self.assertTrue((session.record / "srs" / "wireframe-system" / "plan.md").is_file())
            # one page redrawn later follows the same plan, without planning again
            self.assertEqual(document._wireframe_plan(session, "prj", DOC, {}, fresh=False), PLAN)
            self.assertEqual(len(session.planned), 1)

    def test_a_plan_that_cannot_be_made_never_stops_the_drawing(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(document.bus, "phase"), \
             mock.patch.object(document.bus, "log") as log:
            session = Session(Path(folder))
            session.plan_focused_task = mock.Mock(side_effect=ValueError("model unavailable"))
            self.assertEqual(document._wireframe_plan(session, "prj", DOC, {}, fresh=True), "")
        self.assertIn("Could not plan the wireframes", log.call_args.args[2])

    def test_the_page_prompt_carries_its_part_of_the_plan(self):
        with mock.patch.object(document.plan_stage, "markdown", return_value="APPROVED PLAN"):
            text = document._page_instruction("prj", DOC, DOC["public_pages"][1], {"app.md": "x"},
                                              wireframe_plan=document._plan_for_page(PLAN, "/request"))
        self.assertIn("## The wireframe plan for this page", text)
        self.assertIn('"Send" → `/request/[id]/done`', text)


if __name__ == "__main__":
    unittest.main()
