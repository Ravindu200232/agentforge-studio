"""The build stage's own completeness gate.

Found live: a real project stuck resuming forever with "Run failed - the
single build plan ended without a complete qa/report.json" on every attempt,
even though the agent's own summary (and the recorded per-layer evidence)
described every layer as genuinely finished. An earlier run had been
interrupted after the real testing work but before the one `complete: true`
flag was written; resuming kept re-deriving "nothing left to do" from that
same evidence without ever performing the one write that would let the gate
pass - the exact same failure, forever.
"""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "builder-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import build  # noqa: E402
from server_modules import bus, httpd, prompts, runs  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402
from server_modules.validation import build_report  # noqa: E402
from support import isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


class RecoverablyIncompleteTests(unittest.TestCase):
    def test_a_report_with_real_evidence_but_no_complete_flag_is_recoverable(self):
        # Exactly the shape a run interrupted right before its last write
        # would leave: every layer genuinely recorded, `complete` just never set.
        qa_report = {
            "project": "prj_hotel", "summary": {"pass": 12, "fail": 0},
            "journeys": {"stage_total": 12, "stage_passed": 12},
            "accessibility": {"audited": 5}, "security": {"zap": {"status": "partial"}},
        }
        self.assertTrue(build._recoverably_incomplete(qa_report))

    def test_a_missing_report_is_not_recoverable(self):
        self.assertFalse(build._recoverably_incomplete(None))

    def test_a_bare_placeholder_report_is_not_recoverable(self):
        # No real evidence recorded at all - testing plausibly never ran.
        self.assertFalse(build._recoverably_incomplete({"project": "prj_hotel"}))
        self.assertFalse(build._recoverably_incomplete({}))

    def test_an_explicit_complete_false_is_never_overridden(self):
        # The model itself judged this incomplete - a real, honest gap, not
        # the "forgot to write the flag" bug. Never silently override it.
        qa_report = {"project": "prj_hotel", "complete": False,
                    "summary": {"pass": 10, "fail": 2}, "bugs": ["payment webhook 500s"]}
        self.assertFalse(build._recoverably_incomplete(qa_report))

    def test_a_report_with_no_summary_is_not_recoverable(self):
        qa_report = {"project": "prj_hotel", "provenance": "no verification has run yet"}
        self.assertFalse(build._recoverably_incomplete(qa_report))


RUN_PROJECT = "prj_build_straight_through_test"


class Agent:
    def __init__(self):
        self.modes: list[str] = []

    def set_mode(self, mode):
        self.modes.append(mode)


class RunSession:
    """The part of a project session that `build.run` and `build.update` touch, with the engine's calls mocked.

    `says` is what the model answers on the turn before the plan, one per turn (a dict, or an exception to raise);
    once it runs out the model says it is ready - nothing to ask.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.lock = threading.RLock()
        self.cancelled = False
        self.results: list[dict] = []
        self.says: list = []
        self.requests: list[str] = []
        self.before_plan: list[str] = []
        self.task_options: list[dict] = []
        self.stages: list[str] = []
        self.finished: list[str] = []
        self.failed: list[str] = []
        self._agent = Agent()

    def begin(self, stage, role=None, run_id=""):
        self.stages.append(stage)

    def agent(self, model=""):
        return self._agent

    def ask_json(self, prompt, validator=None, model="", attempts=3):
        self.before_plan.append(prompt)
        said = self.says.pop(0) if self.says else {"kind": "ready"}
        if isinstance(said, Exception):
            raise said
        return validator(said) if validator else said

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def run_task(self, request, **options):
        self.requests.append(request)
        self.task_options.append(options)
        return self.results.pop(0)

    def finish(self, text=""):
        self.finished.append(text)

    def fail(self, text):
        self.failed.append(text)


class StraightThroughCase(unittest.TestCase):
    """A build or update is one run that never parks a question on the customer."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = RunSession(Path(self.temp.name))
        bus._pending_decisions.clear()
        self.ask = mock.Mock()
        self.ensure_project = mock.Mock(return_value={"ref": "abc"})
        self.finished_runs: list[tuple] = []
        for patch in (
            mock.patch.object(build, "session_for", lambda project: self.session),
            mock.patch.object(build.store, "require", return_value={"stack": "nextjs-supabase", "name": "Shop"}),
            mock.patch.object(build.bus, "ask", self.ask),
            mock.patch.object(build.supabase_connect, "ensure_project", self.ensure_project),
            mock.patch.object(build, "_finish_run", lambda project, session, result, plan="":
                              self.finished_runs.append((result, plan)) or {"status": "complete"}),
            mock.patch.object(build, "show_preview"),
            mock.patch("srs_agent.document.has_document", return_value=True),
            mock.patch("srs_agent.document.document", return_value={"srs_document": {}}),
            mock.patch("prototype_agent.design.approved_customization", return_value={}),
        ):
            self.enterContext(patch)

    def assertNothingWasAsked(self):
        self.ask.assert_not_called()
        self.assertEqual(bus.pending_decisions(), [])
        for name in ("question.json", "pending.json", "setup.json"):
            self.assertFalse((self.session.record / "build" / name).exists(), name)


class RunStraightThroughTests(StraightThroughCase):
    def setUp(self):
        super().setUp()
        self.install = mock.Mock(return_value={"scaffolded": True, "files": ["package.json"]})
        self.enterContext(mock.patch("builder_agent.scaffold.install", self.install))

    def test_a_build_goes_straight_to_planning_and_never_asks(self):
        outcome = {"status": "complete", "text": "done", "plan": "the plan", "plan_file": "p.md"}
        self.session.results.append(outcome)
        result = build.run(RUN_PROJECT, direction="make the checkout quick")
        self.assertEqual(result, {"status": "complete"})
        self.assertNothingWasAsked()
        self.assertEqual(self.session.stages, ["build"])
        self.ensure_project.assert_called_once()
        self.assertEqual(self.ensure_project.call_args.args, (RUN_PROJECT,))
        self.assertEqual(self.ensure_project.call_args.kwargs["name"], "Shop")
        self.install.assert_called_once_with(self.session.workspace, "nextjs-supabase")
        self.assertEqual(self.session.task_options, [{"plan_directory": "plan", "audit": False}])
        request = self.session.requests[0]
        self.assertIn("## Scaffold installation", request)
        self.assertIn("## Stack build guides", request)
        self.assertIn("make the checkout quick", request)
        self.assertNotIn("Settled with the customer", request)
        self.assertEqual(self.finished_runs, [(outcome, "the plan")])
        self.assertEqual(self.session.failed, [])

    def test_a_blocked_build_is_a_failure_with_its_own_words_never_a_question(self):
        self.session.results.append({"status": "blocked", "text": "the database refused the migration"})
        with self.assertRaisesRegex(ValueError, "the database refused the migration"):
            build.run(RUN_PROJECT)
        self.assertEqual(self.session.failed, ["the database refused the migration"])
        self.assertEqual(self.finished_runs, [])
        self.assertNothingWasAsked()

    def test_a_blocked_build_with_no_words_still_says_what_happened(self):
        self.session.results.append({"status": "blocked", "text": ""})
        with self.assertRaisesRegex(ValueError, "the build was blocked"):
            build.run(RUN_PROJECT)
        self.assertNothingWasAsked()

    def test_a_cancelled_build_is_passed_on_and_is_not_recorded_as_a_failure(self):
        self.session.run_task = mock.Mock(side_effect=RunCancelled())
        with self.assertRaises(RunCancelled):
            build.run(RUN_PROJECT)
        self.assertEqual(self.session.failed, [])
        self.assertNothingWasAsked()

    def test_a_database_that_cannot_be_set_up_fails_the_build_instead_of_asking(self):
        self.ensure_project.side_effect = ValueError("free plan limit: 2 active projects")
        with self.assertRaisesRegex(ValueError, "free plan limit"):
            build.run(RUN_PROJECT)
        self.assertEqual(self.session.requests, [])
        self.assertEqual(self.session.failed, ["free plan limit: 2 active projects"])
        self.assertNothingWasAsked()

    def test_a_build_still_needs_its_specification(self):
        with mock.patch("srs_agent.document.has_document", return_value=False):
            with self.assertRaisesRegex(ValueError, "write the specification before building"):
                build.run(RUN_PROJECT)
        self.ensure_project.assert_not_called()

    def test_old_question_files_left_in_a_project_do_not_block_a_new_build(self):
        for name in ("pending.json", "question.json", "setup.json"):
            path = self.session.record / "build" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"mode": "run", "question": {"question": "stale?"}}), encoding="utf-8")
        self.session.results.append({"status": "complete", "text": "done", "plan": "p"})
        self.assertEqual(build.run(RUN_PROJECT), {"status": "complete"})
        self.ask.assert_not_called()


class FreshProjectTemplateTests(StraightThroughCase):
    def test_a_fresh_project_still_gets_its_template(self):
        """The guides are staged in the record folder, never the app root: a folder made there would make
        `scaffold.install` take a fresh workspace for an existing app and copy no template."""
        self.session.results.append({"status": "complete", "text": "done", "plan": "p"})
        build.run(RUN_PROJECT)
        request = self.session.requests[0]
        installed = json.loads(request.split("## Scaffold installation\n", 1)[1].split("\n\n## ", 1)[0])
        self.assertTrue(installed["scaffolded"], installed.get("existing"))
        self.assertTrue((self.session.workspace / ".agentforge" / "build" / "guides" / "pitfalls.md").is_file())
        self.assertFalse((self.session.workspace / "build").exists())
        self.assertNothingWasAsked()


class UpdateStraightThroughTests(StraightThroughCase):
    def setUp(self):
        super().setUp()
        self.enterContext(mock.patch.object(build, "built", return_value=True))

    def test_an_update_runs_to_the_end_and_never_asks(self):
        self.session.results.append({"status": "complete", "text": "Added the due date."})
        result = build.update(RUN_PROJECT, "add a due date")
        self.assertEqual(result, {"status": "complete", "text": "Added the due date."})
        self.assertEqual(self.session.stages, ["build-edit"])
        self.assertIn("add a due date", self.session.requests[0])
        self.assertEqual(self.session.task_options, [{"audit": False}])
        self.assertEqual(self.session.finished, ["Added the due date."])
        self.assertNothingWasAsked()

    def test_a_blocked_update_ends_as_blocked_instead_of_waiting_on_an_answer(self):
        self.session.results.append({"status": "blocked", "text": "could not reach the payment sandbox"})
        result = build.update(RUN_PROJECT, "take card payments")
        self.assertEqual(result, {"status": "blocked", "text": "could not reach the payment sandbox"})
        self.assertEqual(self.session.finished, ["could not reach the payment sandbox"])
        self.assertNothingWasAsked()

    def test_an_update_needs_something_built_first(self):
        with mock.patch.object(build, "built", return_value=False):
            with self.assertRaisesRegex(ValueError, "nothing built to change yet"):
                build.update(RUN_PROJECT, "add a due date")


class AskingBeforeThePlanTests(StraightThroughCase):
    """The model may ask what it cannot settle itself - once, before the plan, in its own words - and then the build
    runs straight through. Nothing in the code says what to ask."""

    def setUp(self):
        super().setUp()
        self.ensure_project.return_value = {"ref": "abc"}
        self.enterContext(mock.patch("builder_agent.scaffold.install",
                                     mock.Mock(return_value={"scaffolded": True, "files": ["package.json"]})))
        self.waited = mock.Mock(return_value="Use the sandbox")
        self.enterContext(mock.patch.object(build.bus, "ask_and_wait", self.waited))
        self.session.results.append({"status": "complete", "text": "done", "plan": "p"})

    def question(self, text="Which payment provider should checkout use?", **extra):
        return {"kind": "question", "question": text, "why": "the specification names none",
                "options": [{"label": "Stripe", "hint": "cards"}, {"label": "PayPal"}],
                "assumption": "use Stripe", **extra}

    def test_when_nothing_needs_the_customer_the_build_just_goes(self):
        build.run(RUN_PROJECT)
        self.waited.assert_not_called()
        self.assertEqual(len(self.session.before_plan), 1)
        self.assertNotIn("## Decided with the customer", self.session.requests[0])
        self.assertEqual(self.session._agent.modes, ["plan", "act"])
        self.assertFalse((self.session.record / "build" / "decisions.json").exists())

    def test_a_question_the_model_writes_is_asked_and_the_answer_goes_into_the_plan(self):
        self.session.says += [self.question(), {"kind": "ready"}]
        build.run(RUN_PROJECT)
        self.waited.assert_called_once()
        args, kwargs = self.waited.call_args
        self.assertEqual(args[:3], (RUN_PROJECT, "question", "Which payment provider should checkout use?"))
        self.assertEqual([option["label"] for option in kwargs["options"]], ["Stripe", "PayPal"])
        self.assertEqual((kwargs["why"], kwargs["assumption"]), ("the specification names none", "use Stripe"))
        request = self.session.requests[0]
        self.assertIn("## Decided with the customer before this plan", request)
        self.assertIn("- Q: Which payment provider should checkout use?\n  A: Use the sandbox", request)
        self.assertIn("Asked and answered just now", self.session.before_plan[1])
        self.assertEqual(self.session.read_record(*build.DECISIONS),
                         [{"question": "Which payment provider should checkout use?", "answer": "Use the sandbox"}])

    def test_a_value_only_the_customer_has_is_asked_for_in_the_private_box(self):
        self.session.says += [self.question("What is the Stripe secret key?", variable="STRIPE_SECRET_KEY",
                                            secret=True), {"kind": "ready"}]
        build.run(RUN_PROJECT)
        kwargs = self.waited.call_args.kwargs
        self.assertEqual((kwargs["variable"], kwargs["secret"]), ("STRIPE_SECRET_KEY", True))

    def test_leaving_it_to_the_model_is_an_answer_too(self):
        self.waited.return_value = "   "
        self.session.says += [self.question(), {"kind": "ready"}]
        build.run(RUN_PROJECT)
        self.assertIn(prompts.load("changes/unanswered").strip(), self.session.requests[0])

    def test_the_model_cannot_keep_asking_but_the_build_still_goes(self):
        self.session.says += [self.question(f"Question {number}?") for number in range(build.QUESTIONS + 3)]
        self.assertEqual(build.run(RUN_PROJECT), {"status": "complete"})
        self.assertEqual(self.waited.call_count, build.QUESTIONS)
        self.assertIn(prompts.load("changes/no-questions").strip(), self.session.before_plan[-1])
        self.assertEqual(len(self.session.requests), 1)
        self.assertEqual(self.session.failed, [])

    def test_a_turn_that_fails_never_fails_the_build(self):
        self.session.says.append(ValueError("the model could not produce valid JSON after 3 attempts"))
        self.assertEqual(build.run(RUN_PROJECT), {"status": "complete"})
        self.waited.assert_not_called()
        self.assertEqual(self.session.failed, [])
        self.assertEqual(self.session._agent.modes, ["plan", "act"])      # back to acting even when the turn failed

    def test_answers_given_before_a_later_failure_still_count(self):
        self.session.says += [self.question(), RuntimeError("the model went away")]
        build.run(RUN_PROJECT)
        self.assertIn("A: Use the sandbox", self.session.requests[0])

    def test_stopping_the_run_while_it_waits_stops_the_build_without_failing_it(self):
        self.waited.return_value = None
        self.session.says.append(self.question())
        with self.assertRaises(RunCancelled):
            build.run(RUN_PROJECT)
        self.assertEqual(self.session.failed, [])
        self.assertEqual(self.session.requests, [])
        self.ensure_project.assert_not_called()

    def test_nothing_is_provisioned_or_planned_until_the_customer_has_answered(self):
        order = []
        self.waited.side_effect = lambda *args, **kwargs: order.append("answered") or "Stripe"
        self.ensure_project.side_effect = lambda *args, **kwargs: order.append("database")
        self.session.says += [self.question(), {"kind": "ready"}]
        self.session.run_task = lambda request, **options: order.append("plan") or {"status": "complete", "plan": ""}
        build.run(RUN_PROJECT)
        self.assertEqual(order, ["answered", "database", "plan"])

    def test_what_an_earlier_build_decided_is_not_asked_again_and_is_kept(self):
        self.session.write_record(*build.DECISIONS, data=[{"question": "Which provider?", "answer": "Stripe"}])
        self.session.says += [self.question("Which region?"), {"kind": "ready"}]
        build.run(RUN_PROJECT)
        self.assertIn("- Q: Which provider?\n  A: Stripe", self.session.before_plan[0])
        self.assertIn("- Q: Which provider?\n  A: Stripe", self.session.requests[0])
        self.assertEqual([row["answer"] for row in self.session.read_record(*build.DECISIONS)],
                         ["Stripe", "Use the sandbox"])

    def test_the_model_is_told_what_the_build_has_to_go_on_and_that_it_asks_nothing_later(self):
        self.session.says.append({"kind": "ready"})
        build.run(RUN_PROJECT, direction="make checkout quick")
        prompt = self.session.before_plan[0]
        self.assertIn("nextjs-supabase", prompt)
        self.assertIn("make checkout quick", prompt)
        self.assertIn(".agentforge/build/guides/", prompt)
        self.assertIn("Never ask for anything Supabase", prompt)

    def test_a_reply_that_is_neither_ready_nor_a_question_is_refused(self):
        with self.assertRaisesRegex(ValueError, '"kind" must be "ready" or "question"'):
            build._check_decision({"kind": "plan"}, True)
        with self.assertRaisesRegex(ValueError, "no more questions may be asked"):
            build._check_decision({"kind": "question", "question": "Again?"}, False)
        self.assertEqual(build._check_decision({"kind": "ready"}, False), {"kind": "ready"})


class HoldStillForAnswerTests(unittest.TestCase):
    """A run holding still for the customer: the card, the answer from the card or the chat, and being stopped."""

    PROJECT = "prj_hold_still_test"

    def setUp(self):
        bus._pending_decisions.clear()
        bus._waiters.clear()
        self.addCleanup(bus._pending_decisions.clear)
        self.addCleanup(bus._waiters.clear)
        self.stop = threading.Event()

    def start(self, **extra):
        out: dict = {}

        def hold():
            out["reply"] = bus.ask_and_wait(self.PROJECT, "question", "Which provider?", options=[{"label": "A"}],
                                            cancelled=self.stop.is_set, **extra)

        thread = threading.Thread(target=hold, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        return thread, out

    def card(self):
        for _ in range(200):
            question = bus.waiting_question(self.PROJECT)
            if question:
                return question
            time.sleep(0.01)
        self.fail("the question never reached the screen")

    def test_the_answer_from_the_card_releases_the_run(self):
        thread, out = self.start()
        card = self.card()
        result = httpd.decide({"id": card["id"], "decision": "answer", "reply": "PayPal"})
        thread.join(5)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(out["reply"], "PayPal")
        self.assertEqual((bus.pending_decisions(), bus._waiters), ([], {}))

    def test_choosing_to_leave_it_releases_the_run_with_an_empty_answer(self):
        thread, out = self.start()
        httpd.decide({"id": self.card()["id"], "decision": "default"})
        thread.join(5)
        self.assertEqual(out["reply"], "")

    def test_what_is_typed_in_the_chat_is_the_answer(self):
        thread, out = self.start()
        self.card()
        self.assertEqual(runs._answer_held(self.PROJECT, "PayPal please"), {"ok": True, "project": self.PROJECT})
        thread.join(5)
        self.assertEqual(out["reply"], "PayPal please")
        self.assertEqual(bus.pending_decisions(), [])

    def test_a_private_value_is_not_taken_from_the_chat(self):
        thread, out = self.start(variable="STRIPE_SECRET_KEY", secret=True)
        card = self.card()
        refused = runs._answer_held(self.PROJECT, "sk_live_whatever")
        self.assertFalse(refused["ok"])
        self.assertTrue(thread.is_alive())
        self.assertTrue(bus.deliver(card["id"], "saved"))      # the private box is the way in
        thread.join(5)
        self.assertEqual(out["reply"], "saved")

    def test_stopping_the_run_ends_the_wait_and_clears_the_card(self):
        thread, out = self.start()
        self.card()
        self.stop.set()
        thread.join(5)
        self.assertIsNone(out["reply"])
        self.assertEqual((bus.pending_decisions(), bus._waiters), ([], {}))

    def test_typing_in_the_chat_with_nothing_waiting_is_left_alone(self):
        self.assertIsNone(runs._answer_held(self.PROJECT, "add a due date"))

    def test_a_question_nobody_holds_still_for_is_not_taken_by_this(self):
        # Deployment's and the planner's questions: answered the way they always were.
        decision_id = bus.ask(self.PROJECT, "question", "Which region?", options=[])
        self.assertFalse(bus.deliver(decision_id, "eu"))
        with mock.patch.object(runs, "agent_update_direct") as direct:
            httpd.decide({"id": decision_id, "decision": "answer", "reply": "eu"})
        direct.assert_called_once()
        self.assertFalse(bus.deliver("ask-gone", "x"))


class NoQuestionsInTheBuildPromptsTests(unittest.TestCase):
    """The build prompts say never to ask; the deployment prompts, which do ask, are left as they were."""

    def test_the_build_prompts_do_not_tell_the_model_to_write_a_question_or_stop_for_an_answer(self):
        for name in ("builder/generate", "builder/update"):
            text = prompts.load(name)
            self.assertNotIn("question.json", text, name)
            self.assertNotIn("blocked marker", text, name)
            self.assertNotIn("Ask the customer", text, name)
            self.assertIn("ever stop to ask", text, name)

    def test_the_question_before_the_plan_is_left_to_the_model_in_its_own_words(self):
        text = prompts.load("builder/decide", stack="nextjs-supabase", supabase="", direction="", earlier="", answers="",
                            questions_left="You may ask up to 5 more question(s) in total for this request.")
        self.assertNotIn("{{", text)
        self.assertNotIn("question.json", text)
        self.assertNotIn("blocked marker", text)
        self.assertIn('{"kind": "ready"}', text)
        self.assertIn("Most builds need nothing", text)
        # No checklist of what to ask: no provider, region, plan tier or account is named in the prompt.
        for word in ("region", "free plan", "Atlas", "Stripe", "organisation"):
            self.assertNotIn(word, text)

    def test_the_build_prompts_keep_the_integration_rules_they_still_depend_on(self):
        for name in ("builder/generate", "builder/update"):
            text = prompts.load(name)
            self.assertIn(".agentforge/PLUGIN.md", text, name)
            self.assertIn("Supabase Storage", text, name)
            self.assertIn("storage.objects", text, name)

    def test_deployment_still_asks_its_questions(self):
        execute = prompts.load("deployment/execute")
        self.assertIn("blocked marker", execute)
        self.assertIn("NEEDS_INPUT", execute)
        self.assertIn("blocked marker", prompts.load("deployment/ask-now"))

    def test_a_gap_written_the_way_the_build_prompt_says_passes_the_report_check(self):
        import copy

        saved = copy.deepcopy(build_report.template()["build"]["example"])
        saved["gaps"] = [{"item": "Stripe payments", "status": "unavailable",
                          "reason": "STRIPE_SECRET_KEY is not set; the checkout reads it from .env.example"}]
        self.assertEqual(build_report.problems(saved, "build"), [])
        self.assertIn('"status": "gap|unavailable|untested|known"', prompts.load("builder/generate"))


if __name__ == "__main__":
    unittest.main()
