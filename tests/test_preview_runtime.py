"""Ownership rules for isolated, project-local Studio preview ports."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent", ".deps"):
    value = str(ROOT / folder) if folder else str(ROOT)
    if value not in sys.path:
        sys.path.insert(0, value)

from server_modules import preview_runtime  # noqa: E402


class PreviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        preview_runtime._processes.clear()  # noqa: SLF001 - reset module state
        preview_runtime._last.clear()  # noqa: SLF001 - reset module state

    def test_project_port_order_is_stable_and_in_the_private_preview_range(self):
        first = preview_runtime._port_candidates("demo")
        self.assertEqual(first, preview_runtime._port_candidates("demo"))
        self.assertEqual(len(first), preview_runtime.PREVIEW_PORT_LAST - preview_runtime.PREVIEW_PORT_FIRST + 1)
        self.assertEqual(len(set(first)), len(first))
        self.assertTrue(all(preview_runtime.PREVIEW_PORT_FIRST <= port <= preview_runtime.PREVIEW_PORT_LAST
                            for port in first))

    def test_busy_port_is_skipped_without_touching_the_unrelated_listener(self):
        candidates = preview_runtime._port_candidates("demo")
        with patch.object(preview_runtime, "_port_open", side_effect=lambda port: port == candidates[0]), \
             patch.object(preview_runtime, "_terminate_tree") as terminate:
            selected = preview_runtime._preview_port("demo", {})
        self.assertEqual(selected, candidates[1])
        terminate.assert_not_called()

    def test_status_rejects_stale_metadata_without_listener_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            (record / "preview-runtime.json").write_text(
                json.dumps({"port": preview_runtime.PREVIEW_PORT_FIRST}), encoding="utf-8")
            with patch.object(preview_runtime, "_metadata", return_value=record / "preview-runtime.json"), \
                 patch.object(preview_runtime, "_port_open", return_value=True), \
                 patch.object(preview_runtime, "_listening_pids", return_value=[8888]):
                self.assertEqual(preview_runtime.status("demo")["status"], "stopped")

    def test_status_accepts_only_the_recorded_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            (record / "preview-runtime.json").write_text(
                json.dumps({"port": preview_runtime.PREVIEW_PORT_FIRST, "listenerPid": 8888,
                            "url": f"http://127.0.0.1:{preview_runtime.PREVIEW_PORT_FIRST}/"}),
                encoding="utf-8",
            )
            with patch.object(preview_runtime, "_metadata", return_value=record / "preview-runtime.json"), \
                 patch.object(preview_runtime, "_listening_pids", return_value=[8888]):
                self.assertEqual(preview_runtime.status("demo")["status"], "running")

    def test_cache_corrupted_detects_the_stale_chunk_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "preview.log"
            log_path.write_bytes(b"info: compiling\nError: Cannot find module './611.js'\nRequire stack:\n")
            self.assertTrue(preview_runtime._cache_corrupted(log_path))

    def test_cache_corrupted_ignores_a_real_missing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "preview.log"
            log_path.write_bytes(b"Error: Cannot find module 'left-pad'\n")
            self.assertFalse(preview_runtime._cache_corrupted(log_path))

    def test_heal_clears_the_next_cache_and_relaunches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".next").mkdir()
            (root / ".next" / "marker.txt").write_text("stale", encoding="utf-8")
            log_path = root / "preview.log"
            log_path.touch()
            old_process = Mock(pid=111)
            new_process = Mock(pid=222)
            preview_runtime._processes["demo"] = {"process": old_process, "port": 3001}
            with patch.object(preview_runtime, "_terminate_tree") as terminate, \
                 patch.object(preview_runtime, "_launch", return_value=new_process) as launch, \
                 patch.object(preview_runtime, "_write_metadata"), \
                 patch.object(preview_runtime, "_wait_ready") as wait_ready:
                preview_runtime._heal("demo", old_process, "http://127.0.0.1:3001/", root,
                                      ["npm", "run", "dev"], {}, log_path, "dev")
            terminate.assert_called_once_with(111)
            launch.assert_called_once()
            self.assertFalse((root / ".next").exists())
            self.assertIs(preview_runtime._processes["demo"]["process"], new_process)
            wait_ready.assert_called_once()
            self.assertEqual(wait_ready.call_args.args[1], new_process)
            self.assertTrue(wait_ready.call_args.args[-1] or wait_ready.call_args.kwargs.get("healed"))

    def test_heal_does_nothing_once_a_newer_preview_has_replaced_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "preview.log"
            log_path.touch()
            old_process = Mock(pid=111)
            preview_runtime._processes["demo"] = {"process": Mock(pid=999), "port": 3001}
            with patch.object(preview_runtime, "_terminate_tree") as terminate, \
                 patch.object(preview_runtime, "_launch") as launch:
                preview_runtime._heal("demo", old_process, "http://127.0.0.1:3001/", root,
                                      ["npm", "run", "dev"], {}, log_path, "dev")
            terminate.assert_not_called()
            launch.assert_not_called()

    def test_wait_ready_heals_a_dev_server_that_died_with_a_corrupted_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "preview.log"
            log_path.write_bytes(b"Error: Cannot find module './611.js'\n")
            process = Mock()
            process.poll.return_value = 1
            with patch.object(preview_runtime, "_heal") as heal:
                preview_runtime._wait_ready("demo", process, "http://127.0.0.1:3001/", root,
                                            ["npm", "run", "dev"], {}, log_path, "dev")
            heal.assert_called_once()

    def test_wait_ready_never_heals_a_production_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "preview.log"
            log_path.write_bytes(b"Error: Cannot find module './611.js'\n")
            process = Mock()
            process.poll.return_value = 1
            with patch.object(preview_runtime, "_heal") as heal, \
                 patch.object(preview_runtime, "status", return_value={}):
                preview_runtime._wait_ready("demo", process, "http://127.0.0.1:3001/", root,
                                            ["npm", "run", "start"], {}, log_path, "start")
            heal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
