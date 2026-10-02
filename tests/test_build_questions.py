"""A build or update that pauses mid-run to ask the customer something.

Mirrors the deployment flow's own question/answer mechanism (see
`tests/test_deploy_flow.py`), but deliberately without its plan-approval
card: clicking Build still runs immediately, it can just pause and resume
mid-way when it genuinely needs a value or decision only the customer can
give - a credential, a real account detail, a choice with no safe default.
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
for folder in (".", "builder-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import build  # noqa: E402
from server_modules import bus  # noqa: E402
from support import isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


PROJECT = "prj_build_question_test"


class FakeSession:
    """Stands in for the engine, matching the shape `deploy_agent`'s own flow tests use."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.lock = threading.RLock()
        self.runs: list = []  # callables(request, plan) -> result dict, one per execute_approved
        self.executed: list[tuple[str, str]] = []
        self.finished: list[str] = []
        self.failed: list[str] = []
        self.stages: list[str] = []

    def begin(self, stage, role=None, run_id=""):
        self.stages.append(stage)

    def finish(self, text=""):
        self.finished.append(text)

    def fail(self, text):
        self.failed.append(text)

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        if not path.is_file():
            return fallback
        return json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else path.read_text()

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data) if path.suffix == ".json" else str(data), encoding="utf-8")
        return path

    def execute_approved(self, request, plan, model=""):
        self.executed.append((request, plan))
        return self.runs.pop(0)(request, plan)


class QuestionFlowCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        (self.workspace / ".agentforge").mkdir()
        self.session = FakeSession(self.workspace)
        bus._pending_decisions.clear()
        self.enterContext(mock.patch.object(build, "session_for", lambda project: self.session))


class SettleTests(QuestionFlowCase):
    def test_a_real_result_passes_through_and_clears_any_stale_pending_state(self):
        self.session.write_record(*build.PENDING, data={"mode": "run", "question": {"question": "stale"}})
        result = build._settle(PROJECT, self.session, "run", "the request", "the plan",
                               {"status": "complete", "text": "done"})
        self.assertEqual(result, {"status": "complete", "text": "done"})
        self.assertIsNone(build.waiting(PROJECT))

    def test_a_block_with_no_question_file_is_a_real_failure(self):
        with self.assertRaisesRegex(ValueError, "stuck on something"):
            build._settle(PROJECT, self.session, "run", "the request", "the plan",
                          {"status": "blocked", "text": "stuck on something"})

    def test_a_block_with_a_question_pauses_instead_of_failing(self):
        self.session.write_record(*build.QUESTION, data={
            "question": "Which payment provider - Stripe or PayPal?", "why": "not in the SRS",
            "options": [{"label": "Stripe"}, {"label": "PayPal"}], "assumption": ""})
        result = build._settle(PROJECT, self.session, "run", "the full request", "the plan text",
                               {"status": "blocked", "text": "asked something"})
        self.assertEqual(result["status"], "asking")
        self.assertEqual(result["question"]["question"], "Which payment provider - Stripe or PayPal?")
        self.assertEqual(self.session.finished, ["Waiting for your answer."])
        pending = build.waiting(PROJECT)
        self.assertEqual(pending["mode"], "run")
        self.assertEqual(pending["request"], "the full request")
        self.assertEqual(pending["plan"], "the plan text")
        decisions = bus.pending_decisions()
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["flow"], "build")
        self.assertEqual(decisions[0]["question"], "Which payment provider - Stripe or PayPal?")

    def test_a_credential_question_carries_its_variable_and_secret_flag_to_the_studio(self):
        self.session.write_record(*build.QUESTION, data={
            "question": "What is the Stripe secret key?", "why": "needed to charge cards",
            "options": [], "assumption": "", "variable": "STRIPE_SECRET_KEY", "secret": True})
        build._settle(PROJECT, self.session, "run", "req", "plan", {"status": "blocked", "text": ""})
        decision = bus.pending_decisions()[0]
        self.assertEqual(decision["variable"], "STRIPE_SECRET_KEY")
        self.assertTrue(decision["secret"])

    def test_a_secret_asked_for_without_a_variable_still_gets_the_private_box(self):
        self.session.write_record(*build.QUESTION, data={
            "question": "What should the admin password be?", "why": "the first sign-in account needs one",
            "options": [{"label": "Use the prototype's demo password"}], "assumption": "use the demo password"})
        build._settle(PROJECT, self.session, "run", "req", "plan", {"status": "blocked", "text": ""})
        decision = bus.pending_decisions()[0]
        self.assertEqual(decision["variable"], "ADMIN_PASSWORD")
        self.assertTrue(decision["secret"])

    def test_a_choice_that_only_mentions_a_password_stays_a_plain_question(self):
        self.session.write_record(*build.QUESTION, data={
            "question": "Should people sign in with a password or with Google?", "why": "",
            "options": [{"label": "Password"}, {"label": "Google"}], "assumption": "password"})
        build._settle(PROJECT, self.session, "run", "req", "plan", {"status": "blocked", "text": ""})
        self.assertFalse(bus.pending_decisions()[0].get("variable"))

    def test_a_supabase_value_is_never_asked_when_the_project_is_connected(self):
        self.session.write_record(*build.QUESTION, data={
            "question": "What is the Supabase service role key?", "why": "storage uploads need it",
            "options": [], "assumption": "", "variable": "SUPABASE_SERVICE_ROLE_KEY", "secret": True})
        self.session.runs.append(lambda request, plan: {"status": "complete", "text": "done"})
        with mock.patch.object(build.supabase_connect, "record", return_value={"ref": "abc", "url": "https://abc.supabase.co"}):
            result = build._settle(PROJECT, self.session, "run", "req", "plan", {"status": "blocked", "text": ""})
        self.assertEqual(result["status"], "complete")
        self.assertEqual(bus.pending_decisions(), [])
        resumed, _plan = self.session.executed[0]
        self.assertIn("already connected", resumed)
        self.assertIn("What is the Supabase service role key?", resumed)

    def test_the_supabase_storage_choice_is_still_asked(self):
        self.session.write_record(*build.QUESTION, data={
            "question": "This app stores product photos. Keep them in Supabase Storage, served by signed URL?",
            "why": "", "options": [{"label": "Yes — Supabase Storage"}, {"label": "No"}],
            "assumption": "keep them in Supabase Storage"})
        with mock.patch.object(build.supabase_connect, "record", return_value={"ref": "abc"}):
            result = build._settle(PROJECT, self.session, "run", "req", "plan", {"status": "blocked", "text": ""})
        self.assertEqual(result["status"], "asking")
        self.assertIn("Supabase Storage", bus.pending_decisions()[0]["question"])

    def test_a_supabase_question_keeps_asking_the_customer_only_after_the_automatic_answers(self):
        def ask_again(request, plan):
            self.session.write_record(*build.QUESTION, data={
                "question": "Paste the Supabase anon key", "why": "", "options": [], "assumption": ""})
            return {"status": "blocked", "text": ""}
        self.session.write_record(*build.QUESTION, data={
            "question": "Paste the Supabase anon key", "why": "", "options": [], "assumption": ""})
        self.session.runs.extend([ask_again] * build.AUTO_ANSWERS)
        with mock.patch.object(build.supabase_connect, "record", return_value={"ref": "abc"}):
            result = build._settle(PROJECT, self.session, "run", "req", "plan", {"status": "blocked", "text": ""})
        self.assertEqual(result["status"], "asking")
        self.assertEqual(len(self.session.executed), build.AUTO_ANSWERS)

    def test_there_is_no_cap_on_how_many_times_a_build_may_ask(self):
        for index in range(12):
            self.session.write_record(*build.QUESTION, data={
                "question": f"question {index}", "why": "", "options": [], "assumption": ""})
            result = build._settle(PROJECT, self.session, "run", "req", "plan",
                                   {"status": "blocked", "text": ""})
            self.assertEqual(result["status"], "asking")
            bus.pending_decisions()[-1]  # each one is genuinely posted, never refused


class AnswerTests(QuestionFlowCase):
    def test_answering_with_nothing_waiting_is_refused(self):
        with self.assertRaisesRegex(ValueError, "no build or update waiting"):
            build.answer(PROJECT, "Stripe")

    def test_answering_resumes_the_same_plan_with_the_question_and_reply_folded_in(self):
        self.session.write_record(*build.PENDING, data={
            "mode": "update", "request": "the original request", "plan": "the approved plan",
            "question": {"question": "Which payment provider?"}})
        self.session.runs.append(lambda request, plan: {"status": "complete", "text": "Stripe wired up."})
        result = build.answer(PROJECT, "Stripe")
        self.assertEqual(result, {"status": "complete", "text": "Stripe wired up."})
        request, plan = self.session.executed[0]
        self.assertIn("the original request", request)
        self.assertIn("Which payment provider?", request)
        self.assertIn("Stripe", request)
        self.assertEqual(plan, "the approved plan")
        self.assertEqual(self.session.stages, ["build-edit"])
        self.assertIsNone(build.waiting(PROJECT))

    def test_asking_again_on_resume_stays_paused_instead_of_finishing(self):
        self.session.write_record(*build.PENDING, data={
            "mode": "run", "request": "req", "plan": "plan",
            "question": {"question": "first question?"}})

        def blocked_again(request, plan):
            build.session_for(PROJECT).write_record(*build.QUESTION, data={
                "question": "second question?", "why": "", "options": [], "assumption": ""})
            return {"status": "blocked", "text": ""}

        self.session.runs.append(blocked_again)
        result = build.answer(PROJECT, "an answer")
        self.assertEqual(result["status"], "asking")
        self.assertEqual(result["question"]["question"], "second question?")
        pending = build.waiting(PROJECT)
        self.assertEqual(pending["question"]["question"], "second question?")

    def test_an_empty_reply_tells_the_model_to_decide_itself(self):
        self.session.write_record(*build.PENDING, data={
            "mode": "update", "request": "req", "plan": "plan",
            "question": {"question": "Which provider?"}})
        self.session.runs.append(lambda request, plan: {"status": "complete", "text": "done"})
        build.answer(PROJECT, "")
        request, _plan = self.session.executed[0]
        self.assertNotIn("\nA: \n", request)


class StartGuardTests(QuestionFlowCase):
    def test_run_refuses_to_start_while_an_earlier_question_is_still_waiting(self):
        self.session.write_record(*build.PENDING, data={
            "mode": "run", "request": "req", "plan": "plan", "question": {"question": "q?"}})
        with mock.patch("srs_agent.document.has_document", return_value=True):
            with self.assertRaisesRegex(ValueError, "already has a build waiting"):
                build.run(PROJECT)

    def test_update_refuses_to_start_while_an_earlier_question_is_still_waiting(self):
        self.session.write_record(*build.PENDING, data={
            "mode": "update", "request": "req", "plan": "plan", "question": {"question": "q?"}})
        with mock.patch.object(build, "built", return_value=True):
            with self.assertRaisesRegex(ValueError, "already has a change waiting"):
                build.update(PROJECT, "add a due date")


if __name__ == "__main__":
    unittest.main()
