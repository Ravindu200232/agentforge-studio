"""Connecting a Supabase account (OAuth, since the CLI has no browser sign-in of its own), and
giving each project the one real Supabase project it owns."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import config, httpd, supabase_connect as sc  # noqa: E402

PROJECT = "prj_supabase_connect_test"


class SupabaseSettingsCase(unittest.TestCase):
    """A temporary settings.json and vault, so a test never touches the real ones on this machine."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings_patch = mock.patch.object(config, "SETTINGS_FILE", Path(self.temp.name) / "settings.json")
        key_patch = mock.patch.object(sc, "KEY", Path(self.temp.name) / "supabase.key")
        vault_patch = mock.patch.object(sc, "VAULT", Path(self.temp.name) / "supabase.enc")
        # No built-in engine unless a test gives one: it is the broker that holds the publisher's OAuth app.
        self.engine: dict = {}
        engine_patch = mock.patch.object(config, "built_in_engine", side_effect=lambda: dict(self.engine))
        for patch in (settings_patch, key_patch, vault_patch, engine_patch):
            patch.start()
            self.addCleanup(patch.stop)

    def register(self, client_id="fake-client-id", client_secret="fake-client-secret"):
        config.save_settings({"supabase_client_id": client_id, "supabase_client_secret": client_secret})


class AccountConnectionTests(SupabaseSettingsCase):
    def test_nothing_is_connected_until_an_app_is_registered(self):
        self.assertEqual(sc.token_status(), {"app_registered": False, "connected": False, "org": "", "broker": False,
                                              "accounts": [], "active": ""})
        self.assertFalse(sc.credentials_saved())

    def test_registering_the_app_does_not_by_itself_sign_anyone_in(self):
        self.register()
        status = sc.token_status()
        self.assertEqual((status["app_registered"], status["connected"]), (True, False))

    def test_forgetting_the_account_keeps_the_registered_app(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "at", "supabase_oauth_refresh_token": "rt",
                              "supabase_org": "Acme"})
        sc.forget_account()
        status = sc.token_status()
        self.assertEqual((status["app_registered"], status["connected"], status["org"]), (True, False, ""))


class StartTests(SupabaseSettingsCase):
    def test_starting_without_a_registered_app_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Register a Supabase OAuth app"):
            sc.OAUTH.start()

    def test_start_builds_the_exact_authorize_url_supabase_expects(self):
        self.register(client_id="my-client-id")
        started = sc.OAUTH.start()
        uri = started["verification_uri"]
        self.assertTrue(uri.startswith(sc.AUTHORIZE_URL + "?"))
        for expected in ("response_type=code", "client_id=my-client-id", "scope=all",
                         f"state={started['flow_id']}", "code_challenge=", "code_challenge_method=S256"):
            self.assertIn(expected, uri)
        # The redirect_uri is AgentForge's own already-running API server - not a port of its own -
        # so it is exactly what the person registers as the OAuth app's callback URL. "localhost",
        # not "127.0.0.1": Supabase's authorize endpoint refuses a loopback IP with
        # {"message":"redirect_uri must use HTTPS"} (tried live) even though the dashboard's own
        # callback-URL field accepts one; only the literal hostname is exempted.
        self.assertIn("redirect_uri=http%3A%2F%2Flocalhost%3A7824%2F__agentforge%2Fapi%2Fsupabase-oauth%2Fcallback", uri)

    def test_every_flow_gets_its_own_unguessable_state(self):
        self.register()
        first, second = sc.OAUTH.start(), sc.OAUTH.start()
        self.assertNotEqual(first["flow_id"], second["flow_id"])


class CallbackAndPollTests(SupabaseSettingsCase):
    def test_poll_is_pending_until_the_callback_arrives(self):
        self.register()
        started = sc.OAUTH.start()
        self.assertEqual(sc.OAUTH.poll(started["flow_id"]), {"status": "pending"})

    def test_a_callback_with_an_unknown_state_matches_nothing(self):
        self.register()
        sc.OAUTH.start()
        self.assertFalse(sc.OAUTH.receive_callback("not-a-real-flow", "code", ""))

    def test_polling_an_unknown_flow_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no longer running"):
            sc.OAUTH.poll("sbo_does_not_exist")

    def test_a_denied_sign_in_is_surfaced_as_the_reason_supabase_gave(self):
        self.register()
        started = sc.OAUTH.start()
        self.assertTrue(sc.OAUTH.receive_callback(started["flow_id"], "", "User denied access"))
        with self.assertRaisesRegex(ValueError, "User denied access"):
            sc.OAUTH.poll(started["flow_id"])

    def test_a_successful_callback_exchanges_the_code_and_keeps_the_tokens(self):
        self.register()
        started = sc.OAUTH.start()
        sc.OAUTH.receive_callback(started["flow_id"], "auth-code-123", "")
        token_answer = mock.Mock(status_code=200)
        token_answer.json.return_value = {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}
        orgs_answer = mock.Mock(returncode=0, stdout='[{"id": "org-1", "name": "Acme"}]', stderr="")
        with mock.patch("httpx.post", return_value=token_answer) as post, \
                mock.patch.object(sc, "_tool", return_value="supabase"), \
                mock.patch("subprocess.run", return_value=orgs_answer):
            result = sc.OAUTH.poll(started["flow_id"])
        self.assertEqual((result["status"], result["connected"], result["org"]), ("ready", True, "Acme"))
        # The exchange authenticates as the registered app, not with anything the browser sent.
        self.assertEqual(post.call_args.kwargs["auth"], ("fake-client-id", "fake-client-secret"))
        sent = post.call_args.kwargs["data"]
        self.assertEqual((sent["grant_type"], sent["code"]), ("authorization_code", "auth-code-123"))
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-1")
        self.assertEqual(config.setting("supabase_org"), "Acme")

    def test_a_flow_can_only_be_polled_to_completion_once(self):
        self.register()
        started = sc.OAUTH.start()
        sc.OAUTH.receive_callback(started["flow_id"], "", "denied")
        with self.assertRaises(ValueError):
            sc.OAUTH.poll(started["flow_id"])
        with self.assertRaisesRegex(ValueError, "no longer running"):
            sc.OAUTH.poll(started["flow_id"])

    def test_supabase_rejecting_the_exchange_is_a_clean_error_not_a_crash(self):
        self.register()
        started = sc.OAUTH.start()
        sc.OAUTH.receive_callback(started["flow_id"], "auth-code-123", "")
        rejected = mock.Mock(status_code=400)
        rejected.json.return_value = {"error_description": "Invalid client_id"}
        with mock.patch("httpx.post", return_value=rejected):
            with self.assertRaisesRegex(ValueError, "Invalid client_id"):
                sc.OAUTH.poll(started["flow_id"])


class CallbackRouteTests(SupabaseSettingsCase):
    """The route in httpd.py, exercised through the real dispatcher - the browser's own request."""

    def test_the_matching_and_denied_and_unknown_cases_each_answer_a_page(self):
        self.register()
        started = sc.OAUTH.start()

        ok = httpd.dispatch("GET", "/supabase-oauth/callback", {}, {"state": started["flow_id"], "code": "x"})
        self.assertIn("You can close this tab", ok.body.decode())
        self.assertEqual(ok.content_type, "text/html; charset=utf-8")

        unknown = httpd.dispatch("GET", "/supabase-oauth/callback", {}, {"state": "garbage", "code": "x"})
        self.assertIn("expired", unknown.body.decode())

    def test_a_denied_callback_names_the_reason_without_leaking_markup(self):
        self.register()
        started = sc.OAUTH.start()
        answer = httpd.dispatch("GET", "/supabase-oauth/callback", {},
                                {"state": started["flow_id"], "error": "access_denied",
                                 "error_description": "<script>alert(1)</script>"})
        body = answer.body.decode()
        self.assertIn("Supabase said:", body)
        self.assertNotIn("<script>", body)  # escaped, not executed


class RefreshTests(SupabaseSettingsCase):
    def test_a_still_valid_token_is_used_as_is_no_network_call(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "still-good",
                              "supabase_oauth_expires_at": __import__("time").time() + 3600})
        with mock.patch("httpx.post") as post:
            self.assertEqual(sc._env_with_token()["SUPABASE_ACCESS_TOKEN"], "still-good")
        post.assert_not_called()

    def test_an_expired_token_is_refreshed_silently(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "old", "supabase_oauth_refresh_token": "rt-1",
                              "supabase_oauth_expires_at": 0})
        refreshed = mock.Mock(status_code=200)
        refreshed.json.return_value = {"access_token": "new-token", "refresh_token": "rt-2", "expires_in": 3600}
        with mock.patch("httpx.post", return_value=refreshed) as post, \
                mock.patch.object(sc, "_fetch_org", return_value={}):
            env = sc._env_with_token()
        self.assertEqual(env["SUPABASE_ACCESS_TOKEN"], "new-token")
        self.assertEqual(post.call_args.kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(config.setting("supabase_oauth_refresh_token"), "rt-2")

    def test_a_failed_refresh_falls_back_to_the_stale_token_rather_than_crash(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "old", "supabase_oauth_refresh_token": "rt-1",
                              "supabase_oauth_expires_at": 0})
        with mock.patch("httpx.post", side_effect=__import__("httpx").ConnectError("network down")):
            env = sc._env_with_token()
        self.assertEqual(env["SUPABASE_ACCESS_TOKEN"], "old")


class ProjectRecordTests(SupabaseSettingsCase):
    def test_a_project_with_no_record_reports_not_connected(self):
        self.assertEqual(sc.status(PROJECT), {"connected": False})
        self.assertEqual(sc.env_for(PROJECT), {})

    def test_env_for_hands_out_every_alias_a_template_might_read(self):
        sc._write_all({PROJECT: {"ref": "abcdef", "name": "demo", "url": "https://abcdef.supabase.co",
                                 "anon_key": "anon-1", "service_role_key": "service-1", "db_password": "pw-1"}})
        env = sc.env_for(PROJECT)
        self.assertEqual(env["SUPABASE_URL"], "https://abcdef.supabase.co")
        self.assertEqual(env["NEXT_PUBLIC_SUPABASE_ANON_KEY"], "anon-1")
        self.assertEqual(env["VITE_SUPABASE_URL"], "https://abcdef.supabase.co")
        self.assertEqual(env["SUPABASE_DB_URL"], "postgresql://postgres:pw-1@db.abcdef.supabase.co:5432/postgres")
        self.assertNotIn("NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY", env)  # never a public alias

    def test_forgetting_a_project_does_not_touch_another_projects_record(self):
        sc._write_all({PROJECT: {"ref": "a"}, "prj_other": {"ref": "b"}})
        sc.forget(PROJECT)
        self.assertEqual(sc.status(PROJECT), {"connected": False})
        self.assertTrue(sc.status("prj_other")["connected"])


class EnsureProjectTests(SupabaseSettingsCase):
    def test_refuses_to_create_a_project_with_no_account_connected(self):
        with self.assertRaisesRegex(ValueError, "No Supabase account is connected"):
            sc.ensure_project(PROJECT)

    def test_an_existing_record_is_returned_without_calling_the_cli_again(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "at"})
        sc._write_all({PROJECT: {"ref": "existing", "name": PROJECT, "url": "https://existing.supabase.co"}})
        with mock.patch.object(sc, "_run_json") as run_json:
            result = sc.ensure_project(PROJECT)
        run_json.assert_not_called()
        self.assertEqual(result["ref"], "existing")

    def test_creates_a_project_and_waits_for_its_keys(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "at"})
        calls = []

        def fake_run_json(args, timeout=40):
            calls.append(args)
            if args[1:3] == ["orgs", "list"]:
                return [{"id": "org-1", "name": "Acme"}]
            if args[1:3] == ["projects", "create"]:
                return {"id": "newref"}
            if args[1:3] == ["projects", "api-keys"]:
                return [{"name": "anon", "api_key": "anon-1"}, {"name": "service_role", "api_key": "service-1"}]
            raise AssertionError(f"unexpected CLI call: {args}")

        with mock.patch.object(sc, "_tool", return_value="supabase"), \
                mock.patch.object(sc, "_run_json", side_effect=fake_run_json), \
                mock.patch.object(sc, "time") as fake_time:
            fake_time.sleep.return_value = None
            fake_time.time.side_effect = __import__("time").time
            result = sc.ensure_project(PROJECT, name="My App")
        self.assertEqual(result, {"connected": True, "ref": "newref", "name": "My App", "url": "https://newref.supabase.co"})
        row = sc.record(PROJECT)
        self.assertEqual((row["anon_key"], row["service_role_key"]), ("anon-1", "service-1"))
        self.assertTrue(row["db_password"])  # generated, never empty

    def test_a_new_project_goes_to_the_chosen_organisation_and_region(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "at"})
        sc._write_all({PROJECT: {"ref": "oldref", "name": PROJECT, "url": "https://oldref.supabase.co"}})
        calls = []

        def fake_run_json(args, timeout=40):
            calls.append(args)
            if args[1:3] == ["orgs", "list"]:
                return [{"id": "org-free", "name": "Mine"}, {"id": "org-pro", "name": "Team"}]
            if args[1:3] == ["projects", "create"]:
                return {"id": "newref"}
            return [{"name": "anon", "api_key": "a"}, {"name": "service_role", "api_key": "s"}]

        with mock.patch.object(sc, "_tool", return_value="supabase"), \
                mock.patch.object(sc, "_run_json", side_effect=fake_run_json):
            result = sc.ensure_project(PROJECT, name="Shop", region="ap-south-1", org_id="org-pro", fresh=True)
        create = next(args for args in calls if args[1:3] == ["projects", "create"])
        self.assertEqual(create[create.index("--org-id") + 1], "org-pro")
        self.assertEqual(create[create.index("--region") + 1], "ap-south-1")
        self.assertEqual(result["ref"], "newref")
        with mock.patch.object(sc, "_tool", return_value="supabase"), \
                mock.patch.object(sc, "_run_json", side_effect=fake_run_json):
            with self.assertRaisesRegex(ValueError, "no organisation org-gone"):
                sc.ensure_project(PROJECT, org_id="org-gone", fresh=True)

    def test_account_facts_list_organisations_and_projects_never_keys(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "at"})

        def fake_run_json(args, timeout=40):
            if args[1:3] == ["orgs", "list"]:
                return [{"id": "org-free", "name": "Mine"}]
            return [{"id": "ref1", "name": "Old shop", "region": "us-east-1", "status": "ACTIVE_HEALTHY",
                     "organization_id": "org-free", "anon_key": "secret"}]

        answer = mock.Mock(status_code=200)
        answer.json.return_value = {"plan": "free"}
        with mock.patch.object(sc, "_tool", return_value="supabase"), \
                mock.patch.object(sc, "_run_json", side_effect=fake_run_json), \
                mock.patch.object(sc.httpx, "get", return_value=answer):
            facts = sc.account_facts()
        self.assertEqual(facts["organizations"], [{"id": "org-free", "name": "Mine", "plan": "free"}])
        self.assertEqual(facts["projects"][0]["ref"], "ref1")
        self.assertNotIn("secret", json.dumps(facts))

    def test_no_organisation_is_a_clear_error_not_a_crash(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "at"})
        with mock.patch.object(sc, "_tool", return_value="supabase"), \
                mock.patch.object(sc, "_run_json", return_value=[]):
            with self.assertRaisesRegex(ValueError, "no organisation"):
                sc.ensure_project(PROJECT)


class MakeRoomTests(unittest.TestCase):
    def _answer(self, status: int, body: dict | None = None):
        return SimpleNamespace(status_code=status, text=json.dumps(body or {}), json=lambda: body or {})

    def test_pause_waits_until_the_project_is_down(self):
        states = iter([self._answer(200, {"status": "ACTIVE_HEALTHY"}), self._answer(200, {"status": "PAUSING"}),
                       self._answer(200, {"status": "INACTIVE"})])
        with mock.patch.object(sc, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(sc.httpx, "get", side_effect=lambda *a, **k: next(states)), \
             mock.patch.object(sc.httpx, "post", return_value=self._answer(200)) as post, \
             mock.patch.object(sc.time, "sleep"):
            sc.make_room("refshop", "pause")
        self.assertTrue(post.call_args.args[0].endswith("/v1/projects/refshop/pause"))

    def test_a_project_already_paused_is_left_alone(self):
        with mock.patch.object(sc, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(sc.httpx, "get", return_value=self._answer(200, {"status": "INACTIVE"})), \
             mock.patch.object(sc.httpx, "post") as post:
            sc.make_room("refshop", "pause")
        post.assert_not_called()

    def test_delete_forgets_the_agentforge_project_that_used_it(self):
        saved = {"prj_shop": {"ref": "refshop"}, "prj_other": {"ref": "refother"}}
        states = iter([self._answer(200, {"status": "ACTIVE_HEALTHY"}), self._answer(404)])
        with mock.patch.object(sc, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(sc.httpx, "get", side_effect=lambda *a, **k: next(states)), \
             mock.patch.object(sc.httpx, "delete", return_value=self._answer(200)) as delete, \
             mock.patch.object(sc.time, "sleep"), \
             mock.patch.object(sc, "_read_all", return_value=dict(saved)), \
             mock.patch.object(sc, "_write_all") as wrote:
            sc.make_room("refshop", "delete")
        self.assertTrue(delete.call_args.args[0].endswith("/v1/projects/refshop"))
        self.assertEqual(wrote.call_args.args[0], {"prj_other": {"ref": "refother"}})

    def test_a_refusal_comes_back_as_the_reason(self):
        with mock.patch.object(sc, "_refresh_if_needed", return_value="tok"), \
             mock.patch.object(sc.httpx, "get", return_value=self._answer(200, {"status": "ACTIVE_HEALTHY"})), \
             mock.patch.object(sc.httpx, "delete", return_value=self._answer(403, {"message": "no access"})):
            with self.assertRaisesRegex(ValueError, "would not delete project refshop: no access"):
                sc.make_room("refshop", "delete")


class OauthHttpRoutesTests(SupabaseSettingsCase):
    def test_status_start_and_cancel_routes_round_trip(self):
        self.register()
        status = httpd.dispatch("POST", "/supabase/oauth/status", {}, {})
        self.assertEqual((status["app_registered"], status["connected"]), (True, False))

        started = httpd.dispatch("POST", "/supabase/oauth/start", {}, {})
        self.assertIn("flow_id", started)

        cancelled = httpd.dispatch("POST", "/supabase/oauth/cancel", {"flow_id": started["flow_id"]}, {})
        self.assertEqual(cancelled["status"], "cancelled")
        with self.assertRaises(ValueError):
            httpd.dispatch("POST", "/supabase/oauth/poll", {"flow_id": started["flow_id"]}, {})


class BrokerSignInTests(SupabaseSettingsCase):
    """Nobody who installs AgentForge registers an OAuth app: the engine Worker holds the publisher's, so signing in is a
    click. Every call to it carries the app token, and the client secret never reaches this computer."""

    ENGINE = {"url": "https://engine.example.test", "token": "app-token"}

    def setUp(self):
        super().setUp()
        self.engine = dict(self.ENGINE)

    @staticmethod
    def answer(status, body):
        reply = mock.Mock(status_code=status)
        reply.json.return_value = body
        return reply

    def link(self):
        return sc.AUTHORIZE_URL + "?client_id=publisher&state=signed"

    def start(self, link=None):
        with mock.patch("httpx.post", return_value=self.answer(200, {"authorize_url": link or self.link()})) as post:
            started = sc.OAUTH.start()
        return started, post

    def test_a_broker_means_nothing_to_register(self):
        status = sc.token_status()
        self.assertEqual((status["app_registered"], status["connected"], status["broker"]), (True, False, True))
        self.assertFalse(sc.credentials_saved())

    def test_start_asks_the_broker_for_the_link_without_any_client_id(self):
        started, post = self.start()
        self.assertEqual(started["verification_uri"], self.link())
        self.assertEqual(post.call_args.args[0], "https://engine.example.test/oauth/supabase/start")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer app-token")
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["flow_id"], started["flow_id"])
        self.assertEqual(sent["return_to"], sc.REDIRECT_URI)
        self.assertGreaterEqual(len(sent["challenge"]), 43)  # a PKCE S256 challenge; the verifier stays here
        self.assertNotIn("verifier", json.dumps(sent))

    def test_a_link_that_is_not_supabases_is_never_opened(self):
        with mock.patch("httpx.post", return_value=self.answer(200, {"authorize_url": "https://evil.example/login"})):
            with self.assertRaisesRegex(ValueError, "not Supabase's"):
                sc.OAUTH.start()

    def test_a_broker_that_is_not_set_up_says_so_when_there_is_no_own_app_to_fall_back_on(self):
        not_set_up = self.answer(503, {"error": "Supabase sign-in is not set up on this engine yet"})
        with mock.patch("httpx.post", return_value=not_set_up):
            with self.assertRaisesRegex(ValueError, "not set up"):
                sc.OAUTH.start()
        with mock.patch("httpx.post", side_effect=__import__("httpx").ConnectError("down")):
            with self.assertRaisesRegex(ValueError, "could not be reached"):
                sc.OAUTH.start()

    def test_a_persons_own_saved_app_still_works_when_the_broker_is_not_set_up(self):
        self.register(client_id="mine")
        with mock.patch("httpx.post", return_value=self.answer(503, {"error": "not set up"})):
            started = sc.OAUTH.start()
        self.assertIn("client_id=mine", started["verification_uri"])

    def test_the_code_is_traded_through_the_broker_with_the_verifier_and_no_secret(self):
        started, _ = self.start()
        sc.OAUTH.receive_callback(started["flow_id"], "auth-code-9", "")
        tokens = self.answer(200, {"access_token": "at-9", "refresh_token": "rt-9", "expires_in": 3600})
        with mock.patch("httpx.post", return_value=tokens) as post, \
                mock.patch.object(sc, "_fetch_org", return_value={"id": "org-1", "name": "Acme"}):
            result = sc.OAUTH.poll(started["flow_id"])
        self.assertEqual((result["status"], result["connected"], result["org"]), ("ready", True, "Acme"))
        self.assertEqual(post.call_args.args[0], "https://engine.example.test/oauth/supabase/token")
        sent = post.call_args.kwargs["json"]
        self.assertEqual((sent["grant_type"], sent["code"]), ("authorization_code", "auth-code-9"))
        self.assertTrue(sent["code_verifier"])
        self.assertNotIn("auth", post.call_args.kwargs)  # no client id or secret from this side
        self.assertEqual(config.setting("supabase_oauth_via"), "broker")

    def test_the_broker_refusing_the_exchange_is_a_clean_error(self):
        started, _ = self.start()
        sc.OAUTH.receive_callback(started["flow_id"], "auth-code-9", "")
        with mock.patch("httpx.post", return_value=self.answer(400, {"error_description": "Invalid code"})):
            with self.assertRaisesRegex(ValueError, "Invalid code"):
                sc.OAUTH.poll(started["flow_id"])

    def test_a_token_from_the_broker_is_refreshed_through_the_broker(self):
        config.save_settings({"supabase_oauth_access_token": "old", "supabase_oauth_refresh_token": "rt-1",
                              "supabase_oauth_expires_at": 0, "supabase_oauth_via": "broker"})
        refreshed = self.answer(200, {"access_token": "new", "refresh_token": "rt-2", "expires_in": 3600})
        with mock.patch("httpx.post", return_value=refreshed) as post, \
                mock.patch.object(sc, "_fetch_org", return_value={}):
            env = sc._env_with_token()
        self.assertEqual(env["SUPABASE_ACCESS_TOKEN"], "new")
        self.assertEqual(post.call_args.args[0], "https://engine.example.test/oauth/supabase/token")
        self.assertEqual(post.call_args.kwargs["json"], {"grant_type": "refresh_token", "refresh_token": "rt-1"})
        self.assertEqual(config.setting("supabase_oauth_via"), "broker")  # a refresh does not change who issued it

    def test_a_token_from_a_persons_own_app_is_refreshed_with_that_app_even_when_a_broker_exists(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "old", "supabase_oauth_refresh_token": "rt-1",
                              "supabase_oauth_expires_at": 0})  # saved before the broker existed: no "via"
        refreshed = self.answer(200, {"access_token": "new", "expires_in": 3600})
        with mock.patch("httpx.post", return_value=refreshed) as post, \
                mock.patch.object(sc, "_fetch_org", return_value={}):
            sc._env_with_token()
        self.assertEqual(post.call_args.args[0], sc.TOKEN_URL)
        self.assertEqual(post.call_args.kwargs["auth"], ("fake-client-id", "fake-client-secret"))

    def test_losing_the_broker_does_not_crash_a_refresh(self):
        config.save_settings({"supabase_oauth_access_token": "old", "supabase_oauth_refresh_token": "rt-1",
                              "supabase_oauth_expires_at": 0, "supabase_oauth_via": "broker"})
        self.engine = {}
        self.assertEqual(sc._env_with_token()["SUPABASE_ACCESS_TOKEN"], "old")

    def test_signing_in_again_through_the_broker_replaces_an_own_app_session(self):
        self.register()
        config.save_settings({"supabase_oauth_access_token": "old-own", "supabase_oauth_via": "own"})
        started, _ = self.start()
        sc.OAUTH.receive_callback(started["flow_id"], "c", "")
        with mock.patch("httpx.post", return_value=self.answer(200, {"access_token": "brokered", "expires_in": 60})), \
                mock.patch.object(sc, "_fetch_org", return_value={}):
            sc.OAUTH.poll(started["flow_id"])
        self.assertEqual((config.setting("supabase_oauth_access_token"), config.setting("supabase_oauth_via")),
                         ("brokered", "broker"))

    def test_forgetting_the_account_forgets_who_issued_it(self):
        config.save_settings({"supabase_oauth_access_token": "at", "supabase_oauth_via": "broker"})
        sc.forget_account()
        self.assertFalse(config.setting("supabase_oauth_via"))
        self.assertFalse(sc.token_status()["connected"])


class SeveralAccountsTests(SupabaseSettingsCase):
    """A person with more than one Supabase account (or organisation) signs in as each, and switches between them."""

    ENGINE = {"url": "https://engine.example.test", "token": "app-token"}

    def setUp(self):
        super().setUp()
        self.engine = dict(self.ENGINE)
        # Supabase answers "which organisation?" for whichever token is in use, as the real CLI does.
        self.orgs_by_token: dict[str, dict] = {}
        patch = mock.patch.object(sc, "_fetch_org", side_effect=lambda: dict(
            self.orgs_by_token.get(config.setting("supabase_oauth_access_token"), {})))
        patch.start()
        self.addCleanup(patch.stop)

    def sign_in_as(self, org, access, refresh):
        """One browser sign-in that lands on `org`."""
        self.orgs_by_token[access] = org
        with mock.patch("httpx.post", return_value=mock.Mock(status_code=200, json=lambda: {"authorize_url": sc.AUTHORIZE_URL + "?x=1"})):
            started = sc.OAUTH.start()
        sc.OAUTH.receive_callback(started["flow_id"], "code", "")
        tokens = mock.Mock(status_code=200, json=lambda: {"access_token": access, "refresh_token": refresh, "expires_in": 3600})
        with mock.patch("httpx.post", return_value=tokens):
            return sc.OAUTH.poll(started["flow_id"])

    def ids(self):
        return [(row["id"], row["label"], row["active"]) for row in sc.accounts()]

    def test_the_first_sign_in_is_the_one_account_and_it_is_active(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.assertEqual(self.ids(), [("org-a", "Acme", True)])
        self.assertEqual(sc.token_status()["active"], "org-a")

    def test_signing_in_as_another_account_keeps_the_first_signed_in_and_makes_the_new_one_active(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        status = self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        self.assertEqual(self.ids(), [("org-b", "Globex", True), ("org-a", "Acme", False)])
        self.assertEqual((status["active"], status["org"]), ("org-b", "Globex"))
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-b")   # what builds use now
        self.assertEqual(sc._aside()["org-a"]["refresh_token"], "rt-a")           # nothing of the first was lost

    def test_signing_in_again_as_the_same_account_does_not_make_a_second_one(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-1", "rt-1")
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-2", "rt-2")
        self.assertEqual(self.ids(), [("org-a", "Acme", True)])
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-2")

    def test_signing_in_as_one_kept_aside_makes_it_active_again_and_not_a_duplicate(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a2", "rt-a2")
        self.assertEqual(self.ids(), [("org-a", "Acme", True), ("org-b", "Globex", False)])
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-a2")

    def test_switching_swaps_the_tokens_builds_use_and_keeps_both_signed_in(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        status = sc.switch_account("org-a")
        self.assertEqual((status["active"], status["org"]), ("org-a", "Acme"))
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-a")
        self.assertEqual(config.setting("supabase_oauth_refresh_token"), "rt-a")
        self.assertEqual(self.ids(), [("org-a", "Acme", True), ("org-b", "Globex", False)])
        sc.switch_account("org-b")
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-b")

    def test_a_switched_to_account_is_refreshed_with_its_own_refresh_token(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        sc.switch_account("org-a")
        config.save_settings({"supabase_oauth_expires_at": 0})        # an hour has passed
        refreshed = mock.Mock(status_code=200, json=lambda: {"access_token": "at-a-new", "expires_in": 3600})
        with mock.patch("httpx.post", return_value=refreshed) as post:
            token = sc._env_with_token()["SUPABASE_ACCESS_TOKEN"]
        self.assertEqual(token, "at-a-new")
        self.assertEqual(post.call_args.kwargs["json"]["refresh_token"], "rt-a")
        self.assertEqual(config.setting("supabase_account_id"), "org-a")

    def test_switching_to_an_account_that_is_not_signed_in_is_refused_and_changes_nothing(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        with self.assertRaisesRegex(ValueError, "not signed in"):
            sc.switch_account("org-zzz")
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-a")
        self.assertEqual(sc.switch_account("org-a")["active"], "org-a")      # already active: nothing to do

    def test_removing_an_account_kept_aside_leaves_the_active_one_alone(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        sc.remove_account("org-a")
        self.assertEqual(self.ids(), [("org-b", "Globex", True)])
        with self.assertRaisesRegex(ValueError, "not signed in"):
            sc.remove_account("org-a")

    def test_removing_the_active_account_signs_it_out_and_keeps_the_others(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        status = sc.remove_account("org-b")
        self.assertFalse(status["connected"])
        self.assertEqual(self.ids(), [("org-a", "Acme", False)])
        self.assertEqual(sc.switch_account("org-a")["org"], "Acme")            # and it can be picked up again

    def test_a_session_saved_before_accounts_existed_is_kept_when_another_account_signs_in(self):
        # Tokens in the flat settings, no account id yet: the organisation is asked while its own token is in use.
        config.save_settings({"supabase_oauth_access_token": "old-at", "supabase_oauth_refresh_token": "old-rt",
                              "supabase_org": "Acme", "supabase_oauth_via": "own"})
        self.assertEqual(len(sc.accounts()), 1)
        self.orgs_by_token["old-at"] = {"id": "org-a", "name": "Acme"}
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        self.assertEqual(self.ids(), [("org-b", "Globex", True), ("org-a", "Acme", False)])   # filed under its organisation
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-b")
        self.assertEqual(sc.switch_account("org-a")["org"], "Acme")
        self.assertEqual(config.setting("supabase_oauth_refresh_token"), "old-rt")

    def test_when_the_organisation_cannot_be_asked_a_new_sign_in_simply_replaces_the_account(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({}, "at-x", "rt-x")
        self.assertEqual(len(sc.accounts()), 1)
        self.assertEqual(config.setting("supabase_oauth_access_token"), "at-x")

    def test_the_accounts_kept_aside_never_reach_the_settings_the_studio_reads(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        shown = httpd.dispatch("GET", "/settings", {}, {})
        text = json.dumps(shown, default=str)
        self.assertNotIn("rt-a", text)
        self.assertNotIn("at-a", text)
        self.assertNotIn("supabase_account_credentials", text)

    def test_the_routes_switch_and_remove(self):
        self.sign_in_as({"id": "org-a", "name": "Acme"}, "at-a", "rt-a")
        self.sign_in_as({"id": "org-b", "name": "Globex"}, "at-b", "rt-b")
        switched = httpd.dispatch("POST", "/supabase/oauth/switch", {"id": "org-a"}, {})
        self.assertEqual(switched["active"], "org-a")
        removed = httpd.dispatch("POST", "/supabase/oauth/remove", {"id": "org-b"}, {})
        self.assertEqual([row["id"] for row in removed["accounts"]], ["org-a"])


if __name__ == "__main__":
    unittest.main()
