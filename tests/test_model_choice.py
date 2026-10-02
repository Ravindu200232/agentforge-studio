"""The model picked beside the first input is the one the interview and the specification run on."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import config, routes_srs, store  # noqa: E402

RECORD = {"id": "prj_pick", "name": "Pick", "stack": "", "language": "English", "status": "new"}


class FirstInputModelTests(unittest.TestCase):
    def create(self, saved: dict, **body):
        with mock.patch.object(config, "setting", side_effect=lambda key, default=None: saved.get(key, default)), \
             mock.patch.object(config, "thinking", return_value=saved.get("thinking_level", "high")), \
             mock.patch.object(config, "save_settings") as save, \
             mock.patch.object(store, "create", return_value=RECORD):
            routes_srs.dispatch("POST", "/projects", {"idea": "a shop", **body})
        return save

    def test_the_picked_model_is_saved_before_the_interview(self):
        save = self.create({"model": "old-model"}, model="new-model:cloud", thinking_level="xhigh")
        save.assert_called_once_with({"model": "new-model:cloud", "thinking_level": "xhigh"})

    def test_nothing_is_written_when_nothing_changed(self):
        save = self.create({"model": "same", "thinking_level": "high"}, model="same", thinking_level="high")
        save.assert_not_called()

    def test_an_older_studio_that_sends_no_model_changes_nothing(self):
        save = self.create({"model": "kept"})
        save.assert_not_called()


class SettingsHaveNoModelTabTests(unittest.TestCase):
    def test_models_are_chosen_beside_the_input_and_in_the_chat_only(self):
        settings = (ROOT / "studio/components/SettingsModal.jsx").read_text(encoding="utf-8")
        self.assertNotIn("ModelPicker", settings)
        self.assertNotIn("id: 'models'", settings)
        store_js = (ROOT / "studio/lib/store.js").read_text(encoding="utf-8")
        self.assertIn("api.saveSettings({ agent_model: chosen })", store_js)


if __name__ == "__main__":
    unittest.main()
