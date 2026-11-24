"""Generated HTML wireframes, their Studio metadata, and static serving."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import httpd, prompts, routes_srs, web_app  # noqa: E402
from srs_agent import document, wireframe  # noqa: E402
from test_wireframe import FakeSession, PAGES  # noqa: E402

PROJECT = "prj_bakery"
FILES = ["home.html", "orders-id.html", "orders.html"]


class Scratch(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = Path(self.folder.name)
        (self.workspace / ".agentforge" / "srs" / "handoff").mkdir(parents=True)
        (self.workspace / ".agentforge" / "srs" / "handoff" / "app.md").write_text("# Bakery", encoding="utf-8")
        self.session = FakeSession(self.workspace)
        self.session.agent = self.draws
        self.draw = list(FILES)
        for patcher in (
            mock.patch.object(wireframe, "session_for", lambda project: self.session),
            mock.patch.object(document, "session_for", lambda project: self.session),
            mock.patch.object(wireframe.document, "screens", return_value=PAGES),
            mock.patch.object(wireframe.document, "document",
                              return_value={"srs_document": {"app_summary": {"app_name": "Sweet <Crumbs>"}}}),
            mock.patch.object(wireframe.bus, "agent_msg"),
            mock.patch.object(wireframe.bus, "phase"),
            mock.patch.object(wireframe.bus, "wireframe_changed"),
            mock.patch.object(wireframe, "Review"),
            mock.patch.object(wireframe.bus, "log"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.out = self.workspace / ".agentforge" / "wireframe-html"

    def draws(self, session):
        """What the agent does: a page file for each name it is given."""
        (self.out / "assets").mkdir(parents=True, exist_ok=True)
        for name in self.draw:
            (self.out / name).write_text(f"<!doctype html><title>{name}</title><h1>{name}</h1>", encoding="utf-8")


class GeneratingTests(Scratch):
    def test_the_agent_is_told_the_html_files_to_write_and_where(self):
        wireframe.generate_html(PROJECT)
        request = self.session.tasks[0]
        self.assertTrue(request.startswith("Generate low-fidelity wireframes as plain HTML."))
        self.assertIn("`.agentforge/wireframe-html`", request)
        self.assertIn("- `/` — Home — `home.html`", request)
        self.assertIn("- `/orders/[id]` — Order (signed in: Owner) — `orders-id.html`", request)
        self.assertIn("web_search", request)
        self.assertNotIn("{{", request)
        self.assertFalse(self.session.kwargs["audit"])

    def test_the_brief_is_the_same_one_with_html_in_place_of_react(self):
        text = prompts.load("wireframe/html")
        for expected in ("assets/wireframe.css", "assets/wireframe.js", "3. RESEARCH BEFORE DESIGN", "14. QUALITY ASSURANCE",
                         "Five to eight believable sample rows", "{{routes}}", "{{app}}", "{{resume}}"):
            self.assertIn(expected, text)
        for gone in ("shadcn", "@/lib/router", "Tailwind CSS 3", "tsx"):
            self.assertNotIn(gone, text)

    def test_a_gallery_page_lists_every_page_and_says_which_are_not_drawn(self):
        self.draw = ["home.html", "orders.html"]
        done = wireframe.generate_html(PROJECT)
        self.assertEqual((done["ok"], done["written"], done["total"], done["missing"]), (False, 2, 3, ["/orders/[id]"]))
        index = (self.out / "index.html").read_text(encoding="utf-8")
        self.assertIn('href="home.html"', index)
        self.assertIn('href="orders.html"', index)
        self.assertNotIn('href="orders-id.html"', index)
        self.assertIn("not drawn", index)
        self.assertIn("Sweet &lt;Crumbs&gt;", index)                       # the name is escaped, never markup

    def test_the_studio_lists_static_filenames_for_drawn_and_pending_pages(self):
        self.draw = ["home.html", "orders.html"]
        wireframe.generate(PROJECT)
        (self.out / "index.html").unlink()
        pages = document.wireframes(PROJECT)["pages"]
        self.assertEqual([page["html_file"] for page in pages], FILES)
        self.assertEqual([page["has_html"] for page in pages], [True, False, True])
        self.assertGreater(pages[0]["version"], 0)

    def test_a_fresh_run_starts_the_folder_again_and_a_carried_on_run_keeps_the_pages(self):
        self.out.mkdir(parents=True)
        (self.out / "old.html").write_text("old", encoding="utf-8")
        self.draw = []
        wireframe.generate_html(PROJECT)
        self.assertFalse((self.out / "old.html").exists())
        (self.out / "kept.html").write_text("kept", encoding="utf-8")
        wireframe.generate_html(PROJECT, fresh=False)
        self.assertTrue((self.out / "kept.html").exists())
        self.assertIn("The folder already has pages from a run that stopped", self.session.tasks[-1])

    def test_the_react_wireframes_are_not_touched(self):
        react = web_app.app_dir(self.workspace, "wireframe")
        (react / "src").mkdir(parents=True)
        (react / "src" / "keep.tsx").write_text("keep", encoding="utf-8")
        (react / "bundle.html").write_text("<html></html>", encoding="utf-8")
        wireframe.generate_html(PROJECT)
        self.assertEqual((react / "src" / "keep.tsx").read_text(encoding="utf-8"), "keep")
        self.assertTrue((react / "bundle.html").exists())

    def test_a_run_needs_screens_and_the_handoff(self):
        with mock.patch.object(wireframe.document, "screens", return_value=[]):
            with self.assertRaisesRegex(ValueError, "no screens"):
                wireframe.generate_html(PROJECT)
        (self.workspace / ".agentforge" / "srs" / "handoff" / "app.md").unlink()
        with self.assertRaisesRegex(ValueError, "handoff is missing"):
            wireframe.generate_html(PROJECT)


class RunningTests(Scratch):
    def test_a_whole_run_says_where_to_open_the_pages(self):
        done = wireframe.run_html(PROJECT)
        self.assertTrue(done["ok"])
        self.assertEqual(done["url"], f"/__agentforge/api/web/{PROJECT}/wireframe-html/index.html")
        self.assertEqual(self.session.events, ["begin wireframes", "finish The HTML wireframes are ready: 3 of 3 page(s)."])
        said = wireframe.bus.agent_msg.call_args
        self.assertEqual(said.kwargs["title"], "HTML wireframes ready")
        self.assertIn(done["url"], said.args[1])

    def test_a_failure_is_told_and_raised(self):
        with mock.patch.object(wireframe.document, "screens", return_value=[]):
            with self.assertRaises(ValueError):
                wireframe.run_html(PROJECT)
        self.assertTrue(any(event.startswith("fail") for event in self.session.events), self.session.events)


class MovingTests(Scratch):
    def test_drop_edits_the_drawn_page_at_low_effort_and_publishes(self):
        self.draws(self.session)
        page = self.out / "orders.html"
        page.write_text('<button id="search">Search</button><button id="filter">Filter</button>', encoding="utf-8")
        other = (self.out / "home.html").read_bytes()
        path = f"/projects/{PROJECT}/app/move"
        body = {"kind": "wireframe", "route": "/orders",
                "move": {"source": {"selector": "#search"}, "target": {"selector": "#filter"},
                         "placement": "after", "point": {"x": 420, "y": 160}}}

        def edit(_prompt, **_kwargs):
            page.write_text('<button id="filter">Filter</button><button id="search">Search</button>', encoding="utf-8")

        with mock.patch.object(routes_srs, "session_for", return_value=self.session), \
             mock.patch.object(routes_srs.privacy, "screen", side_effect=lambda _project, text: text), \
             mock.patch.object(self.session, "run_direct", side_effect=edit) as model:
            self.assertEqual(routes_srs.dispatch("POST", path, body), {"ok": True, "route": "/orders"})
        self.assertEqual(model.call_args.kwargs["thinking_level"], "low")
        request = model.call_args.args[0]
        for expected in ("`orders.html`", '"placement": "after"', "#search", "#filter", '"x": 420'):
            self.assertIn(expected, request)
        self.assertEqual((self.out / "home.html").read_bytes(), other)
        wireframe.bus.wireframe_changed.assert_called_once_with(PROJECT)

    def test_unchanged_source_is_reported_as_a_failed_move(self):
        self.draws(self.session)
        with self.assertRaisesRegex(ValueError, "could not move"):
            wireframe.edit(PROJECT, "Move a button", "/", layout=("move", '{"placement":"after"}'))
        wireframe.bus.wireframe_changed.assert_not_called()

    def test_resize_posts_the_requested_bounds_at_low_effort(self):
        self.draws(self.session)
        page = self.out / "orders.html"
        page.write_text('<section id="card" style="width:220px">Orders</section>', encoding="utf-8")
        path = f"/projects/{PROJECT}/app/resize"
        before = {"x": 40, "y": 80, "w": 220, "h": 140}
        after = {**before, "w": 300}
        body = {"kind": "wireframe", "route": "/orders",
                "resize": {"source": {"selector": "#card", "rect": before}, "handle": "e", "bounds": after}}
        with mock.patch.object(routes_srs, "session_for", return_value=self.session), \
             mock.patch.object(routes_srs.privacy, "screen", side_effect=lambda _project, text: text), \
             mock.patch.object(self.session, "run_direct",
                               side_effect=lambda *_args, **_kwargs: page.write_text(
                                   '<section id="card" style="width:300px">Orders</section>', encoding="utf-8")) as model:
            with self.assertRaisesRegex(ValueError, "size did not change"):
                routes_srs.dispatch("POST", path, {**body, "resize": {**body["resize"], "bounds": before}})
            self.assertEqual(routes_srs.dispatch("POST", path, body), {"ok": True, "route": "/orders"})

        model.assert_called_once()
        self.assertEqual(model.call_args.kwargs["thinking_level"], "low")
        for expected in ('Resize one existing element', '`orders.html`', '#card', '"handle": "e"', '"w": 300'):
            self.assertIn(expected, model.call_args.args[0])
        wireframe.bus.wireframe_changed.assert_called_once_with(PROJECT)

    def test_wireframe_insert_renders_the_shape_details_and_rejects_prototype(self):
        self.draws(self.session)
        page = self.out / "home.html"
        path = f"/projects/{PROJECT}/app/insert"
        body = {"kind": "wireframe", "route": "/",
                "insert": {"shape": "textbox", "target": {"selector": "body", "rect": {"x": 8, "y": 8}},
                           "bounds": {"x": 50, "y": 60, "w": 180, "h": 70}, "text": "New caption"}}
        with mock.patch.object(routes_srs, "session_for", return_value=self.session), \
             mock.patch.object(routes_srs.privacy, "screen", side_effect=lambda _project, text: text), \
             mock.patch.object(self.session, "run_direct",
                               side_effect=lambda *_args, **_kwargs: page.write_text(
                                   "<p>New caption</p>", encoding="utf-8")) as model:
            with self.assertRaisesRegex(ValueError, "available on wireframes"):
                routes_srs.dispatch("POST", path, {**body, "kind": "prototype"})
            self.assertTrue(routes_srs.dispatch("POST", path, body)["ok"])
        model.assert_called_once()
        self.assertEqual(model.call_args.kwargs["thinking_level"], "low")
        for expected in ('Add one element', '`home.html`', '"shape": "textbox"', '"w": 180', '"text": "New caption"',
                         '"offset_within_target": {"x": 42, "y": 52}'):
            self.assertIn(expected, model.call_args.args[0])

    def test_move_and_resize_for_one_element_are_applied_by_one_edit(self):
        self.draws(self.session)
        source = {"selector": "#box", "rect": {"x": 50, "y": 60, "w": 180, "h": 70}}
        body = {"kind": "wireframe", "route": "/", "layout": {
            "move": {"source": source, "target": {"selector": "#other"}, "placement": "after"},
            "resize": {"source": source, "handle": "e", "bounds": {**source["rect"], "w": 240}},
        }}
        page = self.out / "home.html"
        with mock.patch.object(routes_srs, "session_for", return_value=self.session), \
             mock.patch.object(routes_srs.privacy, "screen", side_effect=lambda _project, text: text), \
             mock.patch.object(self.session, "run_direct",
                               side_effect=lambda *_args, **_kwargs: page.write_text(
                                   '<div id="other"></div><div id="box" style="width:240px"></div>',
                                   encoding="utf-8")) as model:
            self.assertTrue(routes_srs.dispatch("POST", f"/projects/{PROJECT}/app/layout", body)["ok"])
        self.assertIn("Move and resize one existing element", model.call_args.args[0])
        self.assertIn('"w": 240', model.call_args.args[0])
        model.assert_called_once()


class ServingTests(Scratch):
    def setUp(self):
        super().setUp()
        wireframe.generate_html(PROJECT)
        (self.out / "assets" / "wireframe.css").write_text("body{margin:0}", encoding="utf-8")
        (self.out / "assets" / "wireframe.js").write_text("console.log(1)", encoding="utf-8")
        for patcher in (mock.patch.object(httpd, "_project", lambda ctx: PROJECT),
                        mock.patch.object(httpd.wireframer, "session_for", lambda project: self.session)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def get(self, name):
        match = SimpleNamespace(group=lambda key: name)
        return httpd.wireframe_html_file({"_match": match})

    def test_a_page_is_served_with_a_policy_that_lets_it_read_its_own_stylesheet_and_nothing_else(self):
        answer = self.get("home.html")
        self.assertEqual(answer.content_type, "text/html; charset=utf-8")
        text = answer.body.decode("utf-8")
        self.assertIn('http-equiv="Content-Security-Policy"', text)
        self.assertIn("style-src 'self'", text)
        self.assertIn("connect-src 'none'", text)

    def test_the_gallery_is_the_address_with_no_name_and_the_stylesheet_and_script_have_their_types(self):
        self.assertIn(b"wireframes as plain HTML", self.get("").body)
        self.assertEqual(self.get("assets/wireframe.css").content_type, "text/css; charset=utf-8")
        self.assertEqual(self.get("assets/wireframe.js").content_type, "text/javascript; charset=utf-8")

    def test_design_preview_applies_palette_and_fonts_to_home_without_writing_it(self):
        source = self.out / "home.html"
        original = source.read_bytes()
        query = {"colors": "#12372a,#436850,#a3bc9f,#f1f8e8", "heading": "DM Serif Display", "body": "DM Sans"}
        result = httpd.dispatch("GET", f"/web/{PROJECT}/wireframe-html/design-preview", query=query)
        self.assertIn(b"<h1>home.html</h1>", result.body)
        self.assertIn(b"--af-primary:#12372a", result.body)
        self.assertIn(b'--af-heading-font:"DM Serif Display"', result.body)
        self.assertIn(b'https://fonts.googleapis.com/css2?', result.body)
        self.assertEqual(source.read_bytes(), original)

    def test_design_preview_rejects_invalid_fonts_and_reports_missing_home(self):
        query = {"colors": "#12372a,#436850,#a3bc9f,#f1f8e8", "heading": 'x"}', "body": "DM Sans"}
        with self.assertRaises(httpd.HttpError) as bad:
            httpd.dispatch("GET", f"/web/{PROJECT}/wireframe-html/design-preview", query=query)
        self.assertEqual(bad.exception.status, 400)
        (self.out / "home.html").unlink()
        with self.assertRaisesRegex(httpd.HttpError, "Draw the home wireframe") as missing:
            httpd.dispatch("GET", f"/web/{PROJECT}/wireframe-html/design-preview", query=query)
        self.assertEqual(missing.exception.status, 404)

    def test_nothing_outside_the_folder_is_ever_served(self):
        (self.workspace / "secret.txt").write_text("secret", encoding="utf-8")
        for name in ("../../secret.txt", "..%2F..%2Fsecret.txt", "nothing.html"):
            with self.assertRaises(httpd.HttpError) as caught:
                self.get(name)
            self.assertEqual(caught.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
