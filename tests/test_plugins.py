"""Project plugin handoffs: multiple providers, no credential leakage."""
from __future__ import annotations

import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server_modules import config, plugins  # noqa: E402


CATALOGUE = {
    "plugins": [
        {"id": "stripe", "name": "Stripe", "group": "Payments", "what": "Payments",
         "modes": [{"choice": "stripe-test", "label": "Test mode", "hint": "No real money",
                    "fields": [{"key": "STRIPE_SECRET_KEY", "label": "Secret", "secret": True},
                               {"key": "STRIPE_PUBLISHABLE_KEY", "label": "Public", "secret": False}]}]},
        {"id": "resend", "name": "Resend", "group": "Email", "what": "Email",
         "modes": [{"choice": "resend-sandbox", "label": "Sandbox", "hint": "Test sender",
                    "fields": [{"key": "RESEND_API_KEY", "label": "API key", "secret": True}]}]},
    ]
}

VAULT = {
    "stripe": {"mode": "stripe-test", "values": {
        "STRIPE_SECRET_KEY": "sk_test_NEVER_WRITE_THIS",
        "STRIPE_PUBLISHABLE_KEY": "pk_test_NEVER_WRITE_THIS",
    }},
    "resend": {"mode": "resend-sandbox", "values": {
        "RESEND_API_KEY": "re_NEVER_WRITE_THIS",
    }},
}


class PluginHandoffTests(unittest.TestCase):
    def test_builder_and_chat_prompts_read_the_multi_plugin_handoff(self):
        root = Path(__file__).resolve().parents[1]
        # The prompts that write or change the application read the handoff; planning a change does not.
        prompt_paths = (
            "prompts/builder/generate.md",
            "prompts/builder/update.md",
            "prompts/changes/execute.md",
        )
        for relative in prompt_paths:
            text = (root / relative).read_text(encoding="utf-8")
            self.assertIn(".agentforge/PLUGIN.md", text, relative)

    def test_multiple_plugins_share_one_secret_free_handoff(self):
        with mock.patch.object(plugins, "_catalogue", return_value=CATALOGUE), \
             mock.patch.object(plugins, "_read", return_value=VAULT):
            page = plugins.handoff(["stripe", "resend", "stripe"])

        self.assertEqual(page.count("## Stripe"), 1)
        self.assertEqual(page.count("## Resend"), 1)
        for name in ("STRIPE_SECRET_KEY", "STRIPE_PUBLISHABLE_KEY", "RESEND_API_KEY"):
            self.assertIn(name, page)
        for secret in ("sk_test_NEVER_WRITE_THIS", "pk_test_NEVER_WRITE_THIS", "re_NEVER_WRITE_THIS"):
            self.assertNotIn(secret, page)
        self.assertIn("server-only secret", page)
        self.assertIn("remove `.agentforge/PLUGIN.md`", page)

    def test_project_selection_writes_and_success_consumes_the_handoff(self):
        original = config.WORKSPACES
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(plugins, "_catalogue", return_value=CATALOGUE), \
             mock.patch.object(plugins, "_read", return_value=VAULT):
            config.WORKSPACES = Path(folder)
            try:
                enabled = plugins.configure_project("prj_plugins", ["stripe", "unknown", "resend"])
                record = config.record_dir("prj_plugins")
                self.assertEqual(enabled, ["stripe", "resend"])
                self.assertEqual(json.loads((record / plugins.PROJECT_FILE).read_text("utf-8")), enabled)
                self.assertTrue((record / plugins.HANDOFF_FILE).is_file())
                plugins.consume_handoff("prj_plugins")
                self.assertFalse((record / plugins.HANDOFF_FILE).exists())
                self.assertTrue((record / plugins.PROJECT_FILE).is_file())
            finally:
                config.WORKSPACES = original

    def test_disabling_every_plugin_removes_only_the_temporary_handoff(self):
        original = config.WORKSPACES
        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(plugins, "_catalogue", return_value=CATALOGUE), \
             mock.patch.object(plugins, "_read", return_value=VAULT):
            config.WORKSPACES = Path(folder)
            try:
                plugins.configure_project("prj_plugins", ["stripe"])
                plugins.configure_project("prj_plugins", [])
                record = config.record_dir("prj_plugins")
                self.assertEqual(json.loads((record / plugins.PROJECT_FILE).read_text("utf-8")), [])
                self.assertFalse((record / plugins.HANDOFF_FILE).exists())
            finally:
                config.WORKSPACES = original


if __name__ == "__main__":
    unittest.main()
