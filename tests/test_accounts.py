"""Account sign-in, cloud-credit gating and local Ollama independence."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import accounts, config, httpd  # noqa: E402


class AccountsTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.enterContext(mock.patch.object(config, "SETTINGS_FILE", Path(temp.name) / "settings.json"))
        self.enterContext(mock.patch.dict("os.environ", {"AGENTFORGE_ACCOUNTS_URL": "https://admin.example.app"}))
        self.enterContext(mock.patch.object(accounts, "_on", True))
        self.calls = []
        self.replies = {}
        accounts._asked_at = 0.0

        def call(method, path, body=None, token=""):
            self.calls.append((method, path, body, token))
            return self.replies.get(path, (500, {}))

        self.enterContext(mock.patch.object(accounts, "_call", side_effect=call))

    def approved(self, **patch):
        return {"id": "a1", "email": "nimal@example.com", "name": "Nimal", "status": "approved",
                "plan": "free", "limitUsd": 8, "usedUsd": 3, "remainingUsd": 5,
                "weeklyPriceUsd": 21, "checkoutAvailable": False, **patch}

    def test_cloud_requires_sign_in_then_reads_usd_credit(self):
        self.enterContext(mock.patch.object(config, "built_in_engine", return_value={"url": "https://engine", "token": "x"}))
        with self.assertRaisesRegex(accounts.NotAllowed, "Sign in"):
            accounts.check()
        config.save_settings({accounts.TOKEN: "account-token"})
        self.replies["/api/accounts/me"] = (200, {"account": self.approved()})
        accounts.check()
        status = httpd.account_status({})
        self.assertEqual(status["remainingUsd"], 5)
        self.assertEqual(status["plan"], "free")

    def test_cloud_credit_exhaustion_and_admin_unlimited(self):
        self.enterContext(mock.patch.object(config, "built_in_engine", return_value={"url": "https://engine", "token": "x"}))
        config.save_settings({accounts.TOKEN: "account-token"})
        self.replies["/api/accounts/me"] = (200, {"account": self.approved(remainingUsd=0)})
        with self.assertRaisesRegex(accounts.NotAllowed, "credit is used up"):
            accounts.check()
        self.replies["/api/accounts/me"] = (200, {"account": self.approved(unlimited=True, remainingUsd=0)})
        accounts.current(fresh=True)
        accounts.check()

    def test_free_plan_hides_glm_and_replaces_an_older_choice(self):
        self.enterContext(mock.patch.object(config, "built_in_engine", return_value={"url": "https://engine", "token": "x"}))
        config.save_settings({accounts.TOKEN: "account-token", "model": "glm-5.3-flash:cloud"})
        self.replies["/api/accounts/me"] = (200, {"account": self.approved()})
        with mock.patch.object(httpd.ollama_cloud, "engine_names",
                               return_value=["glm-5.3", "glm-5.3-flash", "deepseek-v4.1-flash"]):
            shown = httpd.models({})
        self.assertEqual([row["id"] for row in shown["cloud"]], [accounts.DEFAULT_FREE_MODEL])
        self.assertEqual(shown["selected"], accounts.DEFAULT_FREE_MODEL)
        self.assertEqual(config.setting("model"), accounts.DEFAULT_FREE_MODEL)
        with self.assertRaisesRegex(accounts.NotAllowed, "unavailable on the free plan"):
            accounts.check("glm-5.3:cloud")
        with self.assertRaisesRegex(ValueError, "unavailable on the free plan"):
            httpd.write_settings({"agent_model": "glm-5.3-flash:cloud"})
        accounts.check(accounts.DEFAULT_FREE_MODEL)

    def test_paid_and_admin_accounts_keep_glm_access(self):
        self.enterContext(mock.patch.object(config, "built_in_engine", return_value={"url": "https://engine", "token": "x"}))
        config.save_settings({accounts.TOKEN: "account-token"})
        self.replies["/api/accounts/me"] = (200, {"account": self.approved(plan="paid")})
        accounts.check("glm-5.3:cloud")
        with mock.patch.object(httpd.ollama_cloud, "engine_names", return_value=["glm-5.3"]):
            self.assertEqual(httpd.models({})["cloud"][0]["id"], "glm-5.3:cloud")
        self.replies["/api/accounts/me"] = (200, {"account": self.approved(unlimited=True)})
        accounts.current(fresh=True)
        accounts.check("glm-5.3-flash:cloud")

    def test_local_ollama_needs_no_cloud_account_or_credit(self):
        config.save_settings({"engine": "local"})
        self.assertEqual(httpd.auth_me({})["user"]["id"], "local")
        accounts.check()
        accounts.check("glm-5.3:cloud")
        accounts.record()
        self.assertFalse(accounts.flush())
        self.assertEqual(self.calls, [])

    def test_direct_personal_api_key_does_not_spend_agentforge_credit(self):
        config.save_settings({"engine": "cloud", "ollama_api_key": "personal"})
        accounts.check("glm-5.3-flash:cloud")
        self.assertEqual(self.calls, [])

    def test_checkout_uses_bearer_token_and_never_places_it_in_url(self):
        config.save_settings({accounts.TOKEN: "account-token"})
        self.replies["/api/accounts/checkout"] = (200, {"url": "https://checkout.stripe.com/test"})
        self.assertTrue(httpd.account_checkout({})["ok"])
        self.assertEqual(self.calls[-1], ("POST", "/api/accounts/checkout", {}, "account-token"))

    def test_signup_waits_for_emailed_code_before_creating_an_account(self):
        self.replies["/api/accounts/signup"] = (200, {"verificationRequired": True, "email": "nimal@example.com"})
        result = httpd.auth_signup({"username": "nimal", "email": "nimal@example.com", "password": "password"})
        self.assertFalse(result["ok"])
        self.assertTrue(result["verificationRequired"])
        self.assertEqual(config.setting(accounts.TOKEN, ""), "")
        self.replies["/api/accounts/signup/verify"] = (201, {"token": "new-token", "account": self.approved(usedUsd=0, remainingUsd=8)})
        result = httpd.auth_signup_verify({"email": "nimal@example.com", "code": "123456"})
        self.assertTrue(result["ok"])
        self.assertEqual(config.setting(accounts.TOKEN), "new-token")
        self.assertEqual(result["user"]["account"]["remainingUsd"], 8)
        self.assertEqual(self.calls[-1][2], {"email": "nimal@example.com", "code": "123456"})


if __name__ == "__main__":
    unittest.main()
