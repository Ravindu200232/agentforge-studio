"""The same wireframes as plain HTML pages: drawn beside the React app, to compare them with it."""
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

from server_modules import httpd, prompts, web_app  # noqa: E402
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

    def test_nothing_outside_the_folder_is_ever_served(self):
        (self.workspace / "secret.txt").write_text("secret", encoding="utf-8")
        for name in ("../../secret.txt", "..%2F..%2Fsecret.txt", "nothing.html"):
            with self.assertRaises(httpd.HttpError) as caught:
                self.get(name)
            self.assertEqual(caught.exception.status, 404)


if __name__ == "__main__":
    unittest.main()
