"""A deployment asks the customer in the middle of its run whenever it needs them, not only before the plan.

A run that stops for the customer but never writes the question it stopped for used to fail with its own
reasoning as the error and nobody asked anything; it is now told so once, and asks (or carries on).
"""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "deploy-agent", "builder-agent", "srs-agent", "prototype-agent", "qa-agent"):
    sys.path.insert(0, str(ROOT / folder))

from deploy_agent import deploy  # noqa: E402
from server_modules import bus  # noqa: E402

PROJECT = "prj_deploy_midway_test"
PLAN = {"title": "Deploy", "summary": "Go live", "steps": [{"id": "repo", "title": "Publish the repository"}]}
QUESTION = {"question": "The free tier is not available in that region. What should we do?", "why": "",
            "options": [{"label": "Use the nearest free region"}, {"label": "Pay for this region"}],
            "assumption": "use the nearest free region"}


class FakeSession:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.lock = threading.RLock()
        self.turns: list = []
        self.requests: list[str] = []

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def execute_approved(self, request, plan, model=""):
        self.requests.append(request)
        return self.turns.pop(0)()


class MidwayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = FakeSession(Path(self.temp.name))
        for patch in (mock.patch.object(deploy, "session_for", lambda project: self.session),
                      mock.patch.object(deploy, "stage_skills", return_value=[]),
                      mock.patch.object(deploy, "machine_facts", return_value="facts"),
                      mock.patch.object(deploy.changes, "project_map", return_value=""),
                      mock.patch.object(deploy.store, "get", return_value={})):
            self.enterContext(patch)
        self.change = {"target": "vercel", "plan": PLAN, "request": "Deploy it", "run_id": "run-1"}

    def asks(self):
        self.session.write_record(*deploy.QUESTION, data=QUESTION)
        self.session.write_record(*deploy.RUN, data={"state": "NEEDS_INPUT"})
        return {"status": "blocked", "text": "asked"}

    def test_a_question_written_mid_run_is_asked(self):
        self.session.turns = [self.asks]
        outcome = deploy.execute(PROJECT, self.change, self.session, "")
        self.assertEqual(outcome["status"], "asking")
        self.assertEqual(outcome["question"]["question"], QUESTION["question"])
        self.assertEqual(len(self.session.requests), 1)

    def test_a_stop_without_its_question_is_told_so_and_then_asks(self):
        thinking = {"status": "blocked", "text": "Hmm, I must stop and ask for values. Let me think..."}
        self.session.turns = [lambda: thinking, self.asks]
        outcome = deploy.execute(PROJECT, self.change, self.session, "")
        self.assertEqual(outcome["status"], "asking")
        self.assertIn("You stopped without asking", self.session.requests[1])
        self.assertIn("Publish the repository", self.session.requests[1])      # the same approved plan

    def test_a_run_that_set_needs_input_without_a_question_is_told_so_too(self):
        def waiting_without_question():
            self.session.write_record(*deploy.RUN, data={"state": "NEEDS_INPUT"})
            return {"status": "complete", "text": "waiting"}

        self.session.turns = [waiting_without_question, self.asks]
        self.assertEqual(deploy.execute(PROJECT, self.change, self.session, "")["status"], "asking")

    def test_it_is_told_once_and_a_second_silent_stop_fails_plainly(self):
        silent = lambda: {"status": "blocked", "text": "stopped"}  # noqa: E731
        self.session.turns = [silent, silent]
        outcome = deploy.execute(PROJECT, self.change, self.session, "")
        self.assertEqual(outcome["status"], "failed")
        self.assertEqual(len(self.session.requests), 2)

    def test_the_rules_ask_midway_for_stuck_refused_and_unsolvable(self):
        rules = deploy.prompts.load("deployment/execute")
        for needle in ("Ask in the middle of the deployment", "the same failure came back after two",
                       "a free tier that is not available", "then ask\n  what to do",
                       'never offer an\n  option that only means "I will type it"'):
            self.assertIn(needle, rules)


class QuestionIdTests(unittest.TestCase):
    def test_question_ids_never_repeat_across_restarts(self):
        first = bus.ask("prj_ids", "question", "a?")
        second = bus.ask("prj_ids", "question", "b?")
        self.assertNotEqual(first, second)
        self.assertRegex(first, r"^ask-\d+-[0-9a-f]{8}$")
        bus.resolve(first)
        bus.resolve(second)


if __name__ == "__main__":
    unittest.main()
