"""AgentForge accounts: sign in with an account the admin approved; every model call is one request against its limit.

With no account service set, nothing changes: the person at the computer is signed in, and nothing is counted or refused.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import accounts, bus, config, httpd, session  # noqa: E402


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.enterContext(mock.patch.object(config, "SETTINGS_FILE", Path(self.temp.name) / "settings.json"))
        self.events: list[dict] = []
        self.enterContext(mock.patch.object(bus, "transient", self.events.append))
        self.calls: list[tuple] = []
        self.replies: dict[str, tuple[int, dict]] = {}
        accounts._pending.update(requests=0)
        accounts._asked_at = 0.0

    def serve(self, url="https://admin.example.app"):
        self.enterContext(mock.patch.dict("os.environ", {"AGENTFORGE_ACCOUNTS_URL": url}))
        self.enterContext(mock.patch.object(accounts, "_on", True))

        def call(method, path, body=None, token=""):
            self.calls.append((method, path, body, token))
            reply = self.replies.get(path, (500, {}))
            if isinstance(reply, Exception):
                raise reply
            return reply
        self.enterContext(mock.patch.object(accounts, "_call", side_effect=call))

    def approved(self, limit=1000, used=100):
        return {"id": "a1", "email": "nimal@example.com", "name": "Nimal", "status": "approved", "limit": limit, "used": used}


class OffTests(Case):
    def test_without_an_account_service_the_person_here_is_signed_in_and_nothing_is_counted(self):
        self.enterContext(mock.patch.dict("os.environ", {"AGENTFORGE_ACCOUNTS_URL": ""}))
        self.enterContext(mock.patch.object(accounts, "SERVER_FILE", Path(self.temp.name) / "accounts.json"))
        self.assertFalse(accounts.enabled())
        accounts.check()                                              # never refuses
        accounts.record()
        self.assertEqual(accounts._pending["requests"], 0)
        self.assertEqual(httpd.auth_me({})["user"]["id"], "local")
        self.assertEqual(httpd.account_status({}), {"enabled": False})

    def test_an_address_alone_asks_nothing_of_code_run_outside_the_studios_backend(self):
        self.enterContext(mock.patch.dict("os.environ", {"AGENTFORGE_ACCOUNTS_URL": "https://admin.example.app"}))
        self.assertFalse(accounts.enabled())                          # the tests, a script
        accounts.check()
        with mock.patch.object(accounts, "_on", True):                # server.py has started
            self.assertTrue(accounts.enabled())


class SigningInTests(Case):
    def setUp(self):
        super().setUp()
        self.serve()

    def test_a_new_account_waits_for_the_admin(self):
        self.replies["/api/accounts/signup"] = (201, {"status": "pending"})
        said = httpd.auth_signup({"username": "nimal", "email": "nimal@example.com", "password": "longpassword"})
        self.assertFalse(said["ok"])
        self.assertTrue(said["pending"])
        self.assertIn("waiting for the admin's approval", said["error"])
        self.assertEqual(config.setting(accounts.TOKEN, ""), "")

    def test_signing_in_before_approval_says_so(self):
        self.replies["/api/accounts/login"] = (403, {"status": "pending"})
        said = httpd.auth_login({"login": "nimal@example.com", "password": "x"})
        self.assertTrue(said["pending"])

    def test_an_approved_account_signs_in_and_keeps_its_token(self):
        self.replies["/api/accounts/login"] = (200, {"token": "tok", "account": self.approved()})
        said = httpd.auth_login({"login": "nimal@example.com", "password": "x"})
        self.assertTrue(said["ok"])
        self.assertEqual(said["user"]["account"], {"status": "approved", "limit": 1000, "used": 100, "remaining": 900,
                                                   "unlimited": False})
        self.assertEqual(config.setting(accounts.TOKEN), "tok")
        self.assertEqual(self.events[-1]["type"], "account_usage")

    def test_who_is_signed_in_is_asked_of_the_admin_app_and_sign_in_is_required(self):
        self.assertEqual(httpd.auth_me({}), {"ok": False, "required": True, "pending": False})
        config.save_settings({accounts.TOKEN: "tok"})
        self.replies["/api/accounts/me"] = (200, {"account": self.approved()})
        me = httpd.auth_me({})
        self.assertTrue(me["ok"])
        self.assertTrue(me["required"])
        self.assertEqual(me["user"]["email"], "nimal@example.com")

    def test_a_token_the_admin_app_no_longer_knows_signs_out(self):
        config.save_settings({accounts.TOKEN: "old"})
        self.replies["/api/accounts/me"] = (401, {})
        self.assertEqual(accounts.current(fresh=True), {})
        self.assertEqual(config.setting(accounts.TOKEN), "")

    def test_signing_out_forgets_the_token(self):
        config.save_settings({accounts.TOKEN: "tok"})
        httpd.auth_out({})
        self.assertEqual(config.setting(accounts.TOKEN), "")


class LimitTests(Case):
    def setUp(self):
        super().setUp()
        self.serve()
        config.save_settings({accounts.TOKEN: "tok"})

    def known(self, **account):
        self.replies["/api/accounts/me"] = (200, {"account": {**self.approved(), **account}})

    def test_an_approved_account_with_tokens_left_may_call_the_model(self):
        self.known()
        accounts.check()

    def test_not_signed_in_waiting_or_used_up_is_refused_with_a_plain_reason(self):
        config.save_settings({accounts.TOKEN: ""})
        with self.assertRaisesRegex(accounts.NotAllowed, "Sign in"):
            accounts.check()
        config.save_settings({accounts.TOKEN: "tok"})
        self.known(status="pending")
        with self.assertRaisesRegex(accounts.NotAllowed, "approval"):
            accounts.current(fresh=True) and accounts.check()
        self.known(used=1000)
        accounts.current(fresh=True)
        with self.assertRaisesRegex(accounts.NotAllowed, "request limit is used up"):
            accounts.check()

    def test_the_admin_is_never_refused_and_sees_the_ollama_balance(self):
        self.known(id="admin", unlimited=True, limit=0, used=5_000_000,
                   ollama={"included": {"balance": 72.5, "allowance": 100}})
        row = accounts.current(fresh=True)
        accounts.check()                                              # no limit, whatever is used
        status = accounts.status_of(row)
        self.assertTrue(status["unlimited"])
        self.assertEqual(status["ollama"]["included"]["balance"], 72.5)

    def test_requests_counted_but_not_yet_sent_count_against_the_limit(self):
        self.known(limit=1000, used=999)
        accounts.current(fresh=True)
        with mock.patch.object(accounts, "_start_flusher"):
            accounts.record()
        with self.assertRaises(accounts.NotAllowed):
            accounts.check()

    def test_each_answered_call_is_one_request_shown_live_and_sent_to_the_admin_app(self):
        self.known(limit=1000, used=100)
        accounts.current(fresh=True)
        with mock.patch.object(accounts, "_start_flusher"):
            accounts.record()
            accounts.record()
        live = self.events[-1]
        self.assertEqual((live["used"], live["remaining"]), (102, 898))
        self.replies["/api/accounts/usage"] = (200, {"account": self.approved(used=102)})
        self.assertFalse(accounts.flush())
        sent = next(c for c in self.calls if c[1] == "/api/accounts/usage")
        self.assertEqual(sent[2], {"requests": 2})
        self.assertEqual(sent[3], "tok")
        self.assertEqual(config.setting(accounts.CACHE)["used"], 102)

    def test_requests_that_could_not_be_sent_are_kept_for_the_next_send(self):
        self.known()
        accounts.current(fresh=True)
        with mock.patch.object(accounts, "_start_flusher"):
            accounts.record()
        self.replies["/api/accounts/usage"] = ConnectionError("offline")
        self.assertTrue(accounts.flush())
        self.assertEqual(accounts._pending["requests"], 1)


class EveryModelCallTests(Case):
    """`RetryingClient.chat` is where every model call goes: it asks first and counts after."""

    def test_a_refused_account_never_reaches_the_model(self):
        inner = mock.Mock()
        with mock.patch.object(accounts, "check", side_effect=accounts.NotAllowed("Your token limit is used up.")):
            with self.assertRaisesRegex(accounts.NotAllowed, "used up"):
                session.RetryingClient(inner).chat(model="m", messages=[])
        inner.chat.assert_not_called()

    def test_a_reply_and_a_streamed_reply_are_one_request_each(self):
        reply = {"message": {"content": "hi"}}
        chunks = [{"message": {"content": "h"}}, {"message": {"content": "i"}}, {"message": {"content": "!"}, "done": True}]
        inner = SimpleNamespace(chat=lambda **kw: iter(chunks) if kw.get("stream") else reply)
        counted: list = []
        with mock.patch.object(accounts, "check"), mock.patch.object(accounts, "record", lambda: counted.append(1)):
            client = session.RetryingClient(inner)
            client.chat(model="m", messages=[])
            self.assertEqual(counted, [1])
            stream = client.chat(model="m", messages=[], stream=True)
            next(stream)                                              # counted when the model starts answering
            self.assertEqual(counted, [1, 1])
            list(stream)
        self.assertEqual(counted, [1, 1])


if __name__ == "__main__":
    unittest.main()
