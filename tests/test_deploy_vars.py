"""What only the customer can give a deployment stays out of the chat and reaches only the deployment."""
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

from server_modules import bus, changes, config, deploy_vars, httpd, mongo_check, routes_deploy, runs, secrets_guard, session  # noqa: E402

PROJECT = "prj_deploy_vars_test"
ATLAS = "mongodb+srv://someone:Xy7Pq2Lm9Kd4@cluster0.example.mongodb.net/?appName=Cluster0"


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

    def test_a_deployment_is_handed_its_variables_and_the_production_database(self):
        deploy_vars.save("ADMIN_EMAIL", "a@b.example")
        config.save_settings({"deploy_mongodb_uri": ATLAS, "mongodb_uri": "mongodb://127.0.0.1:27017/studio"})
        env = deploy_vars.environment()
        self.assertEqual(env["ADMIN_EMAIL"], "a@b.example")
        self.assertEqual(env["MONGODB_URI"], ATLAS)                 # the production one, not the studio's own

    def test_the_production_database_must_be_reachable_from_a_host(self):
        self.assertEqual(deploy_vars.check_database_uri(ATLAS), ATLAS)
        for bad in ("mongodb://localhost:27017/app", "mongodb://127.0.0.1/app", "postgres://x/y", "http://x"):
            with self.assertRaises(ValueError, msg=bad):
                deploy_vars.check_database_uri(bad)
        self.assertEqual(deploy_vars.check_database_uri(""), "")     # clearing it is allowed


class SettingsRouteTests(SettingsCase):
    def test_saving_a_local_production_database_is_refused_and_a_remote_one_is_kept_without_being_shown(self):
        with self.assertRaises(ValueError):
            httpd.write_settings({"deploy_mongodb_uri": "mongodb://localhost:27017/app"})
        shown = httpd.write_settings({"deploy_mongodb_uri": ATLAS})
        self.assertTrue(shown["deploy"]["mongodb_uri_set"])
        self.assertEqual(shown["deploy"]["mongodb_uri_hint"], ATLAS[-4:])
        self.assertNotIn("Xy7Pq2Lm9Kd4", json.dumps(shown))

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
        config.save_settings({"deploy_mongodb_uri": ATLAS, "mongodb_uri": "mongodb://127.0.0.1:27017/studio"})
        seen = {}

        def fake_execute(tools, name, args):
            seen.update(tools.command_env)
            return "exit_code=0\nok"

        fake_session = mock.Mock(stage=stage, _agent=None)
        with tempfile.TemporaryDirectory() as workspace, \
                mock.patch.object(session, "session_for", lambda project: fake_session), \
                mock.patch.object(config, "record_dir", lambda project: Path(workspace) / ".agentforge"), \
                mock.patch.object(session.WorkspaceTools, "execute", fake_execute):
            tools = session.StudioTools(Path(workspace), None, lambda q: True, project=PROJECT,
                                        role_of=lambda: "developer")
            tools.execute("run_command", {"command": "echo"})
        return seen

    def test_only_a_deployment_run_is_handed_the_saved_variables_and_the_production_database(self):
        env = self._command_env("deploy")
        self.assertEqual((env["ADMIN_EMAIL"], env["MONGODB_URI"]), ("a@b.example", ATLAS))
        env = self._command_env("build")
        self.assertNotIn("ADMIN_EMAIL", env)
        self.assertEqual(env["MONGODB_URI"], "mongodb://127.0.0.1:27017/studio")     # the studio's own, as before


class ConnectionCheckTests(SettingsCase):
    def test_the_string_goes_in_the_environment_and_nothing_secret_comes_back(self):
        leaked = "mongodb+srv://someone:Xy7Pq2Lm9Kd4@cluster0.example.mongodb.net/app"
        answer = mock.Mock(stdout=json.dumps({"ok": False, "stage": "connect",
                                              "message": f"failed for {leaked} with Xy7Pq2Lm9Kd4"}) + chr(10), stderr="")
        with mock.patch.object(mongo_check.subprocess, "run", return_value=answer) as run:
            result = mongo_check.check(leaked)
        command, options = run.call_args.args[0], run.call_args.kwargs
        self.assertNotIn(leaked, " ".join(command))                   # not on the command line
        self.assertEqual(options["env"]["CHECK_URI"], leaked)          # in the environment
        self.assertNotIn("Xy7Pq2Lm9Kd4", json.dumps(result))

    def test_a_local_address_is_refused_before_anything_is_run_and_an_empty_box_means_the_saved_one(self):
        with mock.patch.object(mongo_check.subprocess, "run") as run:
            self.assertEqual(mongo_check.check("mongodb://localhost:27017/app")["stage"], "address")
            self.assertEqual(mongo_check.check("")["stage"], "empty")                # nothing saved either
        run.assert_not_called()
        config.save_settings({"deploy_mongodb_uri": ATLAS})
        answer = mock.Mock(stdout=json.dumps({"ok": True, "verified": True, "message": "Connected and signed in."}), stderr="")
        with mock.patch.object(mongo_check.subprocess, "run", return_value=answer) as run:
            self.assertTrue(routes_deploy.dispatch("POST", "/mongodb/check", {"uri": ""})["ok"])
        self.assertEqual(run.call_args.kwargs["env"]["CHECK_URI"], ATLAS)

    def test_a_short_password_does_not_garble_the_words_around_it(self):
        self.assertEqual(mongo_check._scrub("the computer", "mongodb://u:p@host/db"), "the computer")

    @unittest.skipUnless(mongo_check._driver_base(), "no built project has the MongoDB driver yet")
    def test_against_a_real_server_it_connects_and_tells_a_wrong_password_from_a_missing_server(self):
        import socket
        try:
            socket.create_connection(("127.0.0.1", 27017), timeout=0.5).close()
        except OSError:
            self.skipTest("no MongoDB on localhost:27017")
        self.assertEqual(mongo_check.check("mongodb://127.0.0.1:27017/check_test", allow_local=True)["stage"], "ping")
        self.assertEqual(mongo_check.check("mongodb://a:wrongpass@127.0.0.1:27017/check_test", allow_local=True)["stage"], "auth")
        self.assertEqual(mongo_check.check("mongodb://a:b@127.0.0.1:1/x", allow_local=True)["stage"], "network")


class ValueQuestionTests(SettingsCase):
    """A question can ask for a value: it goes to a private box, is saved by name, and the model is only told it is saved."""

    def setUp(self):
        super().setUp()
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        bus._pending_decisions.clear()
        self.addCleanup(bus.forget, PROJECT)

    def test_a_question_names_its_variable_and_a_bad_name_or_check_is_sent_back(self):
        asked = changes.check_question({"question": "Which password?", "variable": "ADMIN_PASSWORD"}, True)
        self.assertEqual((asked["variable"], asked["secret"], asked["check"]), ("ADMIN_PASSWORD", True, ""))
        with self.assertRaises(ValueError):
            changes.check_question({"question": "?", "variable": "path"}, True)
        with self.assertRaises(ValueError):
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

    def test_a_database_string_that_does_not_connect_is_refused_with_the_reason_and_the_question_stays(self):
        decision = bus.ask(PROJECT, "question", "Where is the database?", variable="MONGODB_URI", secret=True,
                           check="mongodb", change_id="chg-x")
        bad = {"ok": False, "stage": "auth", "message": "The cluster answered but refused the username or password."}
        with mock.patch.object(mongo_check, "check", return_value=bad):
            result = httpd.decide({"id": decision, "decision": "answer", "reply": ATLAS})
        self.assertFalse(result["ok"])
        self.assertIn("refused the username", result["detail"])
        self.assertEqual([d["id"] for d in bus.pending_decisions()], [decision])
        self.assertNotIn("MONGODB_URI", config.setting("deploy_env", {}))
        good = {"ok": True, "verified": True, "message": "Connected and signed in."}
        with mock.patch.object(mongo_check, "check", return_value=good), \
                mock.patch.object(httpd.changes, "answer", return_value={"ok": True}):
            self.assertTrue(httpd.decide({"id": decision, "decision": "answer", "reply": ATLAS})["ok"])
        self.assertEqual(config.setting("deploy_env")["MONGODB_URI"], ATLAS)

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
        for text in (f"use this url {ATLAS}", "mongodb://admin:Str0ngPass1@db.example.com:27017/app",
                     "token ghp_" + "a1B2c3D4" * 5, "AKIAABCDEFGHIJKLMNOP", "-----BEGIN RSA PRIVATE KEY-----",
                     "sk-" + "abcd1234" * 4):
            self.assertTrue(secrets_guard.looks_secret(text), text)

    def test_ordinary_messages_and_placeholders_are_not(self):
        for text in ("make the repository public", "connect to mongodb://localhost:27017/app",
                     "mongodb+srv://user:password@cluster.mongodb.net/db", "https://example.com/docs",
                     "the password field must be hashed", "mongodb+srv://<user>:<password>@cluster/db"):
            self.assertFalse(secrets_guard.looks_secret(text), text)

    def test_the_refusal_is_the_packs_and_says_where_to_save_it(self):
        text = secrets_guard.refusal(ATLAS)
        self.assertIn("Deployment variables", text)
        self.assertEqual(secrets_guard.refusal("hello"), "")


class ChatRefusesSecretsTests(unittest.TestCase):
    def setUp(self):
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        bus._pending_decisions.clear()
        self.addCleanup(bus.forget, PROJECT)

    def test_a_typed_message_holding_a_secret_is_not_planned_or_kept(self):
        with mock.patch.object(runs.changes, "submit") as submit:
            answer = runs.agent_update({"project": PROJECT, "prompt": f"here it is {ATLAS}"})
        submit.assert_not_called()
        self.assertFalse(answer["ok"])
        self.assertTrue(any("Deployment variables" in (e.get("text") or "") for e in self.events))
        self.assertNotIn("Xy7Pq2Lm9Kd4", json.dumps(self.events))     # not echoed back into the stream

    def test_an_answer_holding_a_secret_leaves_the_question_open(self):
        decision = bus.ask(PROJECT, "question", "Which database?", options=[{"id": "1", "label": "Atlas"}])
        answer = httpd.decide({"id": decision, "decision": "answer", "reply": ATLAS})
        self.assertFalse(answer["ok"])
        self.assertEqual([d["id"] for d in bus.pending_decisions()], [decision])      # still waiting for its answer
        self.assertNotIn("Xy7Pq2Lm9Kd4", json.dumps(self.events))


if __name__ == "__main__":
    unittest.main()
