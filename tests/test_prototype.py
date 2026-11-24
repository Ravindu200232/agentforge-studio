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
            mock.patch.object(web_app, "kit_dir", lambda legacy=False: self.kit),
            mock.patch.object(web_app, "build_for"),
            mock.patch.object(prototyper, "PageReview"),
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
        web_app.create_app(self.wire, PAGES)
        pages = self.wire / "src" / "pages"
        pages.mkdir(parents=True)
        for name in ("home", "login", "register", "orders", "kitchen"):
            (pages / f"{name}.tsx").write_text(f"export default () => 'WIRE {name}'", encoding="utf-8")
        (self.wire / "bundle.html").write_text("<html>wireframe</html>", encoding="utf-8")

    def write_html(self, *names, label="FRESH"):
        self.proto.mkdir(parents=True, exist_ok=True)
        (self.proto / "index.html").write_text('<!doctype html><main id="af-page"></main>', encoding="utf-8")
        assets = self.proto / "assets"
        assets.mkdir(exist_ok=True)
        (assets / "prototype.css").write_text("body { color: #222; }", encoding="utf-8")
        (assets / "prototype.js").write_text("", encoding="utf-8")
        pages = self.proto / "pages"
        pages.mkdir(exist_ok=True)
        for name in names:
            (pages / f"{name}.html").write_text(f"<h1>{label} {name}</h1>", encoding="utf-8")

    def agent_edits(self, session):
        """What the agent does: it reads the wireframes and writes a page for every screen."""
        self.write_html("home", "login", "register", "orders", "kitchen")

    def draw(self, direction: str = "Make it warm"):
        self.session.agent = self.agent_edits
        return prototyper._draw_with_agent(PROJECT, {"tokens": {"light": {"accent": "#c2410c"}}}, direction)


class DrawingTests(Scratch):
    def test_the_agent_gets_the_skill_the_wireframes_app_md_the_design_and_the_pages(self):
        rows = self.draw()

        request = self.session.tasks[0]
        self.assertTrue(request.startswith("Generate a high-fidelity, animated prototype."))
        for expected in (".agentforge/prototype/app",
                         ".agentforge/wireframe/app", ".agentforge/srs/handoff/app.md",
                         ".agentforge/prototype/input/design-spec.json", "design/theme.md", "CUSTOMIZER_EXTRA_PROMPT",
                         "Make it warm", "`/kitchen` — Kitchen (signed in: Baker) — `pages/kitchen.html`"):
            self.assertIn(expected, request)
        self.assertEqual([r["route"] for r in rows], ["/", "/login", "/register", "/orders", "/kitchen"])
        self.assertFalse(self.session.kwargs["audit"], "the pages are the agent's: nothing audits them")

    def test_the_prompt_plans_original_html_ui_with_shared_design_and_motion_guidance(self):
        self.draw()
        request = self.session.tasks[0]
        self.assertLess(request.index("Read the product inputs"), request.index("Plan the shared layout"))
        self.assertIn("HTML, shared CSS and vanilla JavaScript", request)
        self.assertIn("Do not use frameworks", request)
        self.assertIn("prefers-reduced-motion", request)
        self.assertIn("Micro-interactions and page transitions", request)
        self.assertIn("https://github.com/iart-ai/motion-skills", request)
        self.assertNotIn("{{design_motion}}", request)

    def test_the_journeys_are_among_what_the_agent_reads_when_the_specification_has_them(self):
        self.draw()
        self.assertNotIn("user-journeys.json", self.session.tasks[0])
        journeys = self.workspace / ".agentforge" / "srs" / "user-journeys.json"
        journeys.write_text(json.dumps({"journeys": [{"id": "UJ-001", "workflow_name": "View orders", "who": "Customer",
                                                       "steps": [{"id": "UJ-001-S01", "route": "/orders", "step": "Open My Orders",
                                                                  "expected_outcome": "The two sample orders are visible"}]}]}),
                            encoding="utf-8")
        self.draw()
        self.assertIn("`.agentforge/srs/user-journeys.json` — the journeys: who does what, step by step", self.session.tasks[-1])
        root = self.proto.parent
        self.assertTrue((root / "input/skills/journey-driven/SKILL.md").is_file())
        guide = (root / "journeys.md").read_text(encoding="utf-8")
        self.assertIn("UJ-001-S01", guide)
        self.assertIn("The two sample orders are visible", guide)
        snapshot = json.loads((root / "journeys.json").read_text(encoding="utf-8"))
        self.assertEqual(snapshot[0]["steps"][0]["expected_outcome"], "The two sample orders are visible")

    def test_the_prototype_is_a_new_app_and_the_wireframes_stay_as_they_were(self):
        self.draw()

        self.assertEqual((self.proto / "pages/home.html").read_text(encoding="utf-8"), "<h1>FRESH home</h1>")
        self.assertEqual((self.wire / "src/pages/home.tsx").read_text(encoding="utf-8"), "export default () => 'WIRE home'")
        self.assertEqual((self.wire / "bundle.html").read_text(encoding="utf-8"), "<html>wireframe</html>")
        self.assertFalse((self.proto / "bundle.html").exists(), "the prototype is bundled after the agent has written it")

    def test_nothing_of_the_wireframe_is_in_the_new_app_before_the_agent_writes(self):
        self.session.agent = lambda s: self.assertFalse((self.proto / "pages").exists(), "the wireframe's pages were copied")
        with self.assertRaises(prototyper.PrototypeIncomplete):
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")
        self.assertTrue((self.proto / "preview.json").is_file(), "the route map and demo accounts are staged")
        self.assertFalse((self.proto / "src" / "components" / "ui").exists())
        self.assertFalse((self.proto / "components.json").exists())

    def test_it_is_bundled_when_the_agent_is_done(self):
        self.draw()
        web_app.build_for.assert_called_once()
        self.assertEqual(web_app.build_for.call_args.args[1:3], (PROJECT, "prototype"))

    def test_the_html_preview_publishes_without_the_web_kit(self):
        self.draw()
        with mock.patch.object(web_app, "prepare_kit") as prepare:
            ok, message = web_app.bundle(self.proto)
        self.assertTrue(ok, message)
        prepare.assert_not_called()
        self.assertFalse(web_app.stale(self.proto))
        preview = (self.proto / "bundle.html").read_text(encoding="utf-8")
        self.assertIn('id="af-page"', preview)
        self.assertIn("FRESH kitchen", preview)
        self.assertIn("window.AgentForgePreview", preview)

    def test_what_the_build_reads_is_left_beside_the_app(self):
        self.draw()
        root = self.workspace / ".agentforge" / "prototype"
        routes = json.loads((root / "routes.json").read_text(encoding="utf-8"))["routes"]
        self.assertEqual([r["file"] for r in routes],
                         ["app/pages/home.html", "app/pages/login.html", "app/pages/register.html",
                          "app/pages/orders.html", "app/pages/kitchen.html"])
        self.assertEqual([r["signed_in"] for r in routes], [False, False, False, True, True])
        accounts = json.loads((root / "demo-accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(accounts["sign_in"], "/login")
        self.assertEqual({a["email"] for a in accounts["accounts"]}, {"customer@example.com", "baker@example.com"})
        self.assertEqual((root / "plan.md").read_text(encoding="utf-8"), "PLAN")

    def test_the_sign_in_the_prototype_demonstrates_is_the_one_the_build_is_seeded_with(self):
        self.draw()
        preview = json.loads((self.proto / "preview.json").read_text(encoding="utf-8"))
        baker = next(account for account in preview["accounts"] if account["email"] == "baker@example.com")
        self.assertEqual(baker["lands_on"], "/kitchen")
        self.assertEqual(preview["signInRoute"], "/login")
        self.assertEqual(preview["signUp"]["route"], "/register")
        request = self.session.tasks[0]
        self.assertIn("`window.AgentForgePreview.signIn(email, password)`", request)
        self.assertIn("`/login`", request)

    def test_no_page_of_the_prototype_shows_the_demo_accounts_they_are_given_in_the_chat(self):
        self.draw()
        request = self.session.tasks[0]
        self.assertNotIn("demo panel with one button", request)
        self.assertNotIn("`signInAs(roleKey)`", request)
        self.assertIn("no page shows the demo accounts", request)
        self.assertIn("in the chat", request)

    def test_a_product_without_sign_in_is_told_nothing_about_it(self):
        plain = {"app_summary": {"app_name": "Brochure"}, "public_pages": [{"page_name": "Home", "route": "/"}]}
        with mock.patch.object(document, "document", return_value={"srs_document": plain}), \
                mock.patch.object(document, "screens", return_value=plain["public_pages"]):
            self.draw()
        self.assertNotIn("signInAs", self.session.tasks[0])
        self.assertEqual(json.loads((self.proto / "preview.json").read_text(encoding="utf-8"))["accounts"], [])

    def test_an_agent_that_wrote_no_pages_leaves_the_run_to_be_carried_on(self):
        self.session.agent = None
        with self.assertRaises(prototyper.PrototypeIncomplete) as raised:
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")
        self.assertEqual(raised.exception.missing, ["index.html", "assets/prototype.css", "assets/prototype.js",
                                                    "/", "/login", "/register", "/orders", "/kitchen"])
        web_app.build_for.assert_not_called()
        self.assertFalse((self.workspace / ".agentforge/prototype/routes.json").exists())

    def test_a_screen_with_no_page_is_named_and_nothing_is_handed_over(self):
        def writes_some(session):
            self.write_html("home", "login", "register")

        self.session.agent = writes_some
        with self.assertRaises(prototyper.PrototypeIncomplete) as raised:
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")
        self.assertEqual(raised.exception.missing, ["/orders", "/kitchen"])
        web_app.build_for.assert_not_called()

    def test_a_run_that_was_carried_on_keeps_the_pages_it_wrote_and_the_direction_it_had(self):
        def writes_some(session):
            self.write_html("home", label="HALF DONE")

        self.session.agent = writes_some
        with self.assertRaises(prototyper.PrototypeIncomplete):
            prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "warm premium direction")

        def writes_the_rest(request, **_kwargs):
            name = request.split("/pages/", 1)[1].split(".html", 1)[0]
            (self.proto / "pages" / f"{name}.html").write_text(f"<h1>DONE {name}</h1>", encoding="utf-8")
            self.session.unplanned.append(request)

        self.session.run_unplanned = writes_the_rest
        self.session.unplanned.clear()
        prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")

        self.assertEqual((self.proto / "pages/home.html").read_text(encoding="utf-8"), "<h1>HALF DONE home</h1>")
        self.assertEqual(len(self.session.tasks), 1)
        self.assertIn("warm premium direction", self.session.tasks[0])
        self.assertEqual(len(self.session.unplanned), 4)
        self.assertTrue(self.session.unplanned[0].startswith("Write just `.agentforge/prototype/app/pages/login.html`"))
        self.assertIn("warm premium direction", self.session.unplanned[0])

    def test_each_page_is_published_and_checked_before_writing_the_next(self):
        self.session.agent = lambda session: self.write_html("home")
        sequence = []

        def new_page(request, **_kwargs):
            name = request.split("/pages/", 1)[1].split(".html", 1)[0]
            sequence.append(("write", name))
            self.write_html(name)

        def check(row, preview, _brief, _publish):
            name = Path(row["file"]).stem
            sequence.append(("check", name))
            self.assertIn(f"FRESH {name}", preview.read_text(encoding="utf-8"))
            self.assertFalse((self.proto / "bundle.html").exists())
            self.assertFalse((self.proto.parent / "routes.json").exists())

        self.session.run_unplanned = new_page
        prototyper.PageReview.return_value.__enter__.return_value.page.side_effect = check
        prototyper._draw_with_agent(PROJECT, {"tokens": {}}, "")
        self.assertEqual(sequence[:5], [("check", "home"), ("write", "login"), ("check", "login"),
                                        ("write", "register"), ("check", "register")])

    def test_a_changed_design_starts_a_new_app(self):
        self.draw()
        self.session.agent = None
        with self.assertRaises(prototyper.PrototypeIncomplete):
            prototyper._draw_with_agent(PROJECT, {"tokens": {"light": {"accent": "#000"}}}, "Make it warm")
        self.assertFalse((self.proto / "pages/home.html").exists(), "the earlier prototype's pages are gone")
        self.assertNotIn("Resuming", self.session.tasks[1])

    def test_the_customers_images_go_inside_the_app_and_the_originals_stay(self):
        image = self.workspace / "media" / "logo.png"
        image.parent.mkdir()
        image.write_bytes(b"logo")
        self.session.read_record = lambda *parts, fallback=None: [
            {"path": "media/logo.png", "purpose": "Brand logo"}, {"path": "media/../other.png", "purpose": "Unsafe"}]
        staged = prototyper._uploaded_site_images(self.session, self.proto)
        self.assertEqual(staged, [{"name": "logo.png", "usage": "Brand logo", "source": "media/logo.png",
                                   "file": "assets/uploads/logo.png"}])
        self.assertEqual((self.proto / "assets/uploads/logo.png").read_bytes(), b"logo")
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
            mock.patch.object(prototyper, "_look_at", lambda project, session, drawn: drawn),
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

    def test_the_prototype_is_looked_at_before_it_is_handed_over(self):
        looked = []
        self.stage(lambda *a, **k: [{"route": "/", "name": "Home"}])
        with mock.patch.object(prototyper, "_look_at", side_effect=lambda project, session, drawn: looked.append(project) or drawn):
            answer = prototyper.generate_from_wireframes(PROJECT, "")
        self.assertEqual(looked, [PROJECT])
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
        prototyper.bus.prototype_changed.reset_mock()
        (self.workspace / ".agentforge/prototype/generation.json").write_text(json.dumps({"complete": True}), encoding="utf-8")
        prototyper.revise(PROJECT, "Make the buttons rounder")
        self.assertIn("Make the buttons rounder", self.session.directs[0])
        self.assertIn(".agentforge/prototype/app", self.session.directs[0])
        self.assertEqual(web_app.build_for.call_count, 2)           # once when it was made, once now
        prototyper.bus.prototype_changed.assert_called_once_with(PROJECT)

    def test_a_drop_updates_the_html_source_and_republishes_without_a_repair_run(self):
        self.draw()
        self.session.write_record("prototype", "generation.json", data={"complete": True})
        prototyper.bus.prototype_changed.reset_mock()
        target = self.proto / "pages" / "orders.html"
        contents = '<section><p id="second">Second</p><p id="first">First</p></section>'
        with mock.patch.object(self.session, "run_direct",
                               side_effect=lambda *_args, **_kwargs: target.write_text(contents, encoding="utf-8")) as model:
            prototyper.revise(PROJECT, "Move first after second", route="/orders",
                              layout=("move", '{"placement":"after","source":{"selector":"#first"},'
                                               '"target":{"selector":"#second"}}'))
        self.assertEqual(model.call_args.kwargs["thinking_level"], "low")
        self.assertIn("`pages/orders.html`", model.call_args.args[0])
        bundle = (self.proto / "bundle.html").read_text(encoding="utf-8")
        self.assertIn(r'id=\"second\"', bundle)
        self.assertLess(bundle.index(r'id=\"second\"'), bundle.index(r'id=\"first\"'))
        prototyper.bus.prototype_changed.assert_called_once_with(PROJECT)

    def test_a_resize_republishes_the_prototype(self):
        self.draw()
        self.session.write_record("prototype", "generation.json", data={"complete": True})
        target = self.proto / "pages" / "orders.html"
        contents = '<section id="card" style="width:320px;min-height:190px">Orders</section>'
        with mock.patch.object(self.session, "run_direct",
                               side_effect=lambda *_args, **_kwargs: target.write_text(contents, encoding="utf-8")) as model:
            prototyper.revise(PROJECT, "Resize orders card", route="/orders",
                              layout=("resize", '{"handle":"se","bounds":{"x":40,"y":80,"w":320,"h":190}}'))
        self.assertEqual(model.call_args.kwargs["thinking_level"], "low")
        self.assertIn("`pages/orders.html`", model.call_args.args[0])
        self.assertIn("width:320px;min-height:190px", (self.proto / "bundle.html").read_text(encoding="utf-8"))

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


class AccountsMessageTests(unittest.TestCase):
    def pages(self, count):
        return [{"route": f"/p{n}", "name": f"Page {n}"} for n in range(count)]

    def test_a_role_that_opens_many_pages_is_told_how_many_and_the_first_few_not_all_of_them(self):
        rows = [{"route": "/login", "name": "Sign in"}] + self.pages(70)
        account = {"role": "Admin", "email": "admin@example.com", "password": "Demo!2026", "lands_on": "/p0",
                   "can_open": rows[:56], "cannot_open": rows[56:]}
        text = demo.accounts_message([account], rows, "/login")
        self.assertIn("`admin@example.com` / `Demo!2026`", text)
        self.assertIn("lands on **Page 0**", text)
        self.assertIn("can open 55 pages (Page 0, Page 1, Page 2, Page 3, Page 4, Page 5 and 49 more)", text)
        self.assertIn("cannot open 15 (Page 55, Page 56, Page 57, Page 58 and 11 more)", text)
        self.assertNotIn("Page 30", text)
        self.assertLess(len(text), 900)

    def test_a_role_that_opens_everything_says_there_is_nothing_it_cannot_open(self):
        rows = [{"route": "/login", "name": "Sign in"}] + self.pages(2)
        account = {"role": "Owner", "email": "o@example.com", "password": "Demo!2026", "lands_on": "/p1",
                   "can_open": rows, "cannot_open": []}
        text = demo.accounts_message([account], rows, "/login")
        self.assertIn("can open 2 pages (Page 0, Page 1)", text)
        self.assertTrue(text.endswith("cannot open 0"))

    def test_there_is_nothing_to_say_without_accounts(self):
        self.assertEqual(demo.accounts_message([], [], ""), "")

    def test_the_message_says_to_type_the_account_never_to_press_a_demo_button(self):
        rows = [{"route": "/login", "name": "Sign in"}]
        account = {"role": "Owner", "email": "o@example.com", "password": "Demo!2026", "lands_on": "/login",
                   "can_open": rows, "cannot_open": []}
        prototype_text = demo.accounts_message([account], rows, "/login")
        built_text = demo.accounts_message([account], rows, "/login", built=True)
        self.assertNotIn("demo buttons", prototype_text + built_text)
        self.assertIn("by typing one of these", prototype_text)
        self.assertIn("reviewing the prototype", prototype_text)
        self.assertIn("seeded into the built application", built_text)


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

            def shoot(page, out, viewport, browser, **kwargs):
                seen.update(html=Path(page).read_text(encoding="utf-8"), viewport=viewport, **kwargs)
                return out

            self.enterContext(mock.patch.object(screenshot, "working_browser", return_value=("browser", "shell")))
            with mock.patch.object(screenshot, "shoot", shoot):
                screens.shoot_page(root, self.ROWS[1], self.ACCOUNTS, root / "out.png", "mobile")
            self.assertEqual(seen["suffix"], "?as=baker%40example.com#/kitchen")
            self.assertIn(screenshot.MEASURE, seen["html"])
            self.assertEqual(seen["viewport"], "mobile")

            with mock.patch.object(screenshot, "shoot", shoot):
                screens.shoot_page(root, self.ROWS[0], self.ACCOUNTS, root / "out.png", "desktop")
            self.assertEqual(seen["suffix"], "#/")

    def test_mobile_chrome_capture_uses_the_real_viewport(self):
        with mock.patch.object(screens, "Driver") as driver_type, mock.patch.object(screenshot, "shoot") as cli:
            driver = driver_type.return_value.__enter__.return_value
            out = Path("mobile.png")
            driver.screenshot.return_value = out
            result = screens._shoot(Path("prototype.html"), out, "mobile", ("chrome.exe", "chrome"), "#/inventory", None)
        self.assertEqual(result, out)
        driver_type.assert_called_once_with(size=(390, 844), cancelled=None)
        driver.goto.assert_called_once_with(Path("prototype.html"), "#/inventory")
        driver.screenshot.assert_called_once_with(out, max_height=screenshot.MAX_HEIGHT["mobile"])
        cli.assert_not_called()

    def test_there_is_nothing_to_photograph_before_it_is_bundled(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "not bundled"):
                screens.shoot_page(Path(tmp), self.ROWS[0], [], Path(tmp) / "out.png", "desktop")


if __name__ == "__main__":
    unittest.main()
