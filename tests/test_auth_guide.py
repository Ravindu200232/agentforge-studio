"""One authentication guide, read by the build like the design's DESIGN.md; the prototype signs in with fictitious accounts."""
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

from prototype_agent import demo  # noqa: E402
from server_modules import web_app  # noqa: E402
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


class PrototypeSignInTests(unittest.TestCase):
    def test_a_page_is_signed_in_by_its_flag_or_by_who_opens_it(self):
        self.assertTrue(demo.signed_in_page({"login_required": True}))
        self.assertFalse(demo.signed_in_page({"login_required": False, "allowed_roles": ["admin"]}))
        self.assertTrue(demo.signed_in_page({"allowed_roles": ["Admin"]}))
        self.assertFalse(demo.signed_in_page({"allowed_roles": ["Visitor", "Admin"]}))
        self.assertFalse(demo.signed_in_page({}))

    def test_sign_up_signs_the_new_account_in_as_the_role_sign_ups_get(self):
        routes = [{"route": "/login", "name": "Sign in"}, {"route": "/register", "name": "Create account"},
                  {"route": "/home", "name": "My home"}]
        accounts = [{"role": role, "role_key": role.lower(), "display_name": f"Demo {role}", "email": f"{role.lower()}@example.com",
                     "password": "pw", "lands_on": "/home", "can_open": []} for role in ("Admin", "Member")]
        doc = {"authentication_requirement": {"self_registration": True, "registration_mode": "open",
                                              "sign_up_route": "/register", "registration_role": "Member"}}
        sign_up = demo.sign_up_of(doc, routes, accounts)
        self.assertEqual((sign_up["route"], sign_up["role_key"]), ("/register", "member"))
        self.assertIsNone(demo.sign_up_of({"authentication_requirement": {"registration_mode": "admin_created"}}, routes, accounts))

    def test_the_session_every_prototype_has_signs_in_signs_up_and_signs_out(self):
        session = (web_app.KIT_SOURCE / "app" / "src" / "lib" / "session.tsx").read_text(encoding="utf-8")
        for needle in ("signIn:", "signInAs:", "signUp:", "signOut:", "canOpen:", "?as=", "navigate(account.landsOn)",
                       "navigate(signInRoute"):
            self.assertIn(needle, session)
        self.assertNotIn("localStorage", session, "the prototype keeps nobody signed in between visits")

    def test_the_router_keeps_the_app_on_its_own_page(self):
        router = (web_app.KIT_SOURCE / "app" / "src" / "lib" / "router.tsx").read_text(encoding="utf-8")
        for needle in ("hashchange", "event.preventDefault()", 'href.startsWith("/")', "onSubmit", "matchRoute"):
            self.assertIn(needle, router)


if __name__ == "__main__":
    unittest.main()
