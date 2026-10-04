"""Silent screenshots of the prototype's pages, each shown as a role that can open it."""
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
from prototype_agent import prototype_brief, screens  # noqa: E402

ROWS = [{"route": "/", "file": "index.html", "name": "Home", "roles": [], "signed_in": False},
        {"route": "/dashboard", "file": "dashboard.html", "name": "Admin dashboard", "roles": ["admin"], "signed_in": True},
        {"route": "/my-orders", "file": "my-orders.html", "name": "My orders", "roles": ["customer"], "signed_in": True}]
ACCOUNTS = [{"role": "Admin", "role_key": "admin", "display_name": "Ada Admin", "email": "ada@example.test", "password": "demo",
             "lands_on": "/dashboard", "can_open": [{"route": "/dashboard"}]},
            {"role": "Customer", "role_key": "customer", "display_name": "Cy Customer", "email": "cy@example.test", "password": "demo",
             "lands_on": "/my-orders", "can_open": [{"route": "/my-orders"}]}]

PAGE = "<!doctype html><html><head><meta charset=utf-8><title>{name}</title><script src='assets/flow.js'></script></head><body><h1>{name}</h1><p id=who></p></body></html>"


def make_prototype(folder: Path) -> Path:
    root = folder / "prototype"
    (root / "assets").mkdir(parents=True)
    (root / "assets" / "flow.js").write_text(prototype_brief.flow_script(ROWS, {"journeys": []}, ACCOUNTS, "/", None), encoding="utf-8")
    for row in ROWS:
        (root / row["file"]).write_text(PAGE.format(name=row["name"]), encoding="utf-8")
    (root / "review").mkdir()
    (root / "review" / "old.png").write_bytes(b"old")
    (root / "input").mkdir()
    (root / "input" / "app.md").write_text("# app", encoding="utf-8")
    return root


class WhichRoleTests(unittest.TestCase):
    def test_a_public_page_is_shown_signed_out_and_a_signed_in_one_as_a_role_that_can_open_it(self):
        self.assertEqual(screens.role_for(ROWS[0], ACCOUNTS), "")
        self.assertEqual(screens.role_for(ROWS[1], ACCOUNTS), "ada@example.test")
        self.assertEqual(screens.role_for(ROWS[2], ACCOUNTS), "cy@example.test")

    def test_a_signed_in_page_nobody_lists_falls_back_to_the_first_account_and_no_accounts_means_signed_out(self):
        orphan = {"route": "/x", "file": "x.html", "signed_in": True}
        self.assertEqual(screens.role_for(orphan, ACCOUNTS), "ada@example.test")
        self.assertEqual(screens.role_for(orphan, []), "")

    def test_a_prototype_drawn_before_pages_were_flagged_is_read_by_the_roles_that_open_each_page(self):
        public = {"route": "/cart", "file": "cart.html", "roles": ["Visitor", "Customer"]}
        owner_only = {"route": "/dashboard", "file": "dashboard.html", "roles": ["Admin"]}
        self.assertEqual(screens.role_for(public, ACCOUNTS), "")                       # a visitor can open it: shown signed out
        self.assertEqual(screens.role_for(owner_only, ACCOUNTS), "ada@example.test")
        self.assertEqual(screens.role_for({"route": "/x", "file": "x.html"}, ACCOUNTS), "")     # no roles at all: public

    def test_the_route_list_may_be_spelled_either_way_the_prototype_saves_it(self):
        camel = [{**ACCOUNTS[0], "can_open": None, "canOpen": ["/dashboard"]}, ACCOUNTS[1]]
        self.assertEqual(screens.role_for(ROWS[1], camel), "ada@example.test")


class FindPageTests(unittest.TestCase):
    def test_a_page_is_found_by_file_route_or_name_however_the_model_writes_it(self):
        for target in ("dashboard.html", "/dashboard", "dashboard", "Admin dashboard", "  `dashboard.html` ", "dashboard.html#top", "DASHBOARD.HTML"):
            with self.subTest(target=target):
                self.assertEqual(screens.find_page(Path("."), target, ROWS)["file"], "dashboard.html")

    def test_nothing_or_a_slash_is_the_home_page_and_an_unknown_page_is_none(self):
        self.assertEqual(screens.find_page(Path("."), "", ROWS)["file"], "index.html")
        self.assertEqual(screens.find_page(Path("."), "/", ROWS)["file"], "index.html")
        self.assertIsNone(screens.find_page(Path("."), "/nowhere", ROWS))
        self.assertIsNone(screens.find_page(Path("."), "x", []))


class CopyTests(unittest.TestCase):
    def test_a_copy_signed_in_as_a_role_sets_the_session_before_anything_on_the_page_runs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            screens.copy_for(root, Path(folder) / "ada", "ada@example.test")
            html = (Path(folder) / "ada" / "dashboard.html").read_text(encoding="utf-8")
        seed = html.index("localStorage.setItem")
        self.assertLess(seed, html.index("assets/flow.js"))            # before the page's own scripts
        self.assertIn("ada@example.test", html)
        self.assertIn(screens.SESSION_KEY, html)
        self.assertIn(screenshot.HEIGHT_MARK, html)                     # and the height is measured at the end
        self.assertLess(html.index("assets/flow.js"), html.index(screenshot.HEIGHT_MARK))

    def test_a_signed_out_copy_sets_no_session(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            screens.copy_for(root, Path(folder) / "out", "")
            html = (Path(folder) / "out" / "index.html").read_text(encoding="utf-8")
        self.assertNotIn("localStorage.setItem", html)
        self.assertIn(screenshot.HEIGHT_MARK, html)

    def test_the_review_pictures_and_the_working_files_are_not_copied_but_the_assets_are(self):
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            screens.copy_for(root, Path(folder) / "copy", "")
            names = {p.relative_to(Path(folder) / "copy").as_posix() for p in (Path(folder) / "copy").rglob("*") if p.is_file()}
        self.assertIn("assets/flow.js", names)
        self.assertIn("dashboard.html", names)
        self.assertFalse([n for n in names if n.startswith(("review/", "input/"))])

    def test_an_email_cannot_break_out_of_the_script_it_is_written_into(self):
        seed = screens._seed("a'b\\c@example.test")
        self.assertIn("abc@example.test", seed)             # the quote and the backslash are dropped, not escaped
        self.assertNotIn("a'b", seed)
        self.assertNotIn("\\", seed)

    def test_a_page_without_a_head_or_body_still_gets_both_scripts(self):
        html = screens.with_scripts("<h1>bare</h1>", screens._seed("a@b.test"))
        self.assertTrue(html.startswith("<script>"))
        self.assertTrue(html.rstrip().endswith("</script>"))
        self.assertIn(screenshot.HEIGHT_MARK, html)


class CaptureAllTests(unittest.TestCase):
    def test_every_page_is_photographed_at_both_widths_signed_in_as_its_own_role_and_the_results_say_where(self):
        seen = []

        def shoot(page, out, viewport, browser=None, seconds=0):
            html = Path(page).read_text(encoding="utf-8")
            seen.append((Path(page).name, viewport, "ada@example.test" in html, "cy@example.test" in html, "setItem" in html))
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"png" * 300)
            return out

        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            progress = []
            with mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")), \
                    mock.patch.object(screenshot, "shoot", side_effect=shoot):
                shots = screens.capture_all(root, ROWS, ACCOUNTS, on_done=lambda done, total: progress.append((done, total)))
            files = sorted(p.name for p in (root / "review").glob("*.png") if p.name != "old.png")   # old.png: an earlier review's
        self.assertEqual(len(shots), 6)
        self.assertEqual(sorted(seen), sorted([
            ("index.html", "desktop", False, False, False), ("index.html", "mobile", False, False, False),
            ("dashboard.html", "desktop", True, False, True), ("dashboard.html", "mobile", True, False, True),
            ("my-orders.html", "desktop", False, True, True), ("my-orders.html", "mobile", False, True, True)]))
        self.assertEqual(sorted(s["path"] for s in shots), sorted(f"review/{n}" for n in files))
        self.assertIn("dashboard-mobile.png", files)
        self.assertEqual(max(progress), (6, 6))
        self.assertTrue(all(s["error"] == "" for s in shots))

    def test_a_page_that_will_not_draw_costs_that_page_and_nothing_else(self):
        def shoot(page, out, viewport, browser=None, seconds=0):
            if Path(page).name == "dashboard.html":
                raise ValueError("took too long")
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b"png" * 300)
            return out

        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            with mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")), \
                    mock.patch.object(screenshot, "shoot", side_effect=shoot):
                shots = screens.capture_all(root, ROWS, ACCOUNTS)
        failed = [s for s in shots if not s["path"]]
        self.assertEqual({s["file"] for s in failed}, {"dashboard.html"})
        self.assertEqual(failed[0]["error"], "took too long")
        self.assertEqual(len([s for s in shots if s["path"]]), 4)

    def test_no_browser_that_works_is_said_plainly(self):
        with mock.patch.object(screenshot, "working_browser", return_value=None), self.assertRaisesRegex(ValueError, "no browser"):
            screens.capture_all(Path("."), ROWS, ACCOUNTS)

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
                screens.capture_all(root, ROWS, ACCOUNTS)
        self.assertTrue(made)
        self.assertFalse([p for p in made if Path(p).exists()])


@unittest.skipUnless(screenshot.working_browser(), "no browser that takes screenshots here")
class RealBrowserTests(unittest.TestCase):
    def test_the_demo_session_really_is_in_place_when_the_page_runs(self):
        """A real headless browser opens the signed-in copy: the page reads the session `flow.js` keeps in local storage."""
        with tempfile.TemporaryDirectory() as folder:
            root = make_prototype(Path(folder))
            page = root / "dashboard.html"
            page.write_text(page.read_text(encoding="utf-8").replace(
                "<p id=who></p>", "<p id=who></p><script>document.addEventListener('DOMContentLoaded',function(){var u=window.PROTOTYPE.user();"
                "document.getElementById('who').textContent=u?('Signed in as '+u.name):'Signed out'})</script>"), encoding="utf-8")
            work = Path(folder) / "ada"
            screens.copy_for(root, work, "ada@example.test")
            browser = screenshot.working_browser()
            profile = tempfile.mkdtemp(prefix="agentforge-test-")
            try:
                done = screenshot._run([browser[0], *screenshot._flags(browser[1], profile, 800, 600), "--dump-dom",
                                        (work / "dashboard.html").resolve().as_uri()], 40)
            finally:
                import shutil
                shutil.rmtree(profile, ignore_errors=True)
        self.assertIn("Signed in as Ada Admin", done.stdout)


if __name__ == "__main__":
    unittest.main()
