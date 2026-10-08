"""A project whose plan is approved but whose specification is not written (a run of it failed) is written by the pipeline when the
person types into the chat or presses Continue: a chat agent improvising a `requirements.md` leaves the SRS tab empty."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import runs  # noqa: E402
from srs_agent import document as srs_document  # noqa: E402
from srs_agent import plan as plan_stage  # noqa: E402

PROJECT = "prj_inventory"


class Pending(unittest.TestCase):
    def setUp(self):
        self.started = []
        patches = [
            mock.patch.object(runs, "_in_background", lambda name, project, agent, fn, *args, **kw: self.started.append((name, fn, args))),
            mock.patch.object(runs, "_answer_held", return_value=None),
            mock.patch.object(runs.secrets_guard, "refusal", return_value=""),
            mock.patch.object(runs, "_remember_model"),
            mock.patch.object(runs.bus, "agent_msg"),
            mock.patch.object(runs.bus, "user_msg"),
            mock.patch.object(runs.store, "require", return_value={"stage": "srs"}),
            mock.patch.object(runs.changes, "applies", return_value=False),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def state(self, plan: bool, document: bool):
        for patcher in (mock.patch.object(plan_stage, "approved_plan", return_value={"app_name": "x"} if plan else {}),
                        mock.patch.object(srs_document, "has_document", return_value=document)):
            patcher.start()
            self.addCleanup(patcher.stop)


class ChatTests(Pending):
    def test_a_message_to_a_project_with_an_approved_plan_and_no_specification_writes_the_specification(self):
        self.state(plan=True, document=False)
        answer = runs.agent_update({"project": PROJECT, "prompt": "continue"})
        self.assertEqual(answer, {"ok": True, "project": PROJECT})
        self.assertEqual([(name, fn) for name, fn, _ in self.started], [(f"srs:{PROJECT}", srs_document.generate)])
        self.assertEqual(self.started[0][2], (PROJECT,))
        runs.bus.user_msg.assert_called_once_with(PROJECT, "continue")
        self.assertEqual(runs.bus.agent_msg.call_args.kwargs["title"], "Specification")

    def test_a_chat_agent_is_not_started_in_its_place(self):
        self.state(plan=True, document=False)
        with mock.patch.object(runs, "_chat") as chat:
            runs.agent_update({"project": PROJECT, "prompt": "go on"})
        chat.assert_not_called()

    def test_without_an_approved_plan_the_message_is_answered_where_it_stands(self):
        self.state(plan=False, document=False)
        runs.agent_update({"project": PROJECT, "prompt": "what next?"})
        self.assertEqual([name for name, _, _ in self.started], [f"chat:{PROJECT}"])

    def test_with_a_specification_the_message_is_not_taken_for_a_request_to_write_it(self):
        self.state(plan=True, document=True)
        runs.agent_update({"project": PROJECT, "prompt": "what next?"})
        self.assertEqual([name for name, _, _ in self.started], [f"chat:{PROJECT}"])


class ContinueTests(Pending):
    def test_continue_after_a_failed_specification_writes_it_again(self):
        self.state(plan=True, document=False)
        runs.agent_resume({"project": PROJECT})
        self.assertEqual([(name, fn) for name, fn, _ in self.started], [(f"srs:{PROJECT}", srs_document.generate)])
        runs.bus.user_msg.assert_not_called()

    def test_continue_with_a_specification_goes_on_as_it_did(self):
        self.state(plan=True, document=True)
        with mock.patch.object(runs.builder, "run"):
            runs.agent_resume({"project": PROJECT})
        self.assertEqual([name for name, _, _ in self.started], [f"build:{PROJECT}"])


if __name__ == "__main__":
    unittest.main()
