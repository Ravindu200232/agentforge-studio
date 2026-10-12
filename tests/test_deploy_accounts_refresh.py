"""An account connected in Settings shows as connected in the Deploy panel at once, without a refresh or a change of tab."""
from __future__ import annotations

import re
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import cli_signin, config, httpd  # noqa: E402

PAGE = (ROOT / "studio" / "app" / "page.jsx").read_text(encoding="utf-8")
PANEL = (ROOT / "studio" / "components" / "deploy" / "DeployPanel.jsx").read_text(encoding="utf-8")


class ThePageTellsThePanelTests(unittest.TestCase):
    """The panel re-reads who is signed in when the page says an account changed; before, nobody ever told it."""

    def test_the_deploy_panel_is_given_a_revision_that_changes_with_every_account_change_and_when_settings_closes(self):
        element = re.search(r"<DeployPanel.*?accountsRevision=\{[^}]*\} />", PAGE, re.DOTALL)
        self.assertIsNotNone(element)
        self.assertIn("accountsRevision={accountsChanged + settingsClosed}", element.group(0))

    def test_what_settings_saves_while_it_is_open_counts_as_a_change(self):
        modal = re.search(r"<SettingsModal.*?onImport", PAGE, re.DOTALL).group(0)
        self.assertIn("setAccountsChanged(n => n + 1)", modal)
        self.assertIn("setSettingsClosed(n => n + 1)", modal)                 # and closing it still counts, as it did

    def test_the_panel_asks_again_when_the_window_is_shown_and_asks_fresh_after_a_change(self):
        self.assertIn("window.addEventListener('focus', again)", PANEL)
        self.assertIn("document.addEventListener('visibilitychange', again)", PANEL)
        self.assertIn("api.cliSigninAvailable('', accountsRevision > 0 || shownAgain > 0)", PANEL)
        self.assertIn("[accountsRevision, shownAgain]", PANEL)

    def test_a_refresh_keeps_the_last_answer_on_screen_instead_of_flashing_checking(self):
        look = PANEL[PANEL.index("const [shownAgain"):PANEL.index("// A stack that only some targets")]
        self.assertNotIn("setCli(null)", look)
        self.assertIn("setCli(prior => prior || {})", look)                   # a failed look does not erase a good answer

    def test_looks_are_not_made_more_than_every_few_seconds_when_the_window_is_shown_over_and_over(self):
        self.assertIn("Date.now() - lastLook.current < 4000", PANEL)
        self.assertIn("document.visibilityState === 'hidden'", PANEL)


class TheMongoPageOffersTheFixTests(unittest.TestCase):
    ACCOUNTS = (ROOT / "studio" / "components" / "deploy" / "DeployAccounts.jsx").read_text(encoding="utf-8")

    def test_a_refused_password_gets_a_button_that_makes_this_computer_its_own_user_and_tests_again(self):
        self.assertIn("status.repairable", self.ACCOUNTS)
        self.assertIn("Fix the connection", self.ACCOUNTS)
        repair = self.ACCOUNTS[self.ACCOUNTS.index("async function repair()"):self.ACCOUNTS.index("async function connectAccount()")]
        self.assertIn("api.deploy('/mongodb/repair', {})", repair)
        self.assertIn("await onSave({})", repair)
        self.assertIn("await test('')", repair)


class TheServerForgetsWhatItRememberedTests(unittest.TestCase):
    """Who a tool is signed in as is remembered for a few seconds, because asking is slow; a change drops it."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patch = mock.patch.object(config, "SETTINGS_FILE", Path(self.temp.name) / "settings.json")
        patch.start()
        self.addCleanup(patch.stop)
        self.signins = cli_signin.SIGNINS
        self.signins._seen["vercel"] = (time.time(), {"installed": True, "signed_in": False, "identity": None})
        self.addCleanup(self.signins._seen.clear)

    def test_forget_empties_what_was_remembered(self):
        self.signins.forget()
        self.assertEqual(self.signins._seen, {})

    def test_saving_an_accounts_token_or_connection_drops_it_so_the_next_look_is_the_truth(self):
        for key, value in (("vercel_token", "tok-1234567890"), ("netlify_token", "tok-1234567890"), ("github_token", "ghp_1234567890"),
                           ("aws_profile", "deployment-agent"), ("azure_credentials", "{}"),
                           ("deploy_mongodb_uri", "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/?retryWrites=true")):
            with self.subTest(setting=key):
                self.signins._seen["vercel"] = (time.time(), {"signed_in": False})
                httpd.write_settings({key: value})
                self.assertEqual(self.signins._seen, {}, key)

    def test_a_setting_that_is_not_an_account_leaves_it_alone(self):
        httpd.write_settings({"language": "en"})
        self.assertIn("vercel", self.signins._seen)

    def test_a_sign_in_that_just_finished_is_seen_by_the_next_unforced_look(self):
        calls = []
        provider = mock.Mock(tool="vercel")
        with mock.patch.object(self.signins, "_look", side_effect=lambda p: calls.append(1) or {"signed_in": True}), \
                mock.patch.dict(cli_signin.PROVIDERS, {"vercel": provider}, clear=False):
            self.signins.forget()
            row = self.signins.available(only="vercel")["vercel"]          # not "fresh": the cache is what was dropped
        self.assertTrue(row["signed_in"])
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
