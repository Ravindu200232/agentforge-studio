"""Diagrams are drawn as pictures: a renderer that cannot run is not mistaken for a bad diagram, is looked for again,
and the release never ships the file that broke it (a package.json with a byte-order mark)."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent", "tests"):
    sys.path.insert(0, str(ROOT / folder))

import support  # noqa: E402
from server_modules import mermaid  # noqa: E402
from srs_agent import document  # noqa: E402

BOM_FAILURE = "SyntaxError: Unexpected token '﻿', \"﻿{\" is not valid JSON"
PARSE_FAILURE = "Error: Parse error on line 2: | ...a --> | Expecting 'SEMI', 'NEWLINE', got 'EOF'"


def setUpModule():
    support.isolate_workspaces()


class SyntaxOrRendererTests(unittest.TestCase):
    def test_only_mermaid_rejecting_the_source_counts_as_the_diagrams_fault(self):
        self.assertTrue(mermaid.is_syntax_error(PARSE_FAILURE))
        self.assertTrue(mermaid.is_syntax_error("Syntax error in text mermaid version 11"))
        self.assertTrue(mermaid.is_syntax_error("UnknownDiagramError: No diagram type detected"))
        self.assertFalse(mermaid.is_syntax_error(BOM_FAILURE))
        self.assertFalse(mermaid.is_syntax_error("Error: Failed to launch the browser process!"))
        self.assertFalse(mermaid.is_syntax_error("no mermaid renderer is installed"))
        self.assertFalse(mermaid.is_syntax_error("the renderer timed out after 180s"))


class FindAgainTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(setattr, mermaid, "_cli", False)

    def test_a_renderer_not_found_is_looked_for_again_later(self):
        mermaid._cli = False  # noqa: SLF001
        with mock.patch.object(mermaid, "_node_binaries", return_value=[]), \
             mock.patch.object(mermaid.shutil, "which", return_value=None):
            self.assertIsNone(mermaid._find_cli())  # noqa: SLF001
        probe = mock.Mock(returncode=0)
        with mock.patch.object(mermaid.shutil, "which", side_effect=lambda name: "mmdc" if name == "mmdc" else None), \
             mock.patch.object(mermaid.subprocess, "run", return_value=probe):
            self.assertIsNone(mermaid._find_cli())  # noqa: SLF001 - within RECHECK_SECONDS: the answer stands
            with mock.patch.object(mermaid, "RECHECK_SECONDS", 0):
                self.assertEqual(mermaid._find_cli(), ["mmdc"])  # noqa: SLF001


class BrowserTests(unittest.TestCase):
    def test_playwrights_chromium_is_used_when_there_is_no_chrome_or_edge(self):
        with tempfile.TemporaryDirectory() as folder:
            chrome = Path(folder) / "chromium-1243" / "chrome-win64" / "chrome.exe"
            chrome.parent.mkdir(parents=True)
            chrome.write_bytes(b"")
            empty = str(Path(folder) / "none")
            with mock.patch.dict("os.environ", {"PLAYWRIGHT_BROWSERS_PATH": folder, "PROGRAMFILES": empty,
                                                "PROGRAMFILES(X86)": empty, "LOCALAPPDATA": empty,
                                                "PUPPETEER_EXECUTABLE_PATH": ""}):
                self.assertEqual(mermaid._installed_browser(), str(chrome))  # noqa: SLF001


class DrawTests(unittest.TestCase):
    def test_a_renderer_that_cannot_run_never_sends_a_good_diagram_back_to_be_rewritten(self):
        good = "flowchart TD\n  a[Start] --> b[Done]\n"
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            session = mock.Mock(workspace=workspace)
            session.record_path.side_effect = lambda *parts: (workspace / ".agentforge" / Path(*parts))
            (workspace / ".agentforge" / "srs" / "diagrams").mkdir(parents=True)
            with mock.patch.object(document.llm, "complete", return_value=good) as asked, \
                 mock.patch.object(document, "_diagram_reference", return_value=""), \
                 mock.patch.object(document.mermaid, "available", return_value=True), \
                 mock.patch.object(document.mermaid, "render_diagram", return_value=(False, BOM_FAILURE)):
                entry = document._draw_diagram(session, "prj_draw", {}, "activity")  # noqa: SLF001
        self.assertEqual(asked.call_count, 1)                   # drawn once, not "corrected" twice more
        self.assertEqual(entry["source"].strip(), good.strip())
        self.assertNotIn("svg", entry)                           # drawn from the source later, once it can be


class ReleaseFilesTests(unittest.TestCase):
    def test_the_build_never_writes_a_byte_order_mark_into_files_node_or_the_installer_read(self):
        script = (ROOT / "release" / "build.ps1").read_text(encoding="utf-8")
        code = [line for line in script.splitlines() if not line.lstrip().startswith("#")]
        self.assertFalse([line for line in code if "-Encoding UTF8" in line])
        self.assertIn("UTF8Encoding $false", script)


if __name__ == "__main__":
    unittest.main()
