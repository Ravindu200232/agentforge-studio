"""Pointing at things on a page and retyping its words: what is told to the agent, and the swap in the app's source."""
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

from server_modules import pointed, routes_srs, runs, web_app  # noqa: E402

HOME = '''export default function Home() {
  return (
    <main>
      <h1>Find your next book</h1>
      <p>
        Fresh arrivals every
        week, picked by hand.
      </p>
      <button title="Open the cart">Add to cart</button>
      <span>Tom &amp; Jerry's Shop</span>
      <span>Cartographer</span>
      <a href="#/books">Browse the shelves</a>
    </main>
  )
}
'''
CART = 'const rows = ["Add to cart", "Total"]\nexport default () => <h1>Your cart</h1>\n'


class Scratch(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = Path(self.temp.name) / "app"
        (self.app / "src" / "pages").mkdir(parents=True)
        (self.app / "src" / "components" / "ui").mkdir(parents=True)
        (self.app / "src" / "pages" / "home.tsx").write_bytes(HOME.encode("utf-8"))        # the line ends as written, on any system
        (self.app / "src" / "pages" / "cart.tsx").write_bytes(CART.encode("utf-8"))

    def source(self, name: str = "pages/home.tsx") -> str:
        return (self.app / "src" / name).read_text(encoding="utf-8")


class SwapTests(Scratch):
    def test_words_written_once_are_swapped_where_they_are_written(self):
        done = web_app.edit_text(self.app, "Find your next book", "Find your next story")
        self.assertEqual((done["ok"], done["file"], done["line"]), (True, "src/pages/home.tsx", 4))
        self.assertIn("<h1>Find your next story</h1>", self.source())
        self.assertEqual(done["original"], HOME)

    def test_a_paragraph_written_over_two_lines_is_found_by_the_words_the_page_shows(self):
        self.assertTrue(web_app.edit_text(self.app, "Fresh arrivals every week, picked by hand.", "New books every week.")["ok"])
        self.assertIn("        New books every week.\n      </p>", self.source())

    def test_words_that_are_also_written_somewhere_else_are_not_guessed_at(self):
        before = self.source()
        self.assertEqual(web_app.edit_text(self.app, "Add to cart", "Buy"), {"ok": False, "reason": "found in several places"})
        self.assertEqual(self.source(), before)

    def test_words_are_a_whole_piece_of_text_never_the_middle_of_another(self):
        self.assertEqual(web_app.edit_text(self.app, "Cart", "Basket"), {"ok": False, "reason": "built in code"})
        self.assertEqual(web_app.edit_text(self.app, "next", "last"), {"ok": False, "reason": "built in code"})
        self.assertEqual(web_app.edit_text(self.app, "Nothing like it", "x"), {"ok": False, "reason": "built in code"})

    def test_an_ampersand_and_a_quote_are_found_however_the_source_spells_them_and_written_so_they_hold(self):
        self.assertTrue(web_app.edit_text(self.app, "Tom & Jerry's Shop", "Tom {and} Jerry <3")["ok"])
        self.assertIn("<span>Tom &#123;and&#125; Jerry &lt;3</span>", self.source())

    def test_words_in_a_string_are_swapped_inside_the_string_with_the_quote_made_safe(self):
        self.assertTrue(web_app.edit_text(self.app, "Total", 'The "total" \\ here')["ok"])
        self.assertIn('["Add to cart", "The \\"total\\" \\\\ here"]', self.source("pages/cart.tsx"))

    def test_an_attribute_that_holds_the_words_is_a_string_like_any_other(self):
        self.assertTrue(web_app.edit_text(self.app, "Open the cart", "Open the basket")["ok"])
        self.assertIn('title="Open the basket"', self.source())

    def test_what_belongs_to_the_toolkit_and_the_studio_is_never_swapped(self):
        (self.app / "src" / "components" / "ui" / "button.tsx").write_text("export const x = <b>Only here</b>", encoding="utf-8")
        (self.app / "src" / "routes.ts").write_text('export const routes = [{ "name": "Only in the table" }]', encoding="utf-8")
        for words in ("Only here", "Only in the table"):
            self.assertEqual(web_app.edit_text(self.app, words, "x")["reason"], "built in code")

    def test_a_file_with_windows_line_ends_keeps_them(self):
        path = self.app / "src" / "pages" / "home.tsx"
        path.write_bytes(HOME.replace("\n", "\r\n").encode("utf-8"))
        self.assertTrue(web_app.edit_text(self.app, "Browse the shelves", "Browse")["ok"])
        raw = path.read_bytes()
        self.assertIn(b"Browse</a>\r\n", raw)
        self.assertEqual(raw.count(b"\r\n"), HOME.count("\n"))

    def test_there_must_be_old_words_and_new_ones(self):
        self.assertEqual(web_app.edit_text(self.app, "  ", "x")["reason"], "no words")
        self.assertEqual(web_app.edit_text(self.app, "Find your next book", "  ")["reason"], "the new words are empty")


class PointedTests(unittest.TestCase):
    ELEMENT = {"tag": "button", "text": "Add   to cart", "route": "/books/the-cartographers-daughter",
               "attrs": {"type": "button", "aria-label": "Add to cart", "data-x": "ignored"},
               "chain": [{"tag": "section", "text": "Featured"}, {"tag": "main", "text": ""}, {"tag": "div", "text": ""}, {"tag": "body"}],
               "outerHTML": '<button class="a">Add to cart</button>'}

    def test_nothing_pointed_at_is_nothing_said(self):
        for value in (None, [], "text", [3, "x"]):
            self.assertEqual(pointed.describe(value), "")

    def test_each_thing_is_named_by_its_words_where_it_is_and_what_is_around_it(self):
        text = pointed.describe([self.ELEMENT])
        for expected in ("They pointed at this on the page", "`<button>` with the words “Add to cart”", "on the page `/books/the-cartographers-daughter`",
                         'type="button"', 'aria-label="Add to cart"', "inside: <div> › <main> › <section> “Featured”",
                         '`<button class="a">Add to cart</button>`'):
            self.assertIn(expected, text)
        self.assertNotIn("data-x", text)

    def test_several_things_are_numbered_and_no_more_than_six_are_told(self):
        text = pointed.describe([{"tag": f"h{n}", "text": f"Heading {n}"} for n in range(1, 9)])
        self.assertIn("They pointed at these", text)
        self.assertIn("6. `<h6>`", text)
        self.assertNotIn("7.", text)

    def test_a_change_aimed_at_something_tells_the_agent_what_it_is(self):
        sent = []
        with mock.patch.object(runs, "agent_update", lambda message, screened=False: sent.append(message) or {"ok": True}):
            runs.element_edit({"project": "p", "route": "/prototype", "prompt": "Make it green", "elements": [self.ELEMENT]})
        self.assertIn("Make it green", sent[0]["prompt"])
        self.assertIn("`<button>` with the words “Add to cart”", sent[0]["prompt"])


class RouteTests(Scratch):
    def setUp(self):
        super().setUp()
        (self.app / "bundle.html").write_text("<html></html>", encoding="utf-8")
        self.session = SimpleNamespace(stage="idle", workspace=Path(self.temp.name))
        self.bundled: list[bool] = []
        patches = (
            mock.patch.object(routes_srs, "session_for", lambda project: self.session),
            mock.patch.object(web_app, "app_dir", lambda workspace, kind: self.app),
            mock.patch.object(web_app, "bundle", side_effect=self.bundle),
            mock.patch.object(routes_srs.bus, "wireframe_changed"),
            mock.patch.object(routes_srs.bus, "prototype_changed"),
        )
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.bundle_ok = True

    def bundle(self, app):
        self.bundled.append(self.bundle_ok)
        return (self.bundle_ok, "") if self.bundle_ok else (False, "error TS1005: broken")

    def ask(self, old="Find your next book", new="Find your next story", kind="wireframe"):
        return routes_srs.edit_app_text("p", {"kind": kind, "old": old, "new": new})

    def test_a_swap_is_bundled_and_the_studio_told_which_app_changed(self):
        done = self.ask()
        self.assertEqual((done["ok"], done["file"]), (True, "src/pages/home.tsx"))
        self.assertNotIn("original", done)
        self.assertEqual(self.bundled, [True])
        routes_srs.bus.wireframe_changed.assert_called_once_with("p")
        self.ask(old="Browse the shelves", new="Browse", kind="prototype")
        routes_srs.bus.prototype_changed.assert_called_once_with("p")

    def test_words_that_cannot_be_swapped_say_why_and_nothing_is_bundled(self):
        self.assertEqual(self.ask(old="Add to cart")["reason"], "found in several places")
        self.assertEqual(self.bundled, [])
        routes_srs.bus.wireframe_changed.assert_not_called()

    def test_a_swap_that_does_not_bundle_is_put_back_and_the_page_that_is_shown_is_made_again(self):
        self.bundle_ok = False
        done = self.ask()
        self.assertEqual((done["ok"], done["reason"]), (False, "does not bundle"))
        self.assertIn("TS1005", done["detail"])
        self.assertEqual(self.source(), HOME)
        self.assertEqual(self.bundled, [False, False])
        routes_srs.bus.wireframe_changed.assert_not_called()

    def test_nothing_is_swapped_under_an_agent_that_is_still_working_or_in_an_app_that_is_not_drawn(self):
        for stage in ("wireframes", "prototype-edit", "build"):
            self.session.stage = stage
            with self.assertRaisesRegex(ValueError, "wait for the agent"):
                self.ask()
        self.session.stage = "idle"
        (self.app / "bundle.html").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "not drawn"):
            self.ask()
        with self.assertRaisesRegex(ValueError, "wireframes or on the prototype"):
            self.ask(kind="design")
        self.assertEqual(self.source(), HOME)


class StudioTests(unittest.TestCase):
    """The tools are in the Studio's views (their behaviour is tried in a browser, not here)."""

    def read(self, *parts: str) -> str:
        return (ROOT / "studio" / Path(*parts)).read_text(encoding="utf-8")

    def test_the_wireframe_page_view_has_the_select_pencil_and_text_tools_and_sends_what_was_pointed_at(self):
        view = self.read("components", "srs", "Wireframes.jsx")
        for expected in ("useFrameTools(frame", "<ToolButtons", "<DrawLayer", "<Chips", "<AppTextEdit", 'kind="wireframe"',
                         "api.editWireframe(srsId, request, route, elements)", "tools.elements"):
            self.assertIn(expected, view)

    def test_the_prototype_pane_has_the_text_tool_beside_select_and_pencil(self):
        pane = self.read("components", "PrototypePane.jsx")
        for expected in ("toggleText", "<Type className", "<AppTextEdit", 'kind="prototype"', "api.editPrototype(",
                         "elementsUnderStrokes(frameRef.current, strokes, vp)"):
            self.assertIn(expected, pane)

    def test_the_chat_tells_the_agent_what_each_drawing_was_around(self):
        chat = self.read("components", "AgentChat.jsx")
        self.assertIn("selection.flatMap(s => (s.kind === 'element' ? [s.info] : s.marked || []))", chat)

    def test_the_api_has_the_three_calls(self):
        api = self.read("lib", "api.js")
        for expected in ("editWireframe: (srsId, prompt, route = '', elements = [])", "editPrototype: (project, prompt, elements = [])",
                         "editAppText: (project, kind, old, text)", "/app/text-edit", "/prototype/edit"):
            self.assertIn(expected, api)

    def test_the_picker_gives_the_route_of_a_screen_kept_in_the_hash_and_finds_what_a_drawing_is_around(self):
        picker = self.read("lib", "picker.js")
        for expected in ("function appRoute(w)", "hash.startsWith('#/')", "export function ownText", "export function elementsUnderStrokes"):
            self.assertIn(expected, picker)


if __name__ == "__main__":
    unittest.main()
