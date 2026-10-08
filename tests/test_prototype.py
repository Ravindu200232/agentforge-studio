"""The prototype: the approved wireframe app, copied, and edited by the agent into a high-fidelity React app."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from ollama_terminal import screenshot  # noqa: E402
from prototype_agent import demo, prototype as prototyper, screens  # noqa: E402
from server_modules import prompts, web_app  # noqa: E402
from srs_agent import document, wireframe  # noqa: E402
from test_wireframe import FakeSession  # noqa: E402

PROJECT = "prj_bakery"
DOC = {
    "app_summary": {"app_name": "Sweet Crumbs"},
    "authentication_requirement": {"login_required": True, "sign_in_route": "/login", "registration_mode": "open",
                                   "sign_up_route": "/register", "registration_role": "Customer"},
    "roles": [{"role_key": "customer", "role_name": "Customer"}, {"role_key": "baker", "role_name": "Baker"}],
    "public_pages": [{"page_name": "Home", "route": "/"}, {"page_name": "Sign in", "route": "/login"},
                     {"page_name": "Create account", "route": "/register"}],
    "protected_pages": [{"page_name": "My orders", "route": "/orders", "login_required": True, "allowed_roles": ["Customer"]},
                        {"page_name": "Kitchen", "route": "/kitchen", "login_required": True, "allowed_roles": ["Baker"]}],
}
PAGES = [*DOC["public_pages"], *DOC["protected_pages"]]


class Scratch(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = Path(self.folder.name)
        handoff = self.workspace / ".agentforge" / "srs" / "handoff"
        handoff.mkdir(parents=True)
        (handoff / "app.md").write_text("# Sweet Crumbs", encoding="utf-8")
        self.session = FakeSession(self.workspace)
        self.kit = self.workspace / "kit"
        for patcher in (
            mock.patch.object(prototyper, "session_for", lambda project: self.session),
            mock.patch.object(wireframe, "session_for", lambda project: self.session),
            mock.patch.object(web_app, "kit_dir", lambda: self.kit),
            mock.patch.object(web_app, "build_for"),
            mock.patch.object(document, "document", return_value={"srs_document": DOC}),
            mock.patch.object(document, "screens", return_value=PAGES),
            mock.patch.object(prototyper.design_stage, "approved_customization", return_value={
                "design_md_path": "prompts/design/themes/terracotta/DESIGN.md", "design_md_workspace_path": "design/theme.md",
                "customizer_prompt": "CUSTOMIZER_EXTRA_PROMPT"}),
            mock.patch.object(prototyper.bus, "file_written"),
            mock.patch.object(prototyper.bus, "log"),
            mock.patch.object(prototyper.bus, "agent_msg"),
            mock.patch.object(prototyper.bus, "phase"),
            mock.patch.object(prototyper.bus, "sync_state"),
            mock.patch.object(prototyper.bus, "cancelled"),
            mock.patch.object(prototyper.bus, "prototype_changed"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.wire = web_app.app_dir(self.workspace, "wireframe")
        self.proto = web_app.app_dir(self.workspace, "prototype")
        web_app.create_app(self.wire, "Sweet Crumbs", PAGES)
        pages = self.wire / "src" / "pages"
        pages.mkdir(parents=True)
        for name in ("home", "login", "register", "orders", "kitchen"):
            (pages / f"{name}.tsx").write_text(f"export default () => 'WIRE {name}'", encoding="utf-8")
        (self.wire / "bundle.html").write_text("<html>wireframe</html>", encoding="utf-8")

    def agent_edits(self, session):
        """What the agent does: it reads the wireframes and writes a page for every screen."""
        pages = self.proto / "src" / "pages"
        pages.mkdir(parents=True, exist_ok=True)
        for name in ("home", "login", "register", "orders", "kitchen"):
            (pages / f"{name}.tsx").write_text(f"export default () => 'FRESH {name}'", encoding="utf-8")

    def draw(self, direction: str = "Make it warm"):
        self.session.agent = self.agent_edits
        return prototyper._draw_with_agent(PROJECT, {"tokens": {"light": {"accent": "#c2410c"}}}, direction)


class DrawingTests(Scratch):
    def test_the_agent_gets_the_skill_the_wireframes_app_md_the_design_and_the_pages(self):
        rows = self.draw()

        request = self.session.tasks[0]
        self.assertTrue(request.startswith("Generate a high-fidelity, animated prototype."))
        for expected in (".agentforge/skills/web-artifacts-builder/SKILL.md", ".agentforge/prototype/app",
                         ".agentforge/wireframe/app", ".agentforge/srs/handoff/app.md",
                         ".agentforge/prototype/input/design-spec.json", "design/theme.md", "CUSTOMIZER_EXTRA_PROMPT",
                         "Make it warm", "`/kitchen` — Kitchen (signed in: Baker) — `src/pages/kitchen.tsx`"):
            self.assertIn(expected, request)
        self.assertEqual([r["route"] for r in rows], ["/", "/login", "/register", "/orders", "/kitchen"])
        self.assertFalse(self.session.kwargs["audit"], "the pages are the agent's: nothing audits them")

    def test_the_prompt_is_short_and_general(self):
        text = prompts.load("prototype/generate")
        self.assertLess(len(text), 2200)
        self.assertNotIn("HTML", text)
        self.assertIn("web-artifacts-builder", text)
        self.assertIn("high-fidelity", text)

    def test_the_agent_is_told_to_read_the_wireframes_then_plan_then_write(self):
        self.draw()
        request = self.session.tasks[0]
        read, plan, write = (request.index(part) for part in ("First read the wireframes", "Then plan the prototype", "and write it"))
        self.assertLess(read, plan)
        self.assertLess(plan, write)
        self.assertIn("every page under `.agentforge/wireframe/app/src/pages/`", request)
        self.assertIn("Never change the wireframes", request)
        self.assertNotIn("copied", request)

    def test_the_prototype_is_a_new_app_and_the_wireframes_stay_as_they_were(self):
        self.draw()

        self.assertEqual((self.proto / "src/pages/home.tsx").read_text(encoding="utf-8"), "export default () => 'FRESH home'")
        self.assertEqual((self.wire / "src/pages/home.tsx").read_text(encoding="utf-8"), "export default () => 'WIRE home'")
        self.assertEqual((self.wire / "bundle.html").read_text(encoding="utf-8"), "<html>wireframe</html>")
        self.assertFalse((self.proto / "bundle.html").exists(), "the prototype is bundled after the agent has written it")

    def test_nothing_of_the_wireframe_is_in_the_new_app_before_the_agent_writes(self):
        self.session.agent = lambda s: self.assertFalse((self.proto / "src" / "pages").exists(), "the wireframe's pages were copied")
        with self.assertRaises(prototyper.PrototypeIncomplete):
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")
        self.assertTrue((self.proto / "src" / "routes.ts").is_file(), "but it is set up: routes, demo accounts, router, components")
        self.assertTrue((self.proto / "src" / "components" / "ui" / "button.tsx").is_file())

    def test_it_is_bundled_when_the_agent_is_done(self):
        self.draw()
        web_app.build_for.assert_called_once()
        self.assertEqual(web_app.build_for.call_args.args[1:3], (PROJECT, "prototype"))

    def test_what_the_build_reads_is_left_beside_the_app(self):
        self.draw()
        root = self.workspace / ".agentforge" / "prototype"
        routes = json.loads((root / "routes.json").read_text(encoding="utf-8"))["routes"]
        self.assertEqual([r["file"] for r in routes],
                         ["app/src/pages/home.tsx", "app/src/pages/login.tsx", "app/src/pages/register.tsx",
                          "app/src/pages/orders.tsx", "app/src/pages/kitchen.tsx"])
        self.assertEqual([r["signed_in"] for r in routes], [False, False, False, True, True])
        accounts = json.loads((root / "demo-accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(accounts["sign_in"], "/login")
        self.assertEqual({a["email"] for a in accounts["accounts"]}, {"customer@example.com", "baker@example.com"})
        self.assertEqual((root / "plan.md").read_text(encoding="utf-8"), "PLAN")

    def test_the_sign_in_the_prototype_demonstrates_is_the_one_the_build_is_seeded_with(self):
        self.draw()
        demo_ts = (self.proto / "src" / "demo.ts").read_text(encoding="utf-8")
        self.assertIn('"email": "baker@example.com"', demo_ts)
        self.assertIn('"landsOn": "/kitchen"', demo_ts)
        self.assertIn('export const signInRoute: string = "/login"', demo_ts)
        self.assertIn('"route": "/register"', demo_ts.split("export const signUp")[1])
        request = self.session.tasks[0]
        self.assertIn("`signInAs(roleKey)`", request)
        self.assertIn("`/login`", request)

    def test_a_product_without_sign_in_is_told_nothing_about_it(self):
        plain = {"app_summary": {"app_name": "Brochure"}, "public_pages": [{"page_name": "Home", "route": "/"}]}
        with mock.patch.object(document, "document", return_value={"srs_document": plain}), \
                mock.patch.object(document, "screens", return_value=plain["public_pages"]):
            self.draw()
        self.assertNotIn("signInAs", self.session.tasks[0])
        self.assertIn("export const accounts: Account[] = []", (self.proto / "src" / "demo.ts").read_text(encoding="utf-8"))

    def test_an_agent_that_wrote_no_pages_leaves_the_run_to_be_carried_on(self):
        self.session.agent = None
        with self.assertRaises(prototyper.PrototypeIncomplete) as raised:
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")
        self.assertEqual(raised.exception.missing, ["/", "/login", "/register", "/orders", "/kitchen"])
        web_app.build_for.assert_not_called()
        self.assertFalse((self.workspace / ".agentforge/prototype/routes.json").exists())

    def test_a_screen_with_no_page_is_named_and_nothing_is_handed_over(self):
        def writes_some(session):
            pages = self.proto / "src" / "pages"
            pages.mkdir(parents=True, exist_ok=True)
            for name in ("home", "login", "register"):
                (pages / f"{name}.tsx").write_text("export default () => null", encoding="utf-8")

        self.session.agent = writes_some
        with self.assertRaises(prototyper.PrototypeIncomplete) as raised:
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")
        self.assertEqual(raised.exception.missing, ["/orders", "/kitchen"])
        web_app.build_for.assert_not_called()

    def test_a_run_that_was_carried_on_keeps_the_pages_it_wrote_and_the_direction_it_had(self):
        def writes_some(session):
            pages = self.proto / "src" / "pages"
            pages.mkdir(parents=True, exist_ok=True)
            (pages / "home.tsx").write_text("export default () => 'HALF DONE'", encoding="utf-8")

        self.session.agent = writes_some
        with self.assertRaises(prototyper.PrototypeIncomplete):
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "warm premium direction")

        def writes_the_rest(session):
            pages = self.proto / "src" / "pages"
            for name in ("login", "register", "orders", "kitchen"):
                (pages / f"{name}.tsx").write_text("export default () => 'DONE'", encoding="utf-8")

        self.session.agent = writes_the_rest
        prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")

        self.assertEqual((self.proto / "src/pages/home.tsx").read_text(encoding="utf-8"), "export default () => 'HALF DONE'")
        self.assertIn("warm premium direction", self.session.tasks[1])
        self.assertIn("Resuming an interrupted run", self.session.tasks[1])
        self.assertIn("write only the pages that are still missing", self.session.tasks[1])

    def test_a_changed_design_starts_a_new_app(self):
        self.draw()
        self.session.agent = None
        with self.assertRaises(prototyper.PrototypeIncomplete):
            prototyper._draw_with_agent(PROJECT, {"tokens": {"light": {"accent": "#000"}}}, "Make it warm")
        self.assertFalse((self.proto / "src/pages/home.tsx").exists(), "the earlier prototype's pages are gone")
        self.assertNotIn("Resuming", self.session.tasks[1])

    def test_the_customers_images_go_inside_the_app_and_the_originals_stay(self):
        image = self.workspace / "media" / "logo.png"
        image.parent.mkdir()
        image.write_bytes(b"logo")
        self.session.read_record = lambda *parts, fallback=None: [
            {"path": "media/logo.png", "purpose": "Brand logo"}, {"path": "media/../other.png", "purpose": "Unsafe"}]
        staged = prototyper._uploaded_site_images(self.session, self.proto)
        self.assertEqual(staged, [{"name": "logo.png", "usage": "Brand logo", "source": "media/logo.png",
                                   "file": "src/assets/uploads/logo.png"}])
        self.assertEqual((self.proto / "src/assets/uploads/logo.png").read_bytes(), b"logo")
        self.assertEqual(image.read_bytes(), b"logo")


class GeneratingTests(Scratch):
    def stage(self, draw):
        patches = (
            mock.patch.object(document, "has_document", return_value=True),
            mock.patch.object(prototyper.design_stage, "current", return_value={"approved": True}),
            mock.patch.object(prototyper.design_stage, "approved_spec", return_value={"tokens": {}}),
            mock.patch.object(prototyper.store, "update"),
            mock.patch.object(prototyper.store, "require", return_value={}),
            mock.patch.object(prototyper.store, "advance"),
            mock.patch.object(prototyper, "_draw_with_agent", draw),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_the_wireframes_are_drawn_first_when_there_are_none(self):
        (self.wire / "bundle.html").unlink()
        drawn = []
        self.stage(lambda *a, **k: [{"route": "/", "name": "Home"}])
        with mock.patch.object(wireframe, "generate", side_effect=lambda project: drawn.append(project)):
            answer = prototyper.generate_from_wireframes(PROJECT, "direction")
        self.assertEqual(drawn, [PROJECT])
        self.assertTrue(answer["complete"])

    def test_the_wireframes_that_are_there_are_not_drawn_again(self):
        self.stage(lambda *a, **k: [{"route": "/", "name": "Home"}])
        with mock.patch.object(wireframe, "generate") as generate:
            prototyper.generate_from_wireframes(PROJECT, "")
        generate.assert_not_called()

    def test_a_finished_prototype_enables_the_build_and_says_who_can_sign_in(self):
        self.draw()                                        # the files the build reads are written by this
        self.stage(lambda *a, **k: [{"route": "/", "name": "Home"}, {"route": "/login", "name": "Sign in"}])
        answer = prototyper.generate_from_wireframes(PROJECT, "")
        self.assertTrue(answer["complete"])
        prototyper.store.update.assert_any_call(PROJECT, prototype_only=True, status="prototyped", build_available=True)
        titles = [call.kwargs.get("title") for call in prototyper.bus.agent_msg.call_args_list]
        self.assertIn("Prototype ready", titles)
        self.assertIn("Demo accounts", titles)
        self.assertEqual(self.session.events[-1], "finish Prototype made: 2 screens.")

    def test_an_omitted_page_keeps_building_disabled(self):
        updates = []
        self.stage(mock.Mock(side_effect=prototyper.PrototypeIncomplete(["/checkout"])))
        with mock.patch.object(prototyper.store, "update", side_effect=lambda _p, **values: updates.append(values)):
            answer = prototyper.generate_from_wireframes(PROJECT, "fresh direction")
        self.assertFalse(answer["complete"])
        self.assertEqual(answer["remaining"], ["/checkout"])
        self.assertTrue(updates and all(u.get("build_available") is False for u in updates))

    def test_the_design_must_be_approved_first(self):
        self.stage(mock.Mock())
        with mock.patch.object(prototyper.design_stage, "current", return_value={"approved": False}):
            with self.assertRaisesRegex(ValueError, "Design Customize"):
                prototyper.generate_from_wireframes(PROJECT, "")


class ChangingTests(Scratch):
    def test_a_message_changes_the_prototype_and_bundles_it_again(self):
        self.draw()
        (self.workspace / ".agentforge/prototype/generation.json").write_text(json.dumps({"complete": True}), encoding="utf-8")
        prototyper.revise(PROJECT, "Make the buttons rounder")
        self.assertIn("Make the buttons rounder", self.session.directs[0])
        self.assertIn(".agentforge/prototype/app", self.session.directs[0])
        self.assertEqual(web_app.build_for.call_count, 2)           # once when it was made, once now
        prototyper.bus.prototype_changed.assert_called_once_with(PROJECT)

    def test_there_must_be_a_prototype_to_change(self):
        with self.assertRaisesRegex(ValueError, "no prototype"):
            prototyper.revise(PROJECT, "x")


class DemoAccountTests(unittest.TestCase):
    def test_each_demo_role_opens_its_own_pages_and_lands_on_the_top_of_its_area(self):
        def protected(route, roles):
            return {"page_name": route.strip("/").title() or "Home", "route": route, "login_required": True, "allowed_roles": roles}

        doc = {"authentication_requirement": {"login_required": True, "sign_in_route": "/login"},
               "roles": [{"role_key": "shopper", "role_name": "Shopper"}, {"role_key": "store_owner", "role_name": "Store Owner"},
                         {"role_key": "guest", "role_name": "Guest"}],
               # an access matrix that names the pages differently from the page list
               "role_access_matrix": [{"role": "Shopper", "allowed_pages": "Storefront and the account area"},
                                      {"role": "store_owner", "allowed_pages": "/admin/staff"}],
               "public_pages": [{"page_name": "Home", "route": "/"}, {"page_name": "Sign in", "route": "/login"}],
               "protected_pages": [protected("/account/orders", ["Shopper"]), protected("/account", ["Shopper"]),
                                   protected("/admin/products", "Store Owner"), protected("/admin", ["store_owner"]),
                                   protected("/admin/staff", [])]}
        accounts = {a["role"]: a for a in demo.draw_accounts(doc)}

        self.assertEqual(set(accounts), {"Shopper", "Store Owner"})
        self.assertEqual(accounts["Shopper"]["lands_on"], "/account")
        self.assertEqual(accounts["Store Owner"]["lands_on"], "/admin")
        owner = {p["route"] for p in accounts["Store Owner"]["can_open"]}
        self.assertTrue({"/admin", "/admin/products", "/admin/staff"} <= owner)
        self.assertNotIn("/account", owner)
        self.assertNotIn("/admin", {p["route"] for p in accounts["Shopper"]["can_open"]})

    def test_there_are_no_accounts_without_sign_in(self):
        self.assertEqual(demo.draw_accounts({"public_pages": [{"page_name": "Home", "route": "/"}]}), [])

    def test_a_signed_in_page_is_one_its_record_says_or_only_signing_in_roles_open(self):
        self.assertTrue(demo.signed_in_page({"login_required": True}))
        self.assertFalse(demo.signed_in_page({"login_required": False, "allowed_roles": ["admin"]}))
        self.assertTrue(demo.signed_in_page({"allowed_roles": ["admin"]}))
        self.assertFalse(demo.signed_in_page({"allowed_roles": ["Visitor"]}))


class PhotographingTests(unittest.TestCase):
    ROWS = [{"route": "/", "name": "Home", "file": "app/src/pages/home.tsx", "signed_in": False},
            {"route": "/kitchen", "name": "Kitchen", "file": "app/src/pages/kitchen.tsx", "signed_in": True}]
    ACCOUNTS = [{"email": "customer@example.com", "can_open": [{"route": "/orders"}]},
                {"email": "baker@example.com", "can_open": [{"route": "/kitchen"}]}]

    def test_a_page_is_found_by_route_file_or_name(self):
        for target in ("/kitchen", "kitchen", "Kitchen", "app/src/pages/kitchen.tsx", "/kitchen#top"):
            self.assertEqual(screens.find_page(Path("."), target, self.ROWS)["route"], "/kitchen", target)
        self.assertEqual(screens.find_page(Path("."), "/", self.ROWS)["route"], "/")
        self.assertIsNone(screens.find_page(Path("."), "/nowhere", self.ROWS))

    def test_a_signed_in_page_is_shown_as_an_account_that_can_open_it(self):
        self.assertEqual(screens.role_for(self.ROWS[0], self.ACCOUNTS), "")
        self.assertEqual(screens.role_for(self.ROWS[1], self.ACCOUNTS), "baker@example.com")

    def test_the_bundled_page_is_opened_at_the_route_signed_in_as_that_account(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app").mkdir()
            (root / "app" / "bundle.html").write_text("<html><body>app</body></html>", encoding="utf-8")
            seen = {}

            def shoot(page, out, viewport, **kwargs):
                seen.update(html=Path(page).read_text(encoding="utf-8"), viewport=viewport, **kwargs)
                return out

            with mock.patch.object(screenshot, "shoot", shoot):
                screens.shoot_page(root, self.ROWS[1], self.ACCOUNTS, root / "out.png", "mobile")
            self.assertEqual(seen["suffix"], "?as=baker%40example.com#/kitchen")
            self.assertIn(screenshot.MEASURE, seen["html"])
            self.assertEqual(seen["viewport"], "mobile")

            with mock.patch.object(screenshot, "shoot", shoot):
                screens.shoot_page(root, self.ROWS[0], self.ACCOUNTS, root / "out.png", "desktop")
            self.assertEqual(seen["suffix"], "#/")

    def test_there_is_nothing_to_photograph_before_it_is_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "not bundled"):
                screens.shoot_page(Path(tmp), self.ROWS[0], [], Path(tmp) / "out.png", "desktop")


if __name__ == "__main__":
    unittest.main()
