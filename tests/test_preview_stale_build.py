"""A production preview server keeps the build it started with: a newer build under it has to replace it."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent", ".deps", "tests"):
    value = str(ROOT / folder) if folder else str(ROOT)
    if value not in sys.path:
        sys.path.insert(0, value)

from server_modules import preview_runtime  # noqa: E402
from support import isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


class StaleBuildTests(unittest.TestCase):
    def setUp(self):
        preview_runtime._processes.clear()  # noqa: SLF001 - reset module state
        preview_runtime._last.clear()  # noqa: SLF001 - reset module state

    def _built(self, root: Path, written_ms: int) -> None:
        marker = root / ".next" / "BUILD_ID"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("abc", encoding="utf-8")
        os.utime(marker, (written_ms / 1000, written_ms / 1000))

    def _running(self, script: str, started_ms: int) -> dict:
        return {"project": "demo", "status": "running", "port": 3100, "revision": started_ms, "script": script}

    def test_a_build_written_after_the_server_started_is_newer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._built(root, 2_000_000)
            self.assertTrue(preview_runtime.build_is_newer(root, 1_000_000))
            self.assertFalse(preview_runtime.build_is_newer(root, 2_000_000))
            self.assertFalse(preview_runtime.build_is_newer(root, 3_000_000))

    def test_no_build_and_no_start_time_is_never_newer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertFalse(preview_runtime.build_is_newer(root, 1_000_000))
            self._built(root, 2_000_000)
            self.assertFalse(preview_runtime.build_is_newer(root, 0))

    def test_the_server_is_replaced_when_a_newer_build_was_written_under_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._built(root, 2_000_000)
            with patch.object(preview_runtime.config, "workspace_for", return_value=root), \
                 patch.object(preview_runtime, "status", return_value=self._running("start", 1_000_000)), \
                 patch.object(preview_runtime, "_read_metadata", return_value={"script": "start"}), \
                 patch.object(preview_runtime, "reopen") as reopen:
                self.assertTrue(preview_runtime.refresh_if_stale("demo"))
        reopen.assert_called_once_with("demo")

    def test_a_server_started_after_the_build_is_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._built(root, 2_000_000)
            with patch.object(preview_runtime.config, "workspace_for", return_value=root), \
                 patch.object(preview_runtime, "status", return_value=self._running("start", 3_000_000)), \
                 patch.object(preview_runtime, "_read_metadata", return_value={"script": "start"}), \
                 patch.object(preview_runtime, "reopen") as reopen:
                self.assertFalse(preview_runtime.refresh_if_stale("demo"))
        reopen.assert_not_called()

    def test_a_dev_server_and_a_stopped_preview_are_left_alone(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._built(root, 2_000_000)
            for row, saved in ((self._running("dev", 1_000_000), {"script": "dev"}),
                               ({**self._running("start", 1_000_000), "status": "stopped"}, {"script": "start"})):
                with self.subTest(status=row["status"], script=saved["script"]), \
                     patch.object(preview_runtime.config, "workspace_for", return_value=root), \
                     patch.object(preview_runtime, "status", return_value=row), \
                     patch.object(preview_runtime, "_read_metadata", return_value=saved), \
                     patch.object(preview_runtime, "reopen") as reopen:
                    self.assertFalse(preview_runtime.refresh_if_stale("demo"))
                    reopen.assert_not_called()

    def test_opening_the_preview_replaces_a_server_that_a_newer_build_has_left_behind(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(
                json.dumps({"scripts": {"dev": "next dev", "start": "next start"}, "dependencies": {"next": "15"}}),
                encoding="utf-8")
            self._built(root, 2_000_000)
            stops = []

            def stop(project):
                stops.append(project)
                preview_runtime._processes.pop(project, None)
                return {}

            with patch.object(preview_runtime.config, "workspace_for", return_value=root), \
                 patch.object(preview_runtime.config, "record_dir", return_value=root / ".agentforge"), \
                 patch.object(preview_runtime, "status", return_value=self._running("start", 1_000_000)), \
                 patch.object(preview_runtime, "_read_metadata",
                              return_value={"script": "start", "framework": "next"}), \
                 patch.object(preview_runtime, "_port_open", return_value=True), \
                 patch.object(preview_runtime, "stop", side_effect=stop), \
                 patch.object(preview_runtime, "_preview_port", return_value=3200), \
                 patch.object(preview_runtime, "_launch", return_value=Mock(pid=5, poll=Mock(return_value=None))), \
                 patch.object(preview_runtime, "_write_metadata"), \
                 patch.object(preview_runtime.supabase_connect, "env_for", return_value={}), \
                 patch.object(preview_runtime.deploy_vars, "environment", return_value={}), \
                 patch.object(preview_runtime.bus, "runtime_state"), \
                 patch.object(preview_runtime.threading, "Thread"):
                preview_runtime.open_preview("demo")
        self.assertEqual(stops, ["demo"])


if __name__ == "__main__":
    unittest.main()
