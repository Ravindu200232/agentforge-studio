"""Silent screenshots of the prototype's pages: one built React app, one hash route per page."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import screenshot  # noqa: E402
from prototype_agent import screens  # noqa: E402

ROWS = [{"route": "/", "file": "app/src/App.tsx", "name": "Home", "roles": [], "signed_in": False},
        {"route": "/dashboard", "file": "app/src/App.tsx", "name": "Admin dashboard", "roles": ["admin"], "signed_in": True},
        {"route": "/orders/[id]", "file": "app/src/App.tsx", "name": "Order detail", "roles": ["customer"], "signed_in": True}]

# What a built bundle is: one page that draws whichever route the hash names.
BUNDLE = ("<!doctype html><html><head><meta charset=utf-8><title>app</title></head><body><div id=root></div>"
          "<script>document.getElementById('root').textContent='ROUTE:'+(location.hash.slice(1)||'/')</script></body></html>")


def make_prototype(folder: Path) -> Path:
    root = folder / "prototype"
    (root / "app").mkdir(parents=True)
    (root / "app" / "bundle.html").write_text(BUNDLE, encoding="utf-8")
    (root / "review").mkdir()
    (root / "review" / "old.png").write_bytes(b"old")
    return root


class FindPageTests(unittest.TestCase):
    def test_a_page_is_found_by_route_name_or_file_name_form_however_the_model_writes_it(self):
        for target in ("/dashboard", "dashboard", "#/dashboard", "`/dashboard`", "Admin dashboard", "admin dashboard"):
            self.assertEqual(screens.find_page(ROWS, target)["route"], "/dashboard", target)
        self.assertEqual(screens.find_page(ROWS, "orders-id")["route"], "/orders/[id]")

    def test_nothing_or_a_slash_is_the_home_page_and_an_unknown_page_is_none(self):
        self.assertEqual(screens.find_page(ROWS, "")["route"], "/")
        self.assertEqual(screens.find_page(ROWS, "/")["route"], "/")
        self.assertIsNone(screens.find_page(ROWS, "/nowhere"))
        self.assertIsNone(screens.find_page([], "/dashboard"))


class MeasuredCopyTests(unittest.TestCase):
    def test_the_copy_ends_with_the_height_measure_and_the_bundle_is_not_touched(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            copy = screens.measured_copy(screens.bundle_of(root), Path(folder) / "copy.html")
            text = copy.read_text(encoding="utf-8")
            self.assertIn(screenshot.HEIGHT_MARK, text)
            self.assertLess(text.index(screenshot.HEIGHT_MARK), text.rindex("</body>"))
            self.assertEqual(screens.bundle_of(root).read_text(encoding="utf-8"), BUNDLE)

    def test_a_page_without_a_body_still_gets_the_measure(self):
        with tempfile.TemporaryDirectory() as folder:
            bundle = Path(folder) / "bundle.html"
            bundle.write_text("<p>bare</p>", encoding="utf-8")
            copy = screens.measured_copy(bundle, Path(folder) / "copy.html")
            self.assertTrue(copy.read_text(encoding="utf-8").endswith(screenshot.MEASURE))


class CaptureAllTests(unittest.TestCase):
    def test_every_page_is_photographed_at_both_widths_at_its_own_route_and_the_results_say_where(self):
        seen = []

        def shoot(page, out, viewport, browser=None, seconds=0, cancelled=None, fragment=""):
            seen.append((Path(page).name, viewport, fragment, screenshot.HEIGHT_MARK in Path(page).read_text(encoding="utf-8")))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"png" * 300)
            return out

        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            progress = []
            with mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")), \
                    mock.patch.object(screenshot, "shoot", side_effect=shoot):
                shots = screens.capture_all(root, ROWS, on_done=lambda done, total: progress.append((done, total)))
            files = sorted(p.name for p in (root / "review").glob("*.png") if p.name != "old.png")   # old.png: an earlier review's
        self.assertEqual(len(shots), 6)
        self.assertEqual(sorted(seen), sorted([
            ("app.html", "desktop", "#/", True), ("app.html", "mobile", "#/", True),
            ("app.html", "desktop", "#/dashboard", True), ("app.html", "mobile", "#/dashboard", True),
            ("app.html", "desktop", "#/orders/1", True), ("app.html", "mobile", "#/orders/1", True)]))
        self.assertEqual(sorted(s["path"] for s in shots), sorted(f"review/{n}" for n in files))
        self.assertIn("dashboard-mobile.png", files)
        self.assertIn("orders-id-desktop.png", files)
        self.assertEqual(max(progress), (6, 6))
        self.assertTrue(all(s["error"] == "" and s["route"] for s in shots))

    def test_a_page_that_will_not_draw_costs_that_page_and_nothing_else(self):
        def shoot(page, out, viewport, browser=None, seconds=0, cancelled=None, fragment=""):
            if fragment == "#/dashboard":
                raise ValueError("took too long")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"png" * 300)
            return out

        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            with mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")), \
                    mock.patch.object(screenshot, "shoot", side_effect=shoot):
                shots = screens.capture_all(root, ROWS)
        failed = [s for s in shots if not s["path"]]
        self.assertEqual({s["route"] for s in failed}, {"/dashboard"})
        self.assertEqual(failed[0]["error"], "took too long")
        self.assertEqual(len([s for s in shots if s["path"]]), 4)

    def test_no_browser_that_works_and_no_built_prototype_are_said_plainly(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            with mock.patch.object(screenshot, "working_browser", return_value=None), self.assertRaisesRegex(ValueError, "no browser"):
                screens.capture_all(root, ROWS)
            (root / "app" / "bundle.html").unlink()
            with self.assertRaisesRegex(ValueError, "not built"):
                screens.capture_all(root, ROWS)
            with self.assertRaisesRegex(ValueError, "not built"):
                screens.shoot_page(root, ROWS[0], root / "x.png", "desktop")

    def test_the_temporary_copies_are_removed(self):
        made = []
        real = tempfile.mkdtemp

        def tracking(*args, **kwargs):
            path = real(*args, **kwargs)
            made.append(path)
            return path

        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            with mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")), \
                    mock.patch.object(screens.tempfile, "mkdtemp", side_effect=tracking), \
                    mock.patch.object(screenshot, "shoot", side_effect=lambda page, out, *a, **k: (out.parent.mkdir(parents=True, exist_ok=True), out.write_bytes(b"p" * 600), out)[2]):
                screens.capture_all(root, ROWS)
                screens.shoot_page(root, ROWS[0], root / "one.png", "desktop")
        self.assertTrue(made)
        self.assertFalse([p for p in made if Path(p).exists()])


@unittest.skipUnless(screenshot.working_browser(), "no browser that takes screenshots here")
class RealBrowserTests(unittest.TestCase):
    def test_the_browser_really_opens_the_page_the_hash_names(self):
        """A real headless browser opens the measured copy at one route and the app draws that route."""
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            copy = screens.measured_copy(screens.bundle_of(root), Path(folder) / "app.html")
            browser = screenshot.working_browser()
            profile = tempfile.mkdtemp(prefix="agentforge-test-")
            try:
                done = screenshot._run([browser[0], *screenshot._flags(browser[1], profile, 800, 600), "--dump-dom",
                                        copy.resolve().as_uri() + "#/dashboard"], 40)
            finally:
                import shutil
                shutil.rmtree(profile, ignore_errors=True)
        self.assertIn("ROUTE:/dashboard", done.stdout)

    def test_shoot_adds_the_fragment_to_a_file_and_saves_a_picture(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            out = screens.shoot_page(root, ROWS[1], Path(folder) / "dashboard.png", "mobile")
            self.assertGreater(out.stat().st_size, 500)


if __name__ == "__main__":
    unittest.main()
