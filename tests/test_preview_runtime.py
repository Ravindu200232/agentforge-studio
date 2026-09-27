"""Ownership rules for the Studio's fixed local preview port."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_preview_address_is_stable(self):
        self.assertEqual(preview_runtime.PREVIEW_PORT, 3001)

    def test_occupied_preview_port_terminates_its_listener(self):
        with patch.object(preview_runtime, "_port_open", return_value=True), \
             patch.object(preview_runtime, "_listening_pids", return_value=[7777]), \
             patch.object(preview_runtime, "_terminate_tree") as terminate:
            with self.assertRaisesRegex(RuntimeError, "still in use"):
                preview_runtime._free_port(5173, timeout=0)
            terminate.assert_called_once_with(7777)

    def test_mern_stop_signal_targets_only_its_saved_runtime_id(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            saved = {"controlMode": "file", "runtimeId": "only-this-run", "port": 5173}
            with patch.object(preview_runtime.config, "record_dir", return_value=record), \
                 patch.object(preview_runtime, "_port_open", return_value=False):
                self.assertTrue(preview_runtime._signal_managed_stop("demo", saved))
            message = json.loads((record / "preview-stop.json").read_text(encoding="utf-8"))
            self.assertEqual(message, {"runtimeId": "only-this-run"})

    def test_status_rejects_stale_metadata_without_listener_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            (record / "preview-runtime.json").write_text(json.dumps({"port": 3001}), encoding="utf-8")
            with patch.object(preview_runtime, "_metadata", return_value=record / "preview-runtime.json"), \
                 patch.object(preview_runtime, "_port_open", return_value=True), \
                 patch.object(preview_runtime, "_listening_pids", return_value=[8888]):
                self.assertEqual(preview_runtime.status("demo")["status"], "stopped")

    def test_status_accepts_only_the_recorded_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            (record / "preview-runtime.json").write_text(
                json.dumps({"port": 3001, "listenerPid": 8888, "url": "http://127.0.0.1:3001/"}),
                encoding="utf-8",
            )
            with patch.object(preview_runtime, "_metadata", return_value=record / "preview-runtime.json"), \
                 patch.object(preview_runtime, "_listening_pids", return_value=[8888]):
                self.assertEqual(preview_runtime.status("demo")["status"], "running")


if __name__ == "__main__":
    unittest.main()
