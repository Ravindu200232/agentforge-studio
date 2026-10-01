"""One authentication guide, read by the wireframes, the prototype and the build alike, like the design's DESIGN.md."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "prototype-agent", "srs-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from prototype_agent import prototype_brief  # noqa: E402
from server_modules import auth_guide, prompts  # noqa: E402

SIGNED_IN = {"protected_pages": [{"route": "/dashboard", "login_required": True, "allowed_roles": ["member"]}]}


class GuideTests(unittest.TestCase):
    def test_only_a_product_with_sign_in_needs_it(self):
        self.assertTrue(auth_guide.needed(SIGNED_IN))
        self.assertTrue(auth_guide.needed({"authentication_requirement": {"login_required": True}}))
        self.assertFalse(auth_guide.needed({"public_pages": [{"route": "/", "login_required": False}]}))
        self.assertFalse(auth_guide.needed({"authentication_requirement": "none"}))
        self.assertFalse(auth_guide.needed(None))

    def test_it_is_staged_where_an_agent_can_read_it(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            path = auth_guide.staged_for(workspace, SIGNED_IN)
            self.assertEqual(path, ".agentforge/auth/AUTHENTICATION.md")
            self.assertEqual((workspace / path).read_text(encoding="utf-8"), prompts.load("shared/authentication"))
            self.assertEqual(auth_guide.staged_for(workspace, {}), "")

    def test_it_covers_cookies_server_side_roles_and_both_navigations(self):
        text = prompts.load("shared/authentication")
        for needle in ("HttpOnly", "SameSite=Lax", "localStorage", "Row Level Security", "403",
                       "Signed out — the public navigation", "Signed in — the navigation of the person's role",
                       "its own dashboard", 'data-auth="in"', 'data-auth="out"'):
            self.assertIn(needle, text)


class PrototypeNavigationTests(unittest.TestCase):
    def test_a_page_is_signed_in_by_its_flag_or_by_who_opens_it(self):
        self.assertTrue(prototype_brief.signed_in_page({"login_required": True}))
        self.assertFalse(prototype_brief.signed_in_page({"login_required": False, "allowed_roles": ["admin"]}))
        self.assertTrue(prototype_brief.signed_in_page({"allowed_roles": ["Admin"]}))
        self.assertFalse(prototype_brief.signed_in_page({"allowed_roles": ["Visitor", "Admin"]}))
        self.assertFalse(prototype_brief.signed_in_page({}))

    def test_flow_js_switches_the_navigation_by_the_demo_session(self):
        routes = [{"route": "/", "file": "index.html", "name": "Home", "roles": [], "signed_in": False},
                  {"route": "/dashboard", "file": "dashboard.html", "name": "Dashboard", "roles": ["member"], "signed_in": True}]
        self.assertEqual([r["signedIn"] for r in prototype_brief.route_map(routes)], [False, True])
        script = prototype_brief.flow_script(routes, {"journeys": [], "leads": {}}, [], "")
        self.assertIn('"signedIn": true', script)
        self.assertIn("[data-auth]", script)
        self.assertIn("[hidden]{display:none!important}", script)

    def test_the_prototype_is_told_to_mark_both_navigations(self):
        accounts = [{"role": "Member", "role_key": "member", "email": "m@example.com", "password": "pw",
                     "lands_on": "/dashboard"}]
        text = prototype_brief.sign_in_text(accounts, "/login", [{"route": "/login", "file": "login.html", "name": "Sign in"}])
        self.assertIn('data-auth="in"', text)
        self.assertIn('data-auth="out"', text)
        self.assertIn("own dashboard", text)


if __name__ == "__main__":
    unittest.main()
