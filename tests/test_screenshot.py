"""Silent screenshots: which browser is used, how a page is photographed, and that a hung browser is never left running."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import screenshot  # noqa: E402


class FindBrowserTests(unittest.TestCase):
    def build(self, folder: Path, *relative: str) -> dict[str, str]:
        made = {}
        for item in relative:
            path = folder / item
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"x")
            made[item] = str(path)
        return made

    def find(self, cache: Path, **env: str) -> list[tuple[str, str]]:
        clean = {k: v for k, v in os.environ.items() if k not in {"AGENTFORGE_BROWSER", "PLAYWRIGHT_BROWSERS_PATH", "LOCALAPPDATA"}}
        with mock.patch.dict(os.environ, {**clean, "PLAYWRIGHT_BROWSERS_PATH": str(cache), **env}, clear=True), \
                mock.patch.object(screenshot.shutil, "which", return_value=None), \
                mock.patch.object(screenshot.Path, "home", return_value=cache / "home"):
            return screenshot.find_browsers()

    def test_playwrights_headless_shell_comes_first_and_the_full_chromium_last(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            made = self.build(cache, "chromium-1243/chrome-win64/chrome.exe",
                              "chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe")
            programs = cache / "pf"
            edge = self.build(programs, "Microsoft/Edge/Application/msedge.exe")
            found = self.find(cache, ProgramFiles=str(programs), **{"ProgramFiles(x86)": str(cache / "none")})
        kinds = [(Path(path).name, how) for path, how in found]
        self.assertEqual(kinds, [("chrome-headless-shell.exe", "shell"), ("msedge.exe", "chrome"), ("chrome.exe", "chrome")])
        self.assertEqual(found[0][0], made["chromium_headless_shell-1243/chrome-headless-shell-win64/chrome-headless-shell.exe"])
        self.assertEqual(found[1][0], edge["Microsoft/Edge/Application/msedge.exe"])

    def test_a_browser_the_person_names_is_tried_before_any_other(self):
        with tempfile.TemporaryDirectory() as folder:
            mine = self.build(Path(folder), "mine/browser.exe")["mine/browser.exe"]
            found = self.find(Path(folder), AGENTFORGE_BROWSER=mine)
        self.assertEqual(found[0], (mine, "chrome"))

    def test_nothing_installed_is_an_empty_list_not_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.find(Path(folder), ProgramFiles=str(Path(folder) / "a"),
                                       **{"ProgramFiles(x86)": str(Path(folder) / "b")}), [])

    def test_the_same_browser_is_listed_once(self):
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            self.build(cache, "chromium_headless_shell-1/chrome-headless-shell-win64/chrome-headless-shell.exe")
            found = self.find(cache, PLAYWRIGHT_BROWSERS_PATH=str(cache), LOCALAPPDATA=str(cache))
        self.assertEqual(len([p for p, _ in found if p.endswith("chrome-headless-shell.exe")]), 1)


class WorkingBrowserTests(unittest.TestCase):
    def setUp(self):
        screenshot._working.clear()
        self.addCleanup(screenshot._working.clear)

    def test_the_first_browser_that_really_takes_a_picture_is_the_one_used_and_the_rest_are_not_tried(self):
        tried = []

        def shoot(page, out, viewport, browser, seconds):
            tried.append(browser[0])
            if browser[0] == "hangs":
                raise ValueError("took too long")

        with mock.patch.object(screenshot, "find_browsers", return_value=[("hangs", "chrome"), ("works", "shell"), ("never", "chrome")]), \
                mock.patch.object(screenshot, "shoot", side_effect=shoot):
            self.assertEqual(screenshot.working_browser(), ("works", "shell"))
            self.assertEqual(screenshot.working_browser(), ("works", "shell"))      # remembered: not probed again
        self.assertEqual(tried, ["hangs", "works"])

    def test_no_browser_that_works_is_none(self):
        with mock.patch.object(screenshot, "find_browsers", return_value=[("a", "chrome")]), \
                mock.patch.object(screenshot, "shoot", side_effect=ValueError("no")):
            self.assertIsNone(screenshot.working_browser())


class LocalUrlTests(unittest.TestCase):
    def test_only_a_page_on_this_computer_may_be_photographed(self):
        for ok in ("http://localhost:3000/rooms", "http://127.0.0.1:5173/"):
            self.assertEqual(screenshot.local_url(ok), ok)
        for bad in ("https://example.com", "http://example.com", "http://user:pw@localhost:3000", "file:///C:/secret", "", "ftp://localhost"):
            with self.subTest(url=bad), self.assertRaises(ValueError):
                screenshot.local_url(bad)


class ShootTests(unittest.TestCase):
    """The command line the browser is given, with the browser itself replaced."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.page = self.folder / "index.html"
        self.page.write_text("<h1>x</h1>", encoding="utf-8")
        self.calls: list[list[str]] = []
        self.height = 1800

    def fake_run(self, command, seconds=screenshot.SECONDS):
        self.calls.append(command)
        if "--dump-dom" in command:
            return SimpleNamespace(stdout=f"<html><title>{screenshot.HEIGHT_MARK}{self.height}</title></html>", stderr="", returncode=0)
        target = next(a for a in command if a.startswith("--screenshot=")).split("=", 1)[1]
        Path(target).write_bytes(b"x" * 600)
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    def shoot(self, source, viewport="desktop", how="chrome"):
        with mock.patch.object(screenshot, "_run", self.fake_run):
            return screenshot.shoot(source, self.folder / "out" / "shot.png", viewport, ("browser.exe", how))

    def window(self, command):
        return next(a for a in command if a.startswith("--window-size=")).split("=", 1)[1]

    def test_a_page_is_photographed_whole_in_a_window_as_tall_as_it_measured(self):
        out = self.shoot(self.page)
        self.assertTrue(out.is_file())
        measure, picture = self.calls
        self.assertEqual(self.window(measure), "1440,900")
        self.assertEqual(self.window(picture), "1440,1800")
        self.assertIn(self.page.resolve().as_uri(), picture)

    def test_a_very_tall_page_is_cut_off_and_a_very_short_one_is_not_padded_far(self):
        self.height = 90000
        self.shoot(self.page, "desktop")
        self.assertEqual(self.window(self.calls[-1]), f"1440,{screenshot.MAX_HEIGHT['desktop']}")
        self.calls.clear()
        self.height = 120
        self.shoot(self.page, "mobile")
        self.assertEqual(self.window(self.calls[-1]), f"390,{screenshot.MIN_HEIGHT}")

    def test_a_page_that_never_wrote_its_height_gets_the_viewport(self):
        self.height = 0
        with mock.patch.object(screenshot, "_run", side_effect=lambda command, seconds=0: (
                self.calls.append(command) or SimpleNamespace(stdout="<html></html>", stderr="", returncode=0)
                if "--dump-dom" in command else self.fake_run(command))):
            screenshot.shoot(self.page, self.folder / "o.png", "mobile", ("b", "chrome"))
        self.assertEqual(self.window(self.calls[-1]), "390,844")

    def test_a_running_preview_is_photographed_at_the_viewport_without_being_measured(self):
        self.shoot("http://localhost:3000/rooms")
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.window(self.calls[0]), "1440,900")
        self.assertIn("http://localhost:3000/rooms", self.calls[0])

    def test_a_remote_address_is_refused_before_any_browser_starts(self):
        with mock.patch.object(screenshot, "_run") as run, self.assertRaises(ValueError):
            screenshot.shoot("http://example.com", self.folder / "o.png", "desktop", ("b", "chrome"))
        run.assert_not_called()

    def test_the_headless_only_build_is_not_given_the_new_headless_flag(self):
        self.shoot(self.page, how="shell")
        self.assertIn("--headless", self.calls[0])
        self.assertNotIn("--headless=new", self.calls[0])
        self.calls.clear()
        self.shoot(self.page, how="chrome")
        self.assertIn("--headless=new", self.calls[0])

    def test_every_picture_uses_its_own_empty_profile_that_is_removed_afterwards(self):
        self.shoot(self.page)
        profiles = {a for call in self.calls for a in call if a.startswith("--user-data-dir=")}
        self.assertEqual(len(profiles), 1)
        self.assertFalse(Path(profiles.pop().split("=", 1)[1]).exists())

    def test_no_picture_saved_is_an_error_naming_the_page(self):
        with mock.patch.object(screenshot, "_run", return_value=SimpleNamespace(stdout="", stderr="", returncode=0)), \
                self.assertRaisesRegex(ValueError, "saved no picture of index.html"):
            screenshot.shoot(self.page, self.folder / "o.png", "desktop", ("b", "chrome"))

    def test_a_browser_that_takes_too_long_is_reported_with_the_page_and_the_time(self):
        with mock.patch.object(screenshot, "_run", side_effect=subprocess.TimeoutExpired("b", 5)), \
                self.assertRaisesRegex(ValueError, "longer than 7 seconds to draw index.html"):
            screenshot.shoot(self.page, self.folder / "o.png", "desktop", ("b", "chrome"), seconds=7)

    def test_an_unknown_viewport_or_no_browser_is_refused(self):
        with self.assertRaisesRegex(ValueError, "desktop or mobile"):
            screenshot.shoot(self.page, self.folder / "o.png", "tablet", ("b", "chrome"))
        with mock.patch.object(screenshot, "working_browser", return_value=None), self.assertRaisesRegex(ValueError, "no browser"):
            screenshot.shoot(self.page, self.folder / "o.png", "desktop")


class RunTests(unittest.TestCase):
    def test_a_command_that_hangs_is_stopped_with_what_it_started_and_nothing_else(self):
        process = mock.Mock(pid=4242)
        process.communicate.side_effect = [subprocess.TimeoutExpired("b", 1), ("", "")]
        with mock.patch.object(screenshot.subprocess, "Popen", return_value=process), \
                mock.patch.object(screenshot.subprocess, "run") as run, \
                self.assertRaises(subprocess.TimeoutExpired):
            screenshot._run(["browser"], seconds=1)
        if os.name == "nt":
            self.assertEqual(run.call_args.args[0], ["taskkill", "/PID", "4242", "/T", "/F"])    # this tree, never by image name
        self.assertNotIn("/IM", str(run.call_args_list))

    def test_a_finished_command_returns_its_output(self):
        done = screenshot._run([sys.executable, "-c", "print('hello')"], seconds=20)
        self.assertEqual((done.returncode, done.stdout.strip()), (0, "hello"))


@unittest.skipUnless(screenshot.working_browser(), "no browser that takes screenshots here")
class RealBrowserTests(unittest.TestCase):
    def test_a_real_page_comes_out_as_a_picture_as_tall_as_the_page(self):
        with tempfile.TemporaryDirectory() as folder:
            page = Path(folder) / "tall.html"
            page.write_text("<!doctype html><title>t</title><div style='height:1500px;background:#ccd'>tall</div>" + screenshot.MEASURE,
                            encoding="utf-8")
            out = screenshot.shoot(page, Path(folder) / "tall.png", "desktop")
            data = out.read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        self.assertEqual(width, 1440)
        self.assertGreaterEqual(height, 1500)


if __name__ == "__main__":
    unittest.main()
