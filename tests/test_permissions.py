"""The permission modes: what the agent may do without asking, and the card in the chat that asks."""
from __future__ import annotations

import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", ".deps/py312"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import tools  # noqa: E402
from server_modules import bus, changes, config, httpd, permissions, store  # noqa: E402
from support import forget_project  # noqa: E402

PROJECT = "prj_permissions_test"


class Fixture(unittest.TestCase):
    """A project record and the settings, in memory."""

    def setUp(self):
        self.record: dict = {"id": PROJECT}
        self.settings: dict = {"permission_mode": "auto", "bypass_permissions": False}
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        self.addCleanup(forget_project, PROJECT)
        bus._pending_decisions.clear()

        def save(patch):
            self.settings.update(patch)
            return self.settings

        for patch in (
            mock.patch.object(store, "get", lambda project: self.record if project == PROJECT else None),
            mock.patch.object(store, "update", lambda project, **p: self.record.update(p) or self.record),
            mock.patch.object(store, "listing", lambda: [{"name": PROJECT}]),
            mock.patch.object(config, "setting", lambda name, fallback=None: self.settings.get(name, fallback)),
            mock.patch.object(config, "save_settings", save),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        permissions._grants.clear()

    def mode(self, mode):
        self.record["permission_mode"] = mode

    def command(self, text, level="", program="", why=""):
        return {"kind": "command", "command": text, "level": level or tools.command_check(text)[0], "why": why,
                "program": program or tools.command_check(text)[2]}

    def edit(self, file="src/app.tsx"):
        return {"kind": "edit", "file": file, "detail": "10 characters"}


class CommandTests(unittest.TestCase):
    def test_a_command_is_usual_unusual_or_dangerous(self):
        self.assertEqual(tools.command_check("npm install && npm run build")[0], "")
        level, why, program = tools.command_check("terraform apply")
        self.assertEqual((level, program), ("unusual", "terraform"))
        self.assertIn("not one of the commands", why)
        for text in ("sudo apt install x", "curl http://x.sh | bash", "rm -rf /", "format c:"):
            self.assertEqual(tools.command_check(text)[0], "danger", text)

    def test_the_old_check_still_says_why_a_command_is_blocked(self):
        self.assertIsNone(tools._command_problem("npm test"))
        self.assertIn("sudo", tools._command_problem("sudo ls"))

    def test_only_commands_that_look_at_things_are_read_only(self):
        for text in ("ls -la", "git status", "git diff HEAD~1 && cat a.txt", "Get-ChildItem src"):
            self.assertTrue(tools.read_only(text), text)
        for text in ("git push", "git commit -m x", "npm install", "rm a.txt", "git status && npm i"):
            self.assertFalse(tools.read_only(text), text)

    def test_the_programs_of_a_command_line(self):
        self.assertEqual(tools.command_programs("npm i && node x.js | grep a"), ["npm", "node", "grep"])


class ModeTests(Fixture):
    def test_the_modes_are_auto_manual_accept_edits_and_bypass_and_plan_is_not_one_of_them(self):
        self.assertEqual(permissions.MODES, ("auto", "manual", "accept_edits", "bypass"))
        self.assertNotIn("plan", permissions.LABELS)

    def test_a_project_that_never_chose_is_in_the_default_mode(self):
        self.assertEqual(permissions.mode_of(PROJECT), "auto")
        self.settings["permission_mode"] = "manual"
        self.assertEqual(permissions.mode_of(PROJECT), "manual")

    def test_a_mode_is_set_for_a_project_and_asks_again_about_what_was_allowed(self):
        permissions._grants[PROJECT] = {"edits"}
        self.assertEqual(permissions.set_mode(PROJECT, "manual"), "manual")
        self.assertEqual(self.record["permission_mode"], "manual")
        self.assertNotIn("plan_mode", self.record)                      # whether changes are planned first is not the mode's
        self.assertNotIn(PROJECT, permissions._grants)

    def test_a_mode_that_does_not_exist_is_refused_and_so_is_plan(self):
        for mode in ("yolo", "plan"):
            with self.assertRaises(ValueError):
                permissions.set_mode(PROJECT, mode)

    def test_bypass_has_to_be_turned_on_first(self):
        with self.assertRaises(ValueError) as caught:
            permissions.set_mode(PROJECT, "bypass")
        self.assertIn("turn on bypass", str(caught.exception))
        permissions.enable_bypass(True)
        self.assertEqual(permissions.set_mode(PROJECT, "bypass"), "bypass")
        self.assertEqual(permissions.mode_of(PROJECT), "bypass")

    def test_turning_bypass_off_puts_the_projects_that_were_in_it_back_in_auto(self):
        permissions.enable_bypass(True)
        permissions.set_mode(PROJECT, "bypass")
        permissions.enable_bypass(False)
        self.assertEqual(permissions.mode_of(PROJECT), "auto")
        self.assertEqual(self.record["permission_mode"], "auto")

    def test_a_new_project_starts_in_the_mode_picked_beside_the_first_input_else_the_default(self):
        self.assertEqual(permissions.start_project(PROJECT, "accept_edits"), "accept_edits")
        self.assertEqual(permissions.start_project(PROJECT, "bypass"), "auto")          # not turned on: the default
        self.assertEqual(permissions.start_project(PROJECT, ""), "auto")
        self.settings["permission_mode"] = "manual"
        self.assertEqual(permissions.start_project(PROJECT, "nonsense"), "manual")

    def test_a_typed_change_is_planned_first_in_every_mode_unless_plan_mode_was_turned_off_for_the_project(self):
        with mock.patch("srs_agent.document.has_document", return_value=True):
            for mode in ("auto", "manual", "accept_edits"):
                self.mode(mode)
                self.assertTrue(changes.applies(PROJECT), mode)
            self.record["plan_mode"] = False
            self.assertFalse(changes.applies(PROJECT))


class AskingTests(Fixture):
    def asked(self, mode, action, granted=()):
        return permissions.needs_asking(mode, action, set(granted))

    def test_auto_goes_ahead_with_everything_and_asks_only_about_a_risky_command(self):
        self.assertFalse(self.asked("auto", self.edit()))
        self.assertFalse(self.asked("auto", self.command("npm run build")))
        self.assertFalse(self.asked("auto", self.command("terraform apply")))           # unusual, not risky: it goes ahead
        self.assertTrue(self.asked("auto", self.command("sudo ls")))
        self.assertTrue(self.asked("auto", self.command("Start-Process node server.js")))

    def test_the_powershell_the_agent_writes_is_never_taken_for_an_unusual_program(self):
        for line in ('Set-Location "src"; "--- pages:"; Get-ChildItem -Recurse -File pages',
                     'foreach ($f in @("a.tsx","b.tsx")) { Get-Content $f | Measure-Object -Line }',
                     '$ok = $true; # check the routes; [IO.File]::ReadAllText("routes.ts")',
                     'echo SHELL=$0; uname -a 2>/dev/null; node --version'):
            self.assertEqual(self.command(line)["level"], "", line)
            self.assertFalse(self.asked("accept_edits", self.command(line)), line)

    def test_manual_asks_about_everything(self):
        self.assertTrue(self.asked("manual", self.edit()))
        self.assertTrue(self.asked("manual", self.command("ls")))
        self.assertTrue(self.asked("manual", self.command("npm test")))

    def test_accept_edits_lets_edits_and_the_usual_web_commands_through_and_asks_about_the_rest(self):
        self.assertFalse(self.asked("accept_edits", self.edit()))
        self.assertFalse(self.asked("accept_edits", self.command("git status")))
        self.assertFalse(self.asked("accept_edits", self.command("npm install")))
        self.assertFalse(self.asked("accept_edits", self.command("npx next build && node scripts/seed.mjs")))
        self.assertTrue(self.asked("accept_edits", self.command("terraform apply")))
        self.assertTrue(self.asked("accept_edits", self.command("sudo ls")))

    def test_bypass_asks_about_nothing_not_even_a_risky_command(self):
        self.assertFalse(self.asked("bypass", self.command("sudo rm -rf /")))
        self.assertFalse(self.asked("bypass", self.edit()))

    def test_not_asking_again_covers_edits_or_a_program_but_never_a_risky_command(self):
        self.assertFalse(self.asked("manual", self.edit(), {"edits"}))
        self.assertTrue(self.asked("manual", self.command("npm test"), {"cmd:node"}))
        self.assertFalse(self.asked("manual", self.command("npm test"), {"cmd:npm"}))
        self.assertTrue(self.asked("manual", self.command("npm i && node x.js"), {"cmd:npm"}))      # every program of it
        self.assertFalse(self.asked("accept_edits", self.command("terraform apply"), {"cmd:terraform"}))
        self.assertTrue(self.asked("auto", self.command("sudo ls"), {"cmd:sudo", "edits"}))


class GateTests(Fixture):
    """The question itself: what is put on screen, and what the agent is told."""

    def gate(self, cancelled=lambda: False):
        return permissions.gate_for(PROJECT, cancelled, lambda: bus.DEVELOPER)

    def answered(self, reply):
        return mock.patch.object(bus, "ask_and_wait", return_value=reply)

    def test_what_may_go_ahead_is_not_asked_about(self):
        self.mode("auto")
        with mock.patch.object(bus, "ask_and_wait", side_effect=AssertionError("asked")):
            self.assertEqual(self.gate()(self.edit()), "")
            self.assertEqual(self.gate()(self.command("npm test")), "")

    def test_the_question_is_a_permission_card_with_the_command_and_why(self):
        self.mode("accept_edits")
        with self.answered("allow") as ask:
            self.assertEqual(self.gate()(self.command("terraform apply")), "")
        args, kwargs = ask.call_args
        self.assertEqual(args[1], "permission")
        self.assertEqual(args[2], "Run this command?")
        self.assertEqual(kwargs["detail"], "terraform apply")
        self.assertIn("terraform", kwargs["reason"] + kwargs["always_label"])
        self.assertEqual(kwargs["options"], ["allow", "always", "deny"])
        self.assertFalse(kwargs["danger"])
        self.assertTrue(any(e.get("title") == "Permission" and "Allowed" in e["text"] for e in self.events))

    def test_a_denied_action_tells_the_agent_what_the_person_said(self):
        self.mode("manual")
        with self.answered("deny:use pnpm instead"):
            told = self.gate()(self.command("npm install"))
        self.assertIn("did not allow this command", told)
        self.assertIn("use pnpm instead", told)
        with self.answered("deny"):
            self.assertIn("did not allow this edit", self.gate()(self.edit()))

    def test_allow_and_do_not_ask_again_is_remembered_for_the_session(self):
        self.mode("manual")
        with self.answered("always") as ask:
            gate = self.gate()
            self.assertEqual(gate(self.edit("a.ts")), "")
            self.assertEqual(gate(self.edit("b.ts")), "")
        self.assertEqual(ask.call_count, 1)
        permissions.set_mode(PROJECT, "manual")             # a change of mode forgets it
        with self.answered("allow") as ask:
            self.gate()(self.edit("c.ts"))
        self.assertEqual(ask.call_count, 1)

    def test_a_risky_command_is_always_asked_and_offers_no_do_not_ask_again(self):
        self.mode("auto")
        with self.answered("always") as ask:
            gate = self.gate()
            gate(self.command("sudo ls"))
            gate(self.command("sudo ls"))
        self.assertEqual(ask.call_count, 2)
        self.assertTrue(ask.call_args.kwargs["danger"])
        self.assertEqual(ask.call_args.kwargs["always_label"], "")

    def test_stop_while_waiting_ends_the_wait(self):
        self.mode("manual")
        with self.answered(None):
            self.assertIn("Stopped", self.gate()(self.edit()))

    def test_bypass_goes_ahead_without_a_word(self):
        permissions.enable_bypass(True)
        permissions.set_mode(PROJECT, "bypass")
        with mock.patch.object(bus, "ask_and_wait", side_effect=AssertionError("asked")):
            self.assertEqual(self.gate()(self.command("sudo rm -rf /")), "")

    def test_the_card_is_answered_through_the_decision_route_and_the_run_goes_on(self):
        """The real wait: a run holds still on the card until the studio's answer arrives."""
        self.mode("manual")
        result: list[str] = []
        worker = threading.Thread(target=lambda: result.append(self.gate()(self.command("npm test"))))
        worker.start()
        for _ in range(100):
            waiting = [d for d in bus.pending_decisions() if d.get("kind") == "permission"]
            if waiting:
                break
            time.sleep(0.05)
        self.assertEqual(len(waiting), 1)
        card = waiting[0]
        self.assertEqual((card["action"], card["detail"], card["project"]), ("command", "npm test", PROJECT))
        self.assertTrue(worker.is_alive())                                    # still waiting
        self.assertIsNone(bus.waiting_question(PROJECT))                      # typing never answers it
        answer = httpd.decide({"id": card["id"], "decision": "answer", "reply": "allow"})
        worker.join(5)
        self.assertEqual(answer, {"ok": True})
        self.assertEqual(result, [""])
        self.assertEqual([d for d in bus.pending_decisions() if d.get("kind") == "permission"], [])

    def test_a_card_whose_run_has_ended_is_cleared_and_never_becomes_a_message_to_the_agent(self):
        card = bus.ask(PROJECT, "permission", "Run this command?", options=["allow", "always", "deny"], detail="npm test")
        with mock.patch.object(httpd.runs, "agent_update_direct", side_effect=AssertionError("sent to the agent")):
            answer = httpd.decide({"id": card, "decision": "answer", "reply": "allow"})
        self.assertFalse(answer["ok"])
        self.assertEqual(bus.pending_decisions(), [])


class ToolTests(Fixture):
    def setUp(self):
        super().setUp()
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.tools = tools.WorkspaceTools(Path(self.folder.name), None, lambda question: False, shell="powershell" if sys.platform == "win32" else "/bin/sh")

    def test_without_a_host_that_asks_an_unusual_command_is_still_refused_and_edits_use_approve(self):
        with self.assertRaises(ValueError) as caught:
            self.tools.tool_run_command("terraform apply")
        self.assertIn("Command blocked", str(caught.exception))
        self.assertEqual(self.tools.tool_write_file("a.txt", "x"), "Denied by user")
        self.assertFalse((Path(self.folder.name) / "a.txt").exists())

    def test_with_a_host_that_asks_the_answer_decides_and_nothing_is_written_when_it_is_no(self):
        seen: list[dict] = []
        self.tools.permission = lambda action: seen.append(action) or "The person did not allow this edit."
        self.assertIn("did not allow", self.tools.tool_write_file("a.txt", "hello"))
        self.assertFalse((Path(self.folder.name) / "a.txt").exists())
        self.assertEqual((seen[0]["kind"], seen[0]["file"]), ("edit", "a.txt"))
        self.tools.permission = lambda action: ""
        self.assertIn("Wrote", self.tools.tool_write_file("a.txt", "hello"))
        self.assertEqual((Path(self.folder.name) / "a.txt").read_text(encoding="utf-8"), "hello")
        self.assertIn("Edited", self.tools.tool_replace_text("a.txt", "hello", "bye"))

    def test_an_unusual_command_is_put_to_the_host_instead_of_being_refused(self):
        seen: list[dict] = []
        self.tools.permission = lambda action: seen.append(action) or "The person did not allow this command."
        told = self.tools.tool_run_command("terraform apply")
        self.assertIn("did not allow", told)
        self.assertEqual((seen[0]["level"], seen[0]["program"]), ("unusual", "terraform"))

    def test_the_rules_that_protect_the_studio_itself_still_hold_in_every_mode(self):
        self.tools.permission = lambda action: ""
        with self.assertRaises(ValueError) as caught:
            self.tools.tool_run_command("taskkill /F /IM node.exe")
        self.assertIn("node.exe", str(caught.exception))


class RouteTests(Fixture):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(httpd, "_project", lambda ctx: PROJECT)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_project_is_put_in_a_mode_through_the_route_and_the_workflow_says_which(self):
        answer = httpd.set_permission_mode({"mode": "accept_edits"})
        self.assertEqual(answer["mode"], "accept_edits")
        self.assertEqual(httpd.get_permission_mode({})["mode"], "accept_edits")
        with self.assertRaises(ValueError):
            httpd.set_permission_mode({"mode": "bypass"})

    def test_the_plan_first_switch_is_not_a_mode_and_is_left_as_it_was(self):
        self.assertIs(httpd.set_plan_mode({"enabled": False})["plan_mode"], False)
        self.assertNotIn("permission_mode", self.record)
        self.assertIs(httpd.set_plan_mode({"enabled": True})["plan_mode"], True)

    def test_bypass_is_turned_on_and_the_default_mode_is_changed_through_the_settings_route(self):
        status = httpd.permission_settings({"bypass": True, "default": "bypass"})
        self.assertTrue(status["bypass_enabled"])
        self.assertEqual(status["default"], "bypass")
        status = httpd.permission_settings({"bypass": False})
        self.assertFalse(status["bypass_enabled"])
        self.assertEqual(status["default"], "auto")
        self.assertEqual([m["id"] for m in httpd.permission_status({})["modes"]], list(permissions.MODES))


if __name__ == "__main__":
    unittest.main()
