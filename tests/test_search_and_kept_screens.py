"""A text search of a built app reads its source, not its packages, build output or test pictures.

One `search_text("/api/health", ".")` of a built app went through 58,000 test frames the Studio had kept and the packages of
three apps, and took sixteen minutes; the deployment plan it was part of took thirty-seven. The frames were Playwright's trace
recordings (`.playwright-artifacts-N`), which the screen keeper copied along with the screenshots.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "qa-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from ollama_terminal import tools  # noqa: E402
from ollama_terminal.tools import WorkspaceTools  # noqa: E402
from qa_agent import screen_keeper  # noqa: E402


def write(root: Path, name: str, text: str = "fetch('/api/health')") -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = WorkspaceTools(self.root, None, lambda question: True)

    def test_the_source_is_searched_and_packages_build_output_and_test_pictures_are_not(self):
        write(self.root, "app/api/health/route.js")
        write(self.root, ".agentforge/build/report.json", '{"health": "/api/health"}')
        for skipped in ("node_modules/next/index.js", ".next/server/app.js", "test-results/results.json",
                        ".agentforge/qa/screens/run/a.txt", ".agentforge/prototype/app/node_modules/x/y.js",
                        "test-results/artifacts/.playwright-artifacts-0/frame.txt", "public/logo.png"):
            write(self.root, skipped)
        found = self.tools.tool_search_text("/API/health", ".")
        self.assertEqual(sorted(line.split(":")[0].replace("\\", "/") for line in found.splitlines()),
                         [".agentforge/build/report.json", "app/api/health/route.js"])

    def test_a_folder_asked_for_by_name_is_searched_even_inside_a_skipped_one(self):
        write(self.root, "node_modules/next/index.js")
        self.assertIn("index.js", self.tools.tool_search_text("api/health", "node_modules/next"))

    def test_a_search_that_runs_too_long_stops_and_says_so(self):
        for number in range(3):
            write(self.root, f"src/file{number}.js")
        with mock.patch.object(tools, "SEARCH_SECONDS", -1):
            self.assertIn("stopped after", self.tools.tool_search_text("api/health", "."))

    def test_nothing_found_says_so(self):
        write(self.root, "src/a.js", "nothing here")
        self.assertEqual(self.tools.tool_search_text("api/health", "."), "No matches")


class KeptScreensTests(unittest.TestCase):
    def test_the_screenshots_are_kept_and_trace_frames_are_not_and_old_kept_frames_go(self):
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            source = workspace / screen_keeper.ARTIFACTS
            (source / "journey-UJ-001-desktop").mkdir(parents=True)
            (source / "journey-UJ-001-desktop" / "test-finished-1.png").write_bytes(b"png")
            (source / ".playwright-artifacts-0").mkdir()
            (source / ".playwright-artifacts-0" / "page@1.jpeg").write_bytes(b"frame")
            old = workspace / screen_keeper.KEPT / ".playwright-artifacts-3"
            old.mkdir(parents=True)
            (old / "page@9.jpeg").write_bytes(b"frame")
            self.assertEqual(screen_keeper.sweep(workspace, settled=False), 1)
            kept = workspace / screen_keeper.KEPT
            self.assertTrue((kept / "journey-UJ-001-desktop" / "test-finished-1.png").is_file())
            self.assertFalse((kept / ".playwright-artifacts-0").exists())
            with screen_keeper.Keeper(workspace, every=0.05):
                pass
            self.assertFalse(old.exists())


if __name__ == "__main__":
    unittest.main()
