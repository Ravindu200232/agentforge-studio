"""Phase 7: the multi-level thinking/tool-use control replacing the plain
agent_think boolean, and the settings route that surfaces it."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import config, httpd  # noqa: E402


class SettingsCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "settings.json"
        patch = mock.patch.object(config, "SETTINGS_FILE", self.file)
        patch.start()
        self.addCleanup(patch.stop)


class ThinkingHelperTests(unittest.TestCase):
    def test_an_unset_level_falls_back_to_the_old_boolean_true(self):
        self.assertEqual(config.thinking({"agent_think": True}), "high")
        self.assertTrue(config.thinking_enabled({"agent_think": True}))

    def test_an_unset_level_falls_back_to_the_old_boolean_false(self):
        self.assertEqual(config.thinking({"agent_think": False}), "off")
        self.assertFalse(config.thinking_enabled({"agent_think": False}))

    def test_a_set_level_wins_over_the_old_boolean(self):
        # Someone toggled agent_think on an old client after setting a level —
        # the level is the one source of truth once it exists.
        self.assertEqual(config.thinking({"thinking_level": "low", "agent_think": True}), "low")

    def test_low_and_both_high_levels_encourage_tool_verification(self):
        self.assertFalse(config.thinking_encourages_tools({"thinking_level": "off"}))
        self.assertTrue(config.thinking_encourages_tools({"thinking_level": "low"}))
        self.assertTrue(config.thinking_encourages_tools({"thinking_level": "high"}))
        self.assertTrue(config.thinking_encourages_tools({"thinking_level": "xhigh"}))

    def test_both_high_levels_actually_reason(self):
        self.assertFalse(config.thinking_enabled({"thinking_level": "off"}))
        self.assertFalse(config.thinking_enabled({"thinking_level": "low"}))
        self.assertTrue(config.thinking_enabled({"thinking_level": "high"}))
        self.assertTrue(config.thinking_enabled({"thinking_level": "xhigh"}))


class SaveSettingsTests(SettingsCase):
    def test_saving_a_level_mirrors_the_old_boolean_for_older_readers(self):
        saved = config.save_settings({"thinking_level": "low"})
        self.assertEqual(saved["thinking_level"], "low")
        self.assertFalse(saved["agent_think"])

        saved = config.save_settings({"thinking_level": "high"})
        self.assertTrue(saved["agent_think"])

        saved = config.save_settings({"thinking_level": "xhigh"})
        self.assertEqual(saved["thinking_level"], "xhigh")
        self.assertTrue(saved["agent_think"])

    def test_an_invalid_level_is_refused(self):
        with self.assertRaises(ValueError):
            config.save_settings({"thinking_level": "ultra"})

    def test_a_settings_file_saved_before_this_existed_still_resolves_correctly(self):
        # Simulates an old settings.json: agent_think only, no thinking_level.
        config._write(config.SETTINGS_FILE, {"agent_think": True})
        self.assertEqual(config.thinking(), "high")
        self.assertTrue(config.thinking_enabled())


class SettingsRouteTests(SettingsCase):
    def test_read_settings_reports_the_resolved_level_not_the_raw_unset_value(self):
        # Nothing saved yet -> DEFAULTS has thinking_level="" (unset), agent_think=False.
        result = httpd.read_settings({})
        self.assertEqual(result["thinking_level"], "off")

    def test_write_then_read_round_trips_the_level(self):
        httpd.write_settings({"thinking_level": "low"})
        result = httpd.read_settings({})
        self.assertEqual(result["thinking_level"], "low")


if __name__ == "__main__":
    unittest.main()
