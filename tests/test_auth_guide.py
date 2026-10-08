"""One authentication guide, read by the build like the design's DESIGN.md. The wireframe and the prototype carry no sign-in logic."""
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
                       "its own dashboard"):
            self.assertIn(needle, text)

    def test_the_wireframe_and_the_prototype_have_no_part_in_it(self):
        text = prompts.load("shared/authentication")
        for gone in ("In the wireframes", "In the prototype", "data-auth", "flow.js", "data-sign-out", "demo session"):
            self.assertNotIn(gone, text)
        self.assertIn("## 5. In the real application", text)


if __name__ == "__main__":
    unittest.main()
