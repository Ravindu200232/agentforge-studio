"""Connecting a Supabase account (OAuth, since the CLI has no browser sign-in of its own), and
giving each project the one real Supabase project it owns."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
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
        for patch in (settings_patch, key_patch, vault_patch):
            patch.start()
            self.addCleanup(patch.stop)

    def register(self, client_id="fake-client-id", client_secret="fake-client-secret"):
        config.save_settings({"supabase_client_id": client_id, "supabase_client_secret": client_secret})


class AccountConnectionTests(SupabaseSettingsCase):
    def test_nothing_is_connected_until_an_app_is_registered(self):
        self.assertEqual(sc.token_status(), {"app_registered": False, "connected": False, "org": ""})
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
                mock.patch.object(sc, "_fetch_org_name", return_value=""):
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


if __name__ == "__main__":
    unittest.main()
