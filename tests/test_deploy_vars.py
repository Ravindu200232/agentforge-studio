"""What only the customer can give a deployment stays out of the chat and reaches only the deployment."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, changes, config, deploy_vars, httpd, runs, secrets_guard, session, supabase_connect  # noqa: E402
from support import forget_project, isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


PROJECT = "prj_deploy_vars_test"
# A connection string with a password in it, only ever used here as an example of the shape
# secrets_guard.looks_secret() has to catch - not a feature this file tests directly anymore.
SECRET_URI = "postgres://someone:Xy7Pq2Lm9Kd4@db.example.com:5432/app"


class SettingsCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.file = Path(self.temp.name) / "settings.json"
        patch = mock.patch.object(config, "SETTINGS_FILE", self.file)
        patch.start()
        self.addCleanup(patch.stop)


class VariableTests(SettingsCase):
    def test_a_variable_is_saved_by_name_and_only_its_name_and_a_hint_come_back(self):
        rows = deploy_vars.save("ADMIN_PASSWORD", "correct-horse-battery")
        self.assertEqual(rows, [{"name": "ADMIN_PASSWORD", "hint": "tery"}])
        self.assertNotIn("correct-horse", json.dumps(deploy_vars.names()))

    def test_an_empty_value_removes_it(self):
        deploy_vars.save("ADMIN_EMAIL", "a@b.example")
        self.assertEqual(deploy_vars.save("ADMIN_EMAIL", ""), [])

    def test_names_that_would_change_how_the_tools_run_are_refused(self):
        for bad in ("path", "PATH", "NODE_OPTIONS", "AGENTFORGE_LIVE_URL", "1BAD", "has space", ""):
            with self.assertRaises(ValueError, msg=bad):
                deploy_vars.save(bad, "x")

    def test_a_deployment_is_handed_its_saved_variables(self):
        deploy_vars.save("ADMIN_EMAIL", "a@b.example")
        env = deploy_vars.environment()
        self.assertEqual(env["ADMIN_EMAIL"], "a@b.example")
        self.assertNotIn("SUPABASE_URL", env)   # that comes from supabase_connect, not a saved variable


class SettingsRouteTests(SettingsCase):
    def test_settings_never_return_a_variable_value_and_it_cannot_be_written_around_the_route(self):
        httpd.write_settings({"deploy_env": {"SNEAKY": "value"}})
        self.assertEqual(config.setting("deploy_env", {}), {})
        deploy_vars.save("ADMIN_PASSWORD", "s3cret-value-here")
        shown = httpd.read_settings({})
        self.assertNotIn("s3cret-value-here", json.dumps(shown))
        self.assertNotIn("deploy_env", shown)


class RunEnvironmentTests(SettingsCase):
    def _command_env(self, stage: str) -> dict:
        deploy_vars.save("ADMIN_EMAIL", "a@b.example")
        seen = {}

        def fake_execute(tools, name, args):
            seen.update(tools.command_env)
            return "exit_code=0\nok"

        fake_session = mock.Mock(stage=stage, _agent=None)
        connected = {"SUPABASE_URL": "https://abcdefgh.supabase.co", "SUPABASE_ANON_KEY": "anon-key",
                    "SUPABASE_SERVICE_ROLE_KEY": "service-key"}
        with tempfile.TemporaryDirectory() as workspace, \
                mock.patch.object(session, "session_for", lambda project: fake_session), \
                mock.patch.object(config, "record_dir", lambda project: Path(workspace) / ".agentforge"), \
                mock.patch.object(session.WorkspaceTools, "execute", fake_execute), \
                mock.patch.object(supabase_connect, "env_for", lambda project: dict(connected)):
            tools = session.StudioTools(Path(workspace), None, lambda q: True, project=PROJECT,
                                        role_of=lambda: "developer")
            tools.execute("run_command", {"command": "echo"})
        return seen

    def test_every_stage_gets_the_projects_own_supabase_connection_but_only_deploy_and_build_get_saved_variables(self):
        env = self._command_env("srs")
        self.assertEqual(env["SUPABASE_URL"], "https://abcdefgh.supabase.co")
        self.assertNotIn("ADMIN_EMAIL", env)
        for stage in ("deploy", "build", "build-edit"):
            env = self._command_env(stage)
            self.assertEqual((env["ADMIN_EMAIL"], env["SUPABASE_URL"]),
                             ("a@b.example", "https://abcdefgh.supabase.co"), stage)

    def test_a_saved_variable_overrides_the_connected_project_at_deploy_time(self):
        deploy_vars.save("SUPABASE_URL", "https://a-different-project.supabase.co", secret=False)
        env = self._command_env("deploy")
        self.assertEqual(env["SUPABASE_URL"], "https://a-different-project.supabase.co")

    PRODUCTION = "mongodb+srv://u:p4ssw0rd-long@cluster0.ab1cd.mongodb.net/app?retryWrites=true&w=majority"
    # The saved string names the shared `app`, so a project gets databases named after itself (`build_databases`).
    BUILD = "mongodb+srv://u:p4ssw0rd-long@cluster0.ab1cd.mongodb.net/prj_deploy_vars_test_build?retryWrites=true&w=majority"
    TEST = "mongodb+srv://u:p4ssw0rd-long@cluster0.ab1cd.mongodb.net/prj_deploy_vars_test_test?retryWrites=true&w=majority"

    def setUp(self):
        super().setUp()
        deploy_vars._checked.clear()
        deploy_vars._noted.clear()
        self.told: list[dict] = []
        for patch in (mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                                        self.told.append({"project": project, "text": text, "title": title})
                                        if title == "MongoDB cluster not reachable" else None),     # not the command lines
                      mock.patch.object(bus, "log", lambda *a, **k: None)):
            patch.start()
            self.addCleanup(patch.stop)

    def connected(self, answers=True, why=""):
        config.save_settings({"deploy_mongodb_uri": self.PRODUCTION})
        patcher = mock.patch.object(deploy_vars, "cluster_answers", return_value=(answers, why))
        self.addCleanup(patcher.stop)
        return patcher.start()

    def test_a_builds_commands_get_databases_of_their_own_on_the_cluster_the_customer_connected(self):
        # Not a MongoDB on this computer, which may not exist, and not the database the deployed application will use.
        self.connected()
        for stage in ("build", "build-edit"):
            env = self._command_env(stage)
            self.assertEqual((env["MONGODB_URI"], env["TEST_MONGODB_URI"]), (self.BUILD, self.TEST), stage)
            self.assertEqual(env["ADMIN_EMAIL"], "a@b.example", stage)        # the other saved variables still arrive

    def test_the_stage_that_starts_the_preview_reads_the_database_the_seed_filled(self):
        self.connected()
        self.assertEqual(self._command_env("preview_start")["MONGODB_URI"], self.BUILD)

    def test_a_deployment_is_handed_the_database_the_build_ran_on_not_the_saved_string_as_it_stands(self):
        # So the deployed application finds the data the build's seed made.
        asked = self.connected()
        env = self._command_env("deploy")
        self.assertEqual(env["MONGODB_URI"], self.BUILD)
        self.assertNotEqual(env["MONGODB_URI"], self.PRODUCTION)
        self.assertNotIn("TEST_MONGODB_URI", env)                              # the unit tests' database is for the build only
        asked.assert_not_called()                                              # a deployment is handed it, not asked first

    def test_a_deployment_is_handed_it_even_when_the_cluster_does_not_answer_and_says_nothing_about_it_here(self):
        self.connected(answers=False, why="no answer")
        self.assertEqual(self._command_env("deploy")["MONGODB_URI"], self.BUILD)
        self.assertEqual(self.told, [])

    def test_what_looks_at_the_deployed_data_looks_at_the_database_the_build_made(self):
        from server_modules import cli_monitor

        self.connected()
        self.assertEqual(cli_monitor.mongodb_uri(PROJECT), self.BUILD)
        with mock.patch.object(supabase_connect, "env_for", lambda project: {}):
            env, hidden = cli_monitor._project_environment(PROJECT)           # noqa: SLF001 - the terminal's variables
        self.assertEqual(env["MONGODB_URI"], self.BUILD)
        self.assertIn(self.BUILD, hidden)
        rows = (ROOT / "server_modules" / "database_rows.py").read_text(encoding="utf-8")
        self.assertIn("cli_monitor.mongodb_uri(project)", rows)

    def test_the_studios_preview_of_what_was_built_reads_the_same_database_as_the_build(self):
        source = (ROOT / "server_modules" / "preview_runtime.py").read_text(encoding="utf-8")
        self.assertIn("**deploy_vars.environment(build=True, project=project)", source)

    def test_a_connection_string_the_customer_saved_by_name_reaches_the_build_as_it_is(self):
        self.connected()
        deploy_vars.save("MONGODB_URI", "mongodb+srv://u:p@their-own.ab1cd.mongodb.net/app", secret=True)
        deploy_vars.save("TEST_MONGODB_URI", "mongodb+srv://u:p@their-own.ab1cd.mongodb.net/app_test", secret=True)
        env = self._command_env("build")
        self.assertEqual((env["MONGODB_URI"], env["TEST_MONGODB_URI"]),
                         ("mongodb+srv://u:p@their-own.ab1cd.mongodb.net/app", "mongodb+srv://u:p@their-own.ab1cd.mongodb.net/app_test"))

    def test_with_no_cluster_connected_nothing_is_handed_over_and_nothing_is_checked(self):
        with mock.patch.object(deploy_vars, "cluster_answers") as asked:
            env = self._command_env("build")
        asked.assert_not_called()
        self.assertNotIn("MONGODB_URI", env)
        self.assertNotIn("TEST_MONGODB_URI", env)

    def test_a_cluster_that_does_not_answer_is_not_handed_over_and_the_customer_is_told_why_once(self):
        # A paused cluster has no address: every command would wait for it and fail.
        self.connected(answers=False, why="querySrv ENOTFOUND _mongodb._tcp.cluster0.ab1cd.mongodb.net")
        env = self._command_env("build")
        self.assertNotIn("MONGODB_URI", env)
        self.assertEqual(env["ADMIN_EMAIL"], "a@b.example")
        self.assertEqual(len(self.told), 1)
        self.assertEqual((self.told[0]["project"], self.told[0]["title"]), (PROJECT, "MongoDB cluster not reachable"))
        self.assertIn("ENOTFOUND", self.told[0]["text"])
        self.assertIn("resume it", self.told[0]["text"])
        self._command_env("build")
        self.assertEqual(len(self.told), 1)                                   # not on every command
        self.assertNotIn("p4ssw0rd", self.told[0]["text"])

    def test_the_customer_is_told_again_after_a_while_and_each_project_is_told_for_itself(self):
        self.connected(answers=False, why="no answer")
        deploy_vars.environment(build=True, project="prj_a")
        deploy_vars.environment(build=True, project="prj_b")
        self.assertEqual([row["project"] for row in self.told], ["prj_a", "prj_b"])
        deploy_vars._noted["prj_a"] -= deploy_vars.NOTE_SECONDS + 1
        deploy_vars.environment(build=True, project="prj_a")
        self.assertEqual(len(self.told), 3)


class BuildDatabaseTests(SettingsCase):
    def setUp(self):
        super().setUp()
        deploy_vars._checked.clear()

    def saved(self, uri):
        config.save_settings({"deploy_mongodb_uri": uri})

    def test_the_databases_are_named_after_the_one_the_saved_string_names(self):
        self.saved("mongodb+srv://u:p@c.mongodb.net/Hotel-Booking?retryWrites=true")
        self.assertEqual(deploy_vars.build_databases(),
                         ("mongodb+srv://u:p@c.mongodb.net/hotel_booking_build?retryWrites=true",
                          "mongodb+srv://u:p@c.mongodb.net/hotel_booking_test?retryWrites=true"))

    def test_a_string_that_names_no_database_takes_the_name_of_the_project(self):
        self.saved("mongodb+srv://u:p@c.mongodb.net/?retryWrites=true")
        with mock.patch("server_modules.store.get", return_value={"name": "Example Hotel"}):
            self.assertEqual(deploy_vars.build_databases("prj_x")[0], "mongodb+srv://u:p@c.mongodb.net/example_hotel_build?retryWrites=true")
        with mock.patch("server_modules.store.get", return_value=None):
            self.assertEqual(deploy_vars.build_databases("prj_x")[1], "mongodb+srv://u:p@c.mongodb.net/prj_x_test?retryWrites=true")
        self.assertEqual(deploy_vars.build_databases()[0], "mongodb+srv://u:p@c.mongodb.net/app_build?retryWrites=true")

    def test_the_test_database_always_ends_in_the_suffix_the_templates_require_and_credentials_and_options_are_kept(self):
        self.saved("mongodb://user:p%40ss%2Fword@h1.example.net:27017,h2.example.net:27017/shop?replicaSet=rs0&tls=true")
        build, test = deploy_vars.build_databases()
        self.assertTrue(test.split("?")[0].endswith("_test"))
        self.assertIn("user:p%40ss%2Fword@h1.example.net:27017,h2.example.net:27017/shop_build?replicaSet=rs0&tls=true", build)

    def test_nothing_connected_means_no_databases(self):
        self.assertEqual(deploy_vars.build_databases(), ("", ""))

    def test_whether_the_cluster_answers_is_asked_for_real_once_and_remembered_for_a_couple_of_minutes(self):
        from server_modules import mongo_check

        with mock.patch.object(mongo_check, "check", return_value={"ok": True, "message": "Connected and signed in."}) as asked:
            self.assertEqual(deploy_vars.cluster_answers("mongodb+srv://u:p@c.mongodb.net/app"), (True, "Connected and signed in."))
            self.assertEqual(deploy_vars.cluster_answers("mongodb+srv://u:p@c.mongodb.net/app")[0], True)
            self.assertEqual(asked.call_count, 1)
            stamp, ok, why = deploy_vars._checked["mongodb+srv://u:p@c.mongodb.net/app"]
            deploy_vars._checked["mongodb+srv://u:p@c.mongodb.net/app"] = (stamp - deploy_vars.BUILD_CHECK_SECONDS - 1, ok, why)
            deploy_vars.cluster_answers("mongodb+srv://u:p@c.mongodb.net/app")
            self.assertEqual(asked.call_count, 2)

    def test_a_refused_login_is_remembered_as_that_and_not_as_any_other_failure(self):
        from server_modules import mongo_check

        uri = "mongodb+srv://agentforge_app:old@c.mongodb.net/app"
        with mock.patch.object(mongo_check, "check", return_value={"ok": False, "stage": "auth", "message": "refused the password"}):
            self.assertEqual(deploy_vars.cluster_answers(uri), (False, "refused the password"))
        self.assertTrue(deploy_vars.refused_login(uri))
        other = "mongodb+srv://agentforge_app:old@d.mongodb.net/app"
        with mock.patch.object(mongo_check, "check", return_value={"ok": False, "stage": "network", "message": "no answer"}):
            deploy_vars.cluster_answers(other)
        self.assertFalse(deploy_vars.refused_login(other))
        self.assertFalse(deploy_vars.refused_login("mongodb+srv://never:seen@e.mongodb.net/app"))

    def test_a_cluster_that_refuses_or_a_check_that_cannot_run_is_not_an_answer_yes(self):
        from server_modules import mongo_check

        with mock.patch.object(mongo_check, "check", return_value={"ok": False, "message": "the cluster refused the password"}):
            self.assertEqual(deploy_vars.cluster_answers("mongodb+srv://u:p@a.mongodb.net/app"), (False, "the cluster refused the password"))
        with mock.patch.object(mongo_check, "check", side_effect=RuntimeError("node is not installed")):
            ok, why = deploy_vars.cluster_answers("mongodb+srv://u:p@b.mongodb.net/app")
        self.assertFalse(ok)
        self.assertIn("node is not installed", why)

    def test_what_a_build_was_handed_is_hidden_wherever_a_tool_might_print_it(self):
        self.saved("mongodb+srv://u:p4ssw0rd-long@c.mongodb.net/app")
        hidden = deploy_vars.secret_values()
        self.assertIn("mongodb+srv://u:p4ssw0rd-long@c.mongodb.net/app", hidden)
        self.assertIn("mongodb+srv://u:p4ssw0rd-long@c.mongodb.net/app_build", hidden)
        self.assertIn("p4ssw0rd-long", hidden)                                  # whatever name the database goes by


class ProjectDatabaseTests(SettingsCase):
    """Two projects on one cluster never share a database; the name a project got never changes afterwards."""

    CLUSTER = "mongodb+srv://u:p4ssw0rd-long@c.mongodb.net/{path}?retryWrites=true"

    def setUp(self):
        super().setUp()
        self.records: dict[str, dict] = {}
        self.updates: list[tuple[str, dict]] = []
        self.built: set[str] = set()
        folder = Path(self.temp.name)

        def record_dir(project):
            return folder / project / ".agentforge"

        def update(project, **patch):
            self.updates.append((project, patch))
            self.records[project].update(patch)

        for patch in (mock.patch("server_modules.store.get", lambda project: self.records.get(project)),
                      mock.patch("server_modules.store.update", update),
                      mock.patch.object(config, "record_dir", record_dir)):
            patch.start()
            self.addCleanup(patch.stop)

    def project(self, project, name):
        self.records[project] = {"id": project, "name": name}

    def build_report(self, project):
        report = Path(self.temp.name) / project / ".agentforge" / "build" / "report.json"
        report.parent.mkdir(parents=True)
        report.write_text("{}", encoding="utf-8")

    def database(self, project):
        return deploy_vars.build_databases(project)[0].split("?")[0].rsplit("/", 1)[-1]

    def test_projects_on_the_shared_app_database_each_get_one_named_after_themselves(self):
        config.save_settings({"deploy_mongodb_uri": self.CLUSTER.format(path="app")})
        self.project("prj_a", "Quick Notes")
        self.project("prj_b", "Pet Clinic")
        self.assertEqual((self.database("prj_a"), self.database("prj_b")), ("quick_notes_build", "pet_clinic_build"))
        self.assertEqual(deploy_vars.build_databases("prj_a")[1].split("?")[0].rsplit("/", 1)[-1], "quick_notes_test")

    def test_a_string_that_names_no_database_does_the_same(self):
        config.save_settings({"deploy_mongodb_uri": self.CLUSTER.format(path="")})
        self.project("prj_a", "Quick Notes")
        self.assertEqual(self.database("prj_a"), "quick_notes_build")

    def test_the_choice_is_kept_in_the_project_and_a_rename_never_moves_its_data(self):
        config.save_settings({"deploy_mongodb_uri": self.CLUSTER.format(path="app")})
        self.project("prj_a", "Quick Notes")
        self.assertEqual(self.database("prj_a"), "quick_notes_build")
        self.assertEqual(self.updates, [("prj_a", {"mongo_database": "quick_notes"})])
        self.records["prj_a"]["name"] = "Notes Pro"                                 # renamed in the studio afterwards
        self.assertEqual(self.database("prj_a"), "quick_notes_build")
        self.assertEqual(len(self.updates), 1)                                      # and it is not written again

    def test_a_project_already_built_on_the_shared_database_keeps_it_so_its_data_and_deployment_stay_where_they_are(self):
        config.save_settings({"deploy_mongodb_uri": self.CLUSTER.format(path="app")})
        self.project("prj_old", "Old Shop")
        self.build_report("prj_old")
        self.assertEqual(self.database("prj_old"), "app_build")
        self.assertEqual(self.updates, [("prj_old", {"mongo_database": "app"})])
        self.project("prj_new", "New Shop")
        self.assertEqual(self.database("prj_new"), "new_shop_build")                # a new one beside it does not mix with it

    def test_a_database_the_customer_named_in_their_string_is_theirs_and_used_as_it_always_was(self):
        config.save_settings({"deploy_mongodb_uri": self.CLUSTER.format(path="hotel")})
        self.project("prj_a", "Quick Notes")
        self.assertEqual(self.database("prj_a"), "hotel_build")
        self.assertEqual(self.updates, [])

    def test_no_project_and_no_record_still_give_a_name(self):
        config.save_settings({"deploy_mongodb_uri": self.CLUSTER.format(path="app")})
        self.assertEqual(self.database(""), "app_build")
        self.assertEqual(self.database("prj_unknown"), "prj_unknown_build")        # no record: named after its id, nothing written
        self.assertEqual(self.updates, [])

    def test_the_database_the_studio_reports_to_the_build_is_the_projects_own(self):
        from server_modules import mongo_connect

        config.save_settings({"deploy_mongodb_uri": self.CLUSTER.format(path="app")})
        self.project("prj_a", "Quick Notes")
        with mock.patch.object(mongo_connect, "cli_account", lambda: {}):
            found = mongo_connect.ensure_for_project("prj_a")
        self.assertEqual((found["status"], found["database"]), ("ready", "quick_notes_build"))


class MongoDatabaseUriTests(SettingsCase):
    """The production MongoDB connection string: never a loopback address, tried for real before a question
    accepts it, and exposed (as a set/hint, never the value) wherever the other saved credentials are."""

    def test_a_loopback_address_is_refused_a_real_one_is_not(self):
        for bad in ("mongodb://127.0.0.1:27017/app", "mongodb://localhost/app", "mongodb+srv://u:p@MyBox.local/app",
                    "mongodb://0.0.0.0:27017/app"):
            with self.assertRaises(ValueError, msg=bad):
                deploy_vars.check_database_uri(bad)
        self.assertEqual(deploy_vars.check_database_uri(""), "")
        real = "mongodb+srv://user:pass@cluster0.ab1cd.mongodb.net/app"
        self.assertEqual(deploy_vars.check_database_uri(real), real)
        with self.assertRaises(ValueError):
            deploy_vars.check_database_uri("postgres://user:pass@db.example.com/app")

    def test_allow_local_is_only_for_a_short_lived_build_test_database(self):
        self.assertEqual(deploy_vars.check_database_uri("mongodb://127.0.0.1:27017/app_test", allow_local=True),
                         "mongodb://127.0.0.1:27017/app_test")

    def test_mongodb_is_a_live_checked_variable(self):
        self.assertIn("mongodb", deploy_vars.CHECKS)

    def test_a_question_with_the_mongodb_check_tries_it_for_real_before_saving(self):
        from server_modules import mongo_check
        question = {"variable": "MONGODB_URI", "secret": True, "check": "mongodb"}
        with mock.patch.object(mongo_check, "check", return_value={"ok": False, "message": "the cluster refused the password"}):
            refusal = deploy_vars.accept(question, "mongodb+srv://u:wrong@cluster0.ab1cd.mongodb.net/app")
        self.assertIn("refused the password", refusal)
        self.assertEqual(deploy_vars.names(), [])
        with mock.patch.object(mongo_check, "check", return_value={"ok": True, "message": "Connected and signed in."}):
            ok = deploy_vars.accept(question, "mongodb+srv://u:right@cluster0.ab1cd.mongodb.net/app")
        self.assertEqual(ok, "")
        self.assertEqual(deploy_vars.names(), [{"name": "MONGODB_URI", "hint": "/app"}])

    def test_the_connected_cluster_reaches_a_deployment_as_mongodb_uri_on_the_database_the_build_used(self):
        config.save_settings({"deploy_mongodb_uri": "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app"})
        env = deploy_vars.environment()
        self.assertEqual(env["MONGODB_URI"], "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app_build")

    def test_a_saved_deploy_env_variable_of_the_same_name_is_not_overridden(self):
        config.save_settings({"deploy_mongodb_uri": "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app"})
        deploy_vars.save("MONGODB_URI", "mongodb+srv://u:p@a-different-cluster.ab1cd.mongodb.net/app", secret=True)
        self.assertEqual(deploy_vars.environment()["MONGODB_URI"],
                         "mongodb+srv://u:p@a-different-cluster.ab1cd.mongodb.net/app")

    def test_settings_refuses_a_loopback_production_uri_and_keeps_a_real_one(self):
        with self.assertRaises(ValueError):
            httpd.write_settings({"deploy_mongodb_uri": "mongodb://127.0.0.1:27017/app"})
        self.assertEqual(config.setting("deploy_mongodb_uri", ""), "")
        httpd.write_settings({"deploy_mongodb_uri": "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app"})
        self.assertEqual(config.setting("deploy_mongodb_uri", ""), "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app")

    def test_settings_expose_only_whether_it_is_set_and_a_hint_never_the_value(self):
        httpd.write_settings({"deploy_mongodb_uri": "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app"})
        shown = httpd.read_settings({})
        self.assertTrue(shown["deploy"]["deploy_mongodb_uri_set"])
        self.assertEqual(shown["deploy"]["deploy_mongodb_uri_hint"], "/app")
        self.assertNotIn("cluster0", json.dumps(shown))

    def test_the_test_connection_route_tries_a_typed_value_without_saving_it(self):
        from server_modules import mongo_check, routes_deploy
        with mock.patch.object(mongo_check, "check", return_value={"ok": True, "message": "Connected and signed in."}) as checked:
            answer = routes_deploy.mongodb_status({"uri": "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app"})
        self.assertEqual((answer["connected"], answer["using_saved"]), (True, False))
        checked.assert_called_once_with("mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app")
        self.assertEqual(config.setting("deploy_mongodb_uri", ""), "")        # testing never saves

    def test_the_test_connection_route_with_no_uri_tries_the_saved_one(self):
        from server_modules import mongo_check, routes_deploy
        httpd.write_settings({"deploy_mongodb_uri": "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app"})
        with mock.patch.object(mongo_check, "check", return_value={"ok": False, "message": "refused"}):
            answer = routes_deploy.mongodb_status({"uri": ""})
        self.assertEqual((answer["connected"], answer["using_saved"], answer["message"]), (False, True, "refused"))

    def test_a_check_that_cannot_run_is_reported_not_raised(self):
        from server_modules import mongo_check, routes_deploy
        with mock.patch.object(mongo_check, "check", side_effect=RuntimeError("node is not installed")):
            answer = routes_deploy.mongodb_status({"uri": "mongodb+srv://u:p@cluster0.ab1cd.mongodb.net/app"})
        self.assertFalse(answer["connected"])
        self.assertIn("node is not installed", answer["message"])


class ValueQuestionTests(SettingsCase):
    """A question can ask for a value: it goes to a private box, is saved by name, and the model is only told it is saved."""

    def setUp(self):
        super().setUp()
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        bus._pending_decisions.clear()
        self.addCleanup(forget_project, PROJECT)

    def test_a_question_names_its_variable_and_a_bad_name_or_check_is_sent_back(self):
        asked = changes.check_question({"question": "Which password?", "variable": "ADMIN_PASSWORD"}, True)
        self.assertEqual((asked["variable"], asked["secret"], asked["check"]), ("ADMIN_PASSWORD", True, ""))
        with self.assertRaises(ValueError):
            changes.check_question({"question": "?", "variable": "path"}, True)
        with self.assertRaises(ValueError):
            # No live check is offered anymore (there is no `deploy_vars.CHECKS` entry left).
            changes.check_question({"question": "?", "variable": "DB", "check": "sql"}, True)
        self.assertNotIn("variable", changes.check_question({"question": "Region?"}, True))

    def _ask(self, **extra):
        return bus.ask(PROJECT, "question", "Which password?", options=[{"id": "1", "label": "Generate one"}],
                       variable="ADMIN_PASSWORD", secret=True, change_id="chg-x", **extra)

    def test_the_value_is_saved_and_the_model_is_told_only_that_it_is_saved(self):
        decision = self._ask()
        with mock.patch.object(httpd.changes, "answer", return_value={"ok": True}) as answer:
            result = httpd.decide({"id": decision, "decision": "answer", "reply": "Str0ng-Pass-Word!"})
        self.assertTrue(result["ok"])
        self.assertEqual(config.setting("deploy_env")["ADMIN_PASSWORD"], "Str0ng-Pass-Word!")
        told = answer.call_args.args[2]
        self.assertIn("ADMIN_PASSWORD", told)
        self.assertNotIn("Str0ng-Pass-Word!", json.dumps(self.events) + told)      # not in the stream, not to the model
        self.assertEqual(bus.pending_decisions(), [])

    def test_an_option_is_an_answer_without_a_value(self):
        decision = self._ask()
        with mock.patch.object(httpd.changes, "answer", return_value={"ok": True}) as answer:
            httpd.decide({"id": decision, "decision": "answer", "reply": "Generate one", "via": "option"})
        self.assertEqual(answer.call_args.args[2], "Generate one")
        self.assertNotIn("deploy_env", {k for k, v in config.settings().items() if v})

    def test_a_line_typed_in_the_chat_does_not_answer_a_question_that_wants_a_private_value(self):
        waiting = {"id": "chg-x", "status": "asking", "question": {"question": "?", "variable": "ADMIN_PASSWORD"}}
        with mock.patch.object(changes, "active", return_value=waiting), mock.patch.object(changes, "answer") as answer:
            result = changes.submit(PROJECT, "hunter2")
        answer.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(any("private" in (e.get("text") or "") for e in self.events))


class ValueQuestionThroughTheFlowTests(SettingsCase):
    """The whole path, with nothing about the flow mocked: ask for a value, take it, plan again."""

    def setUp(self):
        super().setUp()
        import threading

        from tests.test_deploy_flow import DeployFlowCase, plan

        self.case = DeployFlowCase("setUp")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.plan, self.threading = plan, threading
        self.case.session.replies = [
            {"kind": "question", "question": "Which password should the first admin have?", "variable": "ADMIN_PASSWORD",
             "secret": True, "options": [{"label": "I will type it"}, {"label": "Write one to a file for me"}]},
            plan()]

    def test_a_value_typed_in_the_box_is_saved_and_the_next_plan_is_told_only_that_it_is_saved(self):
        started = self.case.start()
        self.assertEqual(changes.active(PROJECT)["status"], "asking")
        ask = [d for d in bus.pending_decisions() if d.get("variable")][0]
        self.assertEqual((ask["variable"], ask["secret"]), ("ADMIN_PASSWORD", True))
        answered = httpd.decide({"id": ask["id"], "decision": "answer", "reply": "Str0ng-Pass-Word!"})
        self.assertTrue(answered["ok"])
        self.case.settle(started["change"])
        self.assertEqual(config.setting("deploy_env")["ADMIN_PASSWORD"], "Str0ng-Pass-Word!")
        self.assertEqual(changes.active(PROJECT)["status"], "proposed")                 # planned on, not stuck
        second = self.case.session.prompts[1]
        self.assertIn("ADMIN_PASSWORD", second)
        self.assertNotIn("Str0ng-Pass-Word!", second)                                    # the model never saw it

    def test_choosing_an_option_instead_of_a_value_carries_on_too(self):
        started = self.case.start()
        ask = [d for d in bus.pending_decisions() if d.get("variable")][0]
        answered = httpd.decide({"id": ask["id"], "decision": "answer", "reply": "Write one to a file for me",
                                 "via": "option"})
        self.assertTrue(answered["ok"])
        self.case.settle(started["change"])
        self.assertEqual(changes.active(PROJECT)["status"], "proposed")
        self.assertIn("Write one to a file for me", self.case.session.prompts[1])
        self.assertNotIn("ADMIN_PASSWORD", config.setting("deploy_env", {}))


class SecretsGuardTests(unittest.TestCase):
    def test_a_connection_string_with_a_password_or_a_key_is_a_secret(self):
        for text in (f"use this url {SECRET_URI}", "postgres://admin:Str0ngPass1@db.example.com:5432/app",
                     "token ghp_" + "a1B2c3D4" * 5, "AKIAABCDEFGHIJKLMNOP", "-----BEGIN RSA PRIVATE KEY-----",
                     "sk-" + "abcd1234" * 4):
            self.assertTrue(secrets_guard.looks_secret(text), text)

    def test_ordinary_messages_and_placeholders_are_not(self):
        for text in ("make the repository public", "connect to postgres://localhost:5432/app",
                     "postgres://user:password@db.example.com/db", "https://example.com/docs",
                     "the password field must be hashed", "postgres://<user>:<password>@host/db"):
            self.assertFalse(secrets_guard.looks_secret(text), text)

    def test_the_refusal_is_the_packs_and_says_where_to_save_it(self):
        text = secrets_guard.refusal(SECRET_URI)
        self.assertIn("Deployment variables", text)
        self.assertEqual(secrets_guard.refusal("hello"), "")


class DatabaseQuestionTests(SettingsCase):
    """The database connection is the studio's to provide: nobody is asked for a connection string, in a plan or in a run."""

    URI = "mongodb+srv://u:p4ssw0rd-long@cluster0.ab1cd.mongodb.net/?retryWrites=true&w=majority"

    def setUp(self):
        super().setUp()
        from server_modules import mongo_connect

        self.atlas = False
        for patch in (mock.patch.object(mongo_connect, "credentials_saved", lambda: False),
                      mock.patch.object(mongo_connect, "cli_account", lambda: {"account": "me@example.com"} if self.atlas else {})):
            patch.start()
            self.addCleanup(patch.stop)

    def test_what_asks_for_the_connection_is_told_from_what_does_not(self):
        for asked in ({"question": "What is your MongoDB connection string?"},
                      {"question": "Where should the data live?", "why": "I need the Mongo URI for the cluster"},
                      {"question": "Paste the connection URL.", "why": "the database address is missing"},
                      {"question": "Which?", "variable": "mongodb_uri"}, {"question": "Which?", "variable": "DATABASE_URL"},
                      {"question": "Which?", "check": "mongodb"}):
            self.assertTrue(deploy_vars.asks_for_database(asked), asked)
        for fine in ({"question": "Which region should the application and the cluster both run in?"},
                     {"question": "Should the production database start empty or with the demo data?"},
                     {"question": "What is the admin's first password?", "variable": "ADMIN_PASSWORD"},
                     {"question": "Which payment provider should checkout use?"}):
            self.assertFalse(deploy_vars.asks_for_database(fine), fine)

    def test_where_the_connection_stands(self):
        self.assertEqual(deploy_vars.database_state(), {"saved": False, "atlas": False})
        self.atlas = True
        self.assertEqual(deploy_vars.database_state(), {"saved": False, "atlas": True})
        config.save_settings({"deploy_mongodb_uri": self.URI})
        self.assertEqual(deploy_vars.database_state(), {"saved": True, "atlas": True})
        config.save_settings({"deploy_mongodb_uri": ""})
        deploy_vars.save("MONGODB_URI", self.URI)                       # saved by name counts as saved
        self.assertTrue(deploy_vars.database_state()["saved"])

    def test_a_question_for_it_is_not_asked_once_a_string_is_saved_or_an_account_is_signed_in(self):
        ask = {"question": "What is your MongoDB connection string?", "variable": "MONGODB_URI"}
        self.assertEqual(deploy_vars.provided(ask), "")                  # nothing connected: it may be asked
        config.save_settings({"deploy_mongodb_uri": self.URI})
        held = deploy_vars.provided(ask)
        self.assertIn("MONGODB_URI", held)
        self.assertIn("not the customer's to give", held)
        config.save_settings({"deploy_mongodb_uri": ""})
        self.atlas = True
        self.assertIn("not the customer's to give", deploy_vars.provided(ask))

    def test_a_build_never_asks_for_it_whatever_is_connected(self):
        ask = {"question": "Paste your MongoDB connection string"}
        self.assertEqual(deploy_vars.provided(ask), "")
        self.assertIn("not the customer's to give", deploy_vars.provided(ask, always=True))

    def test_any_other_question_is_left_alone(self):
        config.save_settings({"deploy_mongodb_uri": self.URI})
        for fine in ({"question": "Which region should the cluster run in?"}, {"question": "What is the admin's email?",
                                                                               "variable": "ADMIN_EMAIL"}):
            self.assertEqual(deploy_vars.provided(fine, always=True), "")

    def test_the_planner_that_asks_for_it_is_sent_back_to_plan_without_it(self):
        config.save_settings({"deploy_mongodb_uri": self.URI})
        with self.assertRaisesRegex(ValueError, "not the customer's to give"):
            changes.check_question({"question": "What is the MongoDB connection string?", "why": "to deploy", "options": [],
                                    "variable": "MONGODB_URI", "secret": True, "check": "mongodb"}, True)
        asked = changes.check_question({"question": "Which region should it run in?", "why": "latency",
                                        "options": [{"label": "US East"}]}, True)
        self.assertEqual(asked["question"], "Which region should it run in?")

    def test_with_nothing_connected_a_planner_could_still_ask(self):
        # The deployment is refused before it plans when nothing is connected (`deploy._require_mongodb`), so this only keeps
        # the check from turning a question into a loop for someone who has no way to connect.
        asked = changes.check_question({"question": "What is the MongoDB connection string?", "why": "to deploy", "options": [],
                                        "variable": "MONGODB_URI", "secret": True, "check": "mongodb"}, True)
        self.assertEqual(asked["variable"], "MONGODB_URI")

    def test_the_model_is_told_it_in_words_that_name_the_variable(self):
        text = (ROOT / "prompts" / "changes" / "database-provided.md").read_text(encoding="utf-8")
        for needle in ("MONGODB_URI", "Settings", "localhost"):
            self.assertIn(needle, text)


class ChatRefusesSecretsTests(unittest.TestCase):
    def setUp(self):
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        bus._pending_decisions.clear()
        self.addCleanup(forget_project, PROJECT)

    def test_a_typed_message_holding_a_secret_is_not_planned_or_kept(self):
        with mock.patch.object(runs.changes, "submit") as submit:
            answer = runs.agent_update({"project": PROJECT, "prompt": f"here it is {SECRET_URI}"})
        submit.assert_not_called()
        self.assertFalse(answer["ok"])
        self.assertTrue(any("Deployment variables" in (e.get("text") or "") for e in self.events))
        self.assertNotIn("Xy7Pq2Lm9Kd4", json.dumps(self.events))     # not echoed back into the stream

    def test_an_answer_holding_a_secret_leaves_the_question_open(self):
        decision = bus.ask(PROJECT, "question", "Which database?", options=[{"id": "1", "label": "Atlas"}])
        answer = httpd.decide({"id": decision, "decision": "answer", "reply": SECRET_URI})
        self.assertFalse(answer["ok"])
        self.assertEqual([d["id"] for d in bus.pending_decisions()], [decision])      # still waiting for its answer
        self.assertNotIn("Xy7Pq2Lm9Kd4", json.dumps(self.events))


if __name__ == "__main__":
    unittest.main()
