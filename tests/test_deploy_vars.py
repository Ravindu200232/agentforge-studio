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

from server_modules import bus, changes, config, deploy_vars, httpd, runs, secrets_guard, session, supabase_connect  # noqa: E402

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

    def test_every_stage_gets_the_projects_own_supabase_connection_but_only_deploy_gets_saved_variables(self):
        env = self._command_env("build")
        self.assertEqual(env["SUPABASE_URL"], "https://abcdefgh.supabase.co")
        self.assertNotIn("ADMIN_EMAIL", env)
        env = self._command_env("deploy")
        self.assertEqual((env["ADMIN_EMAIL"], env["SUPABASE_URL"]),
                         ("a@b.example", "https://abcdefgh.supabase.co"))

    def test_a_saved_variable_overrides_the_connected_project_at_deploy_time(self):
        deploy_vars.save("SUPABASE_URL", "https://a-different-project.supabase.co", secret=False)
        env = self._command_env("deploy")
        self.assertEqual(env["SUPABASE_URL"], "https://a-different-project.supabase.co")


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


class ChatRefusesSecretsTests(unittest.TestCase):
    def setUp(self):
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        bus._pending_decisions.clear()
        self.addCleanup(bus.forget, PROJECT)

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
