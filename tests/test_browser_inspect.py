"""The LLM's local live-browser tool is deliberately loopback-only."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ollama_terminal import browser_inspect  # noqa: E402


class BrowserInspectTests(unittest.TestCase):
    def test_rejects_remote_and_credentialed_urls_before_starting_a_browser(self):
        for url in ("https://example.com", "http://alice:secret@127.0.0.1:3001", "file:///C:/secret"):
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, "preview URL only"):
                browser_inspect.inspect_local_page(Path.cwd(), url)

    def test_runs_playwright_in_the_workspace_and_returns_saved_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def completed(args, **_kwargs):
                incoming = json.loads(args[3])
                saved = Path(incoming["screenshot"])
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(b"png")
                payload = {"url": "http://127.0.0.1:3001/rooms", "title": "Rooms", "status": 200,
                           "screenshot": incoming["relativeScreenshot"], "viewport": {"width": 1440, "height": 1000},
                           "layout": {"horizontalOverflow": False}}
                return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
            with mock.patch("ollama_terminal.browser_inspect.subprocess.run", side_effect=completed) as run:
                result = browser_inspect.inspect_local_page(root, "http://127.0.0.1:3001/rooms")
        self.assertEqual(result["title"], "Rooms")
        self.assertEqual(run.call_args.kwargs["cwd"], root)
        self.assertEqual(run.call_args.args[0][:2], ["node", "-e"])
        self.assertIn("overflowElements", run.call_args.args[0][2])

    def test_invalid_viewport_is_refused_before_starting_a_browser(self):
        with self.assertRaisesRegex(ValueError, "desktop or mobile"):
            browser_inspect.inspect_local_page(Path.cwd(), "http://localhost:3001", "tablet")


if __name__ == "__main__":
    unittest.main()
