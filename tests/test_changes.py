"""A request typed in the chat is planned, shown, revised and approved before anything is changed."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, changes, config, httpd, prompts, runs  # noqa: E402
from support import forget_project  # noqa: E402

PROJECT = "prj_changes_test"


class FakeAgent:
    def __init__(self):
        self.modes: list[str] = []

    def set_mode(self, mode):
        self.modes.append(mode)


class FakeSession:
    """Stands in for the model: `replies` are what it answers to each planning turn, in order."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.lock = threading.RLock()
        self.agent_object = FakeAgent()
        self.replies: list = []
        self.prompts: list[str] = []
        self.executed: list[tuple[str, str]] = []
        self.execution = {"status": "complete", "text": "Done: changed what the plan said.", "rounds": 1}
        self.edits: list[str] = []          # files the "execution" writes, relative to the workspace
        self.hold: threading.Event | None = None
        self.finished: list[str] = []
        self.failed: list[str] = []
        self.stages: list[str] = []

    def begin(self, stage, role=None, run_id=""):
        self.stages.append(stage)

    def finish(self, text=""):
        self.finished.append(text)

    def fail(self, text):
        self.failed.append(text)

    def agent(self, model=""):
        return self.agent_object

    def ask_json(self, prompt, validator=None, model="", attempts=3):
        self.prompts.append(prompt)
        if self.hold is not None:
            self.hold.wait(10)
        reply = self.replies.pop(0)
        return validator(reply) if validator else reply

    def execute_approved(self, request, plan, model=""):
        self.executed.append((request, plan))
        for name in self.edits:
            target = self.workspace / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("changed", encoding="utf-8")
        return dict(self.execution)


PLAN = {"kind": "plan", "title": "Add a due date", "summary": "Tasks get a due date.",
        "impact": [{"stage": "SRS", "affected": True, "why": "new field"},
                   {"stage": "Wireframes", "affected": False, "why": "no layout change"},
                   {"stage": "Build", "affected": True, "why": "form and model"}],
        "steps": [{"stage": "SRS", "title": "Add the field", "detail": "in the data design",
                   "files": [".agentforge/srs/srs.json"]},
                  {"stage": "Build", "title": "Add it to the form", "files": ["app/tasks/page.jsx"]}],
        "assumptions": ["optional field"], "risks": [], "verification": ["build passes"]}


class ChangesTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        (self.workspace / ".agentforge" / "srs").mkdir(parents=True)
        (self.workspace / ".agentforge" / "srs" / "srs.json").write_text("{}")
        (self.workspace / "app").mkdir()
        (self.workspace / "app" / "page.jsx").write_text("x")
        self.session = FakeSession(self.workspace)
        self.events: list[dict] = []
        bus._pending_decisions.clear()
        # Each test recreates this in-memory project name. `forget()` now
        # tombstones deleted projects so late worker events cannot revive
        # them; register the intentional reuse before subscribing to events.
        bus.project_created(PROJECT)
        changes._threads.clear()
        patches = [
            mock.patch.object(changes, "session_for", lambda project: self.session),
            mock.patch.object(config, "record_dir", lambda project: self.workspace / ".agentforge"),
            mock.patch.object(changes, "_guides", lambda *args: "GUIDES"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.addCleanup(bus.subscribe(self.events.append))
        self.addCleanup(forget_project, PROJECT)

    def settle(self, change_id: str):
        thread = changes._threads.get(change_id)
        if thread:
            thread.join(10)

    def of_type(self, kind: str) -> list[dict]:
        return [e for e in self.events if e.get("type") == kind]

    def submit(self, text: str):
        result = changes.submit(PROJECT, text)
        self.settle(result["change"])
        return result["change"]


class PlanFirstTests(ChangesTestCase):
    def test_a_request_is_planned_and_shown_and_nothing_is_changed(self):
        self.session.replies = [dict(PLAN)]
        change_id = self.submit("add a due date to every task")
        state = json.loads((self.workspace / ".agentforge/changes" / f"{change_id}.json").read_text())
        self.assertEqual((state["status"], state["revision"]), ("proposed", 1))
        card = self.of_type("change")[-1]
        self.assertEqual((card["status"], card["plan"]["title"]), ("proposed", "Add a due date"))
        self.assertEqual(self.session.executed, [])                     # not carried out
        self.assertEqual(self.session.agent_object.modes[:1], ["plan"])  # planned read-only
        self.assertEqual(self.session.agent_object.modes[-1], "act")
        self.assertEqual(changes.active(PROJECT)["id"], change_id)

    def test_the_standing_instruction_and_the_project_come_from_the_prompt_not_from_code(self):
        self.session.replies = [dict(PLAN)]
        self.submit("add a due date to every task")
        prompt = " ".join(self.session.prompts[0].split())          # the file wraps its lines
        for sentence in ("Update SRS, wireframes, prototype and build only when the request actually affects them.",
                         "SRS text, Mermaid diagrams, wireframes and prototype updates are direct artifact edits with no test steps.",
                         "For build changes, plan focused unit tests only for changed or newly added business logic files; never plan the full unit suite."):
            self.assertIn(sentence, prompt)
        self.assertIn("Plan E2E and other quality layers only for a new feature or changed user-visible behavior.", prompt)
        self.assertIn("add a due date to every task", prompt)
        self.assertIn("srs.json", prompt)          # the folder listing of this project
        self.assertIn("app/", prompt)
        self.assertNotIn("{{", prompt)              # every placeholder was filled

    def test_a_plain_question_is_answered_without_a_plan_to_approve(self):
        self.session.replies = [{"kind": "answer", "answer": "It lists every task."}]
        self.submit("what does the tasks page do?")
        self.assertEqual({e["text"] for e in self.of_type("agent_msg")}, {"It lists every task."})
        self.assertIsNone(changes.active(PROJECT))
        self.assertEqual(self.of_type("change"), [])


class QuestionTests(ChangesTestCase):
    def test_the_planner_can_ask_and_the_answer_goes_into_the_next_plan(self):
        self.session.replies = [
            {"kind": "question", "question": "Which tasks get a due date?", "why": "changes the model",
             "options": [{"label": "All of them", "hint": "one field"}, "Only urgent ones"],
             "assumption": "give every task one"},
            dict(PLAN)]
        change_id = self.submit("add due dates")
        self.assertEqual(changes.active(PROJECT)["status"], "asking")
        ask = next(e for e in self.events if e.get("type") == "approval")
        self.assertEqual((ask["kind"], ask["change_id"]), ("question", change_id))
        self.assertEqual([o["label"] for o in ask["options"]], ["All of them", "Only urgent ones"])
        self.assertEqual(ask["assumption"], "give every task one")

        changes.answer(PROJECT, change_id, "All of them")
        self.settle(change_id)
        self.assertEqual(changes.active(PROJECT)["status"], "proposed")
        second = self.session.prompts[1]
        self.assertIn("Which tasks get a due date?", second)
        self.assertIn("All of them", second)

    def test_skipping_the_question_lets_the_planner_decide(self):
        self.session.replies = [{"kind": "question", "question": "Which?"}, dict(PLAN)]
        change_id = self.submit("add due dates")
        changes.answer(PROJECT, change_id, "")
        self.settle(change_id)
        self.assertIn(prompts.load("changes/unanswered").strip(), self.session.prompts[1])

    def test_after_the_cap_the_planner_is_told_to_decide_and_may_not_ask(self):
        self.assertIn("may not ask anything more", prompts.load("changes/no-questions"))
        with self.assertRaisesRegex(ValueError, "no more questions"):
            changes._check({"kind": "question", "question": "Again?"}, may_ask=False)
        self.session.replies = [{"kind": "question", "question": f"Q{n}?"} for n in range(changes.MAX_QUESTIONS)] + [dict(PLAN)]
        change_id = self.submit("add due dates")
        for _ in range(changes.MAX_QUESTIONS - 1):
            changes.answer(PROJECT, change_id, "ok")
            self.settle(change_id)
        changes.answer(PROJECT, change_id, "ok")
        self.settle(change_id)
        self.assertIn("may not ask anything more", self.session.prompts[-1])

    def test_a_question_waiting_survives_a_restart(self):
        self.session.replies = [{"kind": "question", "question": "Which?"}]
        change_id = self.submit("add due dates")
        bus._pending_decisions.clear()                                    # the server restarted
        with mock.patch.object(changes.store, "listing", lambda: [{"name": PROJECT}]):
            restored = changes.restore_questions()
        self.assertEqual([d["change_id"] for d in restored], [change_id])
        self.assertEqual(bus.pending_decisions()[0]["question"], "Which?")

    def test_two_browsers_asking_at_once_bring_the_question_back_once(self):
        self.session.replies = [{"kind": "question", "question": "Which?"}]
        self.submit("add due dates")
        bus._pending_decisions.clear()                                    # the server restarted
        with mock.patch.object(changes.store, "listing", lambda: [{"name": PROJECT}]):
            threads = [threading.Thread(target=changes.restore_questions) for _ in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
        self.assertEqual(len(bus.pending_decisions()), 1)

    def test_an_answer_from_the_chat_box_reaches_the_request_through_the_decision_route(self):
        self.session.replies = [{"kind": "question", "question": "Which?"}, dict(PLAN)]
        change_id = self.submit("add due dates")
        pending = bus.pending_decisions()[0]
        httpd.decide({"id": pending["id"], "decision": "answer", "reply": "the first one"})
        self.settle(change_id)
        self.assertEqual(changes.active(PROJECT)["status"], "proposed")
        self.assertIn("the first one", self.session.prompts[1])


class ReviseApproveCancelTests(ChangesTestCase):
    def proposed(self):
        self.session.replies = [dict(PLAN)]
        return self.submit("add a due date to every task")

    def test_typing_while_a_plan_is_shown_revises_that_plan(self):
        change_id = self.proposed()
        self.session.replies = [dict(PLAN, title="Add a due date (optional)")]
        again = self.submit("make it optional")
        self.assertEqual(again, change_id)                                # the same request
        state = changes._load(PROJECT, change_id)
        self.assertEqual(state["revision"], 2)
        prompt = self.session.prompts[-1]
        self.assertIn("make it optional", prompt)
        self.assertIn('"title": "Add a due date"', prompt)                # the plan as it stood
        self.assertEqual(self.of_type("change")[-1]["plan"]["title"], "Add a due date (optional)")

    def test_the_revise_button_sends_the_customers_words_back_to_the_planner(self):
        change_id = self.proposed()
        self.session.replies = [dict(PLAN, title="Second")]
        result = changes.decide(PROJECT, change_id, "revise", "add it to the admin page too")
        self.settle(change_id)
        self.assertTrue(result["ok"])
        self.assertIn("add it to the admin page too", self.session.prompts[-1])
        with self.assertRaises(ValueError):
            changes.decide(PROJECT, change_id, "revise", "   ")

    def test_approving_carries_the_plan_out_with_the_standing_instruction_and_full_access(self):
        change_id = self.proposed()
        self.session.edits = [".agentforge/srs/srs.json", ".agentforge/prototype/tasks.html", "app/page.jsx"]
        with mock.patch("builder_agent.build.built", lambda project: False):
            changes.decide(PROJECT, change_id, "approve")
            self.settle(change_id)
        request, plan = self.session.executed[0]
        flat = " ".join(request.split())
        self.assertIn("Follow the plan in order and change only affected files.", flat)
        self.assertIn("Keep derived artifacts consistent when their source changes.", flat)
        self.assertIn("Do not create or run tests for SRS text, Mermaid diagram, wireframe or prototype-only updates.", flat)
        self.assertIn("For build updates, add or run focused unit tests only for changed or newly added business logic files; never run the full unit suite.", flat)
        self.assertIn("add a due date to every task", request)
        self.assertIn("GUIDES", request)
        self.assertIn("Add the field", plan)
        self.assertIn("Wireframes: not affected", plan)
        self.assertEqual(changes._load(PROJECT, change_id)["status"], "done")
        self.assertIsNone(changes.active(PROJECT))
        seen = [e["status"] for e in self.of_type("change")]
        once = [status for i, status in enumerate(seen) if i == 0 or status != seen[i - 1]]   # each event is mirrored to both roles
        self.assertEqual(once, ["proposed", "approved", "running", "done"])
        # The studio is told which stages' files changed, from the folders they are in.
        self.assertTrue(self.of_type("prototype"))
        self.assertTrue([e for e in self.of_type("sync_state") if e.get("source") == "change"])

    def test_excluding_a_stage_drops_its_steps_before_execution(self):
        change_id = self.proposed()
        changes.decide(PROJECT, change_id, "approve", excluded_stages=["Build"])
        self.settle(change_id)
        request, plan = self.session.executed[0]
        self.assertIn("Add the field", plan)
        self.assertNotIn("Add it to the form", plan)
        self.assertIn("Build: not affected", plan)
        self.assertEqual(changes._load(PROJECT, change_id)["excluded_stages"], ["Build"])
        self.assertEqual(changes._load(PROJECT, change_id)["status"], "done")

    def test_excluding_every_affected_stage_finishes_without_executing(self):
        change_id = self.proposed()
        changes.decide(PROJECT, change_id, "approve", excluded_stages=["SRS", "Build"])
        self.settle(change_id)
        self.assertEqual(self.session.executed, [])
        state = changes._load(PROJECT, change_id)
        self.assertEqual(state["status"], "done")
        self.assertIn("Nothing left to build", state["summary"])

    def test_a_blocked_run_is_a_failed_change_not_a_done_one(self):
        change_id = self.proposed()
        self.session.execution = {"status": "blocked", "text": "no database", "rounds": 2}
        changes.decide(PROJECT, change_id, "approve")
        self.settle(change_id)
        self.assertEqual(changes._load(PROJECT, change_id)["status"], "failed")
        self.assertEqual(self.session.failed, ["no database"])

    def test_cancel_drops_the_plan(self):
        change_id = self.proposed()
        changes.decide(PROJECT, change_id, "cancel")
        self.assertEqual(changes._load(PROJECT, change_id)["status"], "cancelled")
        self.assertIsNone(changes.active(PROJECT))
        self.assertEqual(self.of_type("change")[-1]["status"], "cancelled")
        self.assertEqual(self.session.executed, [])

    def test_a_plan_that_is_not_waiting_cannot_be_approved_twice(self):
        change_id = self.proposed()
        changes.decide(PROJECT, change_id, "approve")
        self.settle(change_id)
        self.assertFalse(changes.decide(PROJECT, change_id, "approve")["ok"])
        self.assertEqual(len(self.session.executed), 1)

    def test_a_new_request_while_one_is_being_worked_on_is_refused(self):
        self.session.hold = threading.Event()
        self.session.replies = [dict(PLAN)]
        first = changes.submit(PROJECT, "add a due date")["change"]
        with self.assertRaisesRegex(ValueError, "still being worked on"):
            changes.submit(PROJECT, "and rename the page")
        self.session.hold.set()
        self.settle(first)

    def test_a_request_the_server_died_on_does_not_block_the_next_one(self):
        stale = {"id": "chg-old", "project": PROJECT, "request": "x", "status": "running", "revision": 0,
                 "asked": 0, "plan": None, "history": [{"role": "user", "kind": "request", "text": "x"}]}
        changes._save(stale)
        changes._set_active(PROJECT, "chg-old")
        self.session.replies = [dict(PLAN)]
        fresh = self.submit("add a due date")
        self.assertNotEqual(fresh, "chg-old")
        self.assertEqual(changes._load(PROJECT, "chg-old")["status"], "failed")


class ReplyShapeTests(unittest.TestCase):
    def test_what_the_model_returns_is_checked_and_the_error_is_the_repair_prompt(self):
        with self.assertRaisesRegex(ValueError, "kind"):
            changes._check({"kind": "banana"}, True)
        with self.assertRaisesRegex(ValueError, "steps"):
            changes._check({"kind": "plan", "title": "t", "summary": "s",
                            "impact": [{"stage": "SRS", "affected": True}]}, True)
        with self.assertRaisesRegex(ValueError, "impact"):
            changes._check({"kind": "plan", "title": "t", "summary": "s", "steps": [{"title": "x"}]}, True)
        with self.assertRaisesRegex(ValueError, "JSON object"):
            changes._check(["not", "an", "object"], True)
        clean = changes._check(dict(PLAN, impact=PLAN["impact"] + [{"stage": " "}, "junk"]), True)
        self.assertEqual(len(clean["impact"]), 3)                          # blank and malformed rows dropped

    def test_the_plan_reads_as_markdown_for_the_agent_that_carries_it_out(self):
        text = changes.plan_markdown(changes._check(dict(PLAN), True))
        self.assertIn("1. [SRS] Add the field", text)
        self.assertIn("- .agentforge/srs/srs.json", text)
        self.assertIn("## Assumptions", text)
        self.assertNotIn("## Risks", text)                                 # empty sections are left out


class RoutingTests(unittest.TestCase):
    def test_chat_requests_are_planned_when_there_is_a_specification_and_answered_directly_when_not(self):
        with mock.patch.object(runs.changes, "applies", lambda project: True), \
                mock.patch.object(runs.changes, "submit", lambda *a, **k: {"planned": True}), \
                mock.patch.object(runs, "agent_update_direct", lambda message: {"planned": False}):
            self.assertEqual(runs.agent_update({"project": "p", "prompt": "change it"}), {"planned": True})
        with mock.patch.object(runs.changes, "applies", lambda project: False), \
                mock.patch.object(runs, "agent_update_direct", lambda message: {"planned": False}):
            self.assertEqual(runs.agent_update({"project": "p", "prompt": "change it"}), {"planned": False})

    def test_the_prompt_pack_carries_the_instructions(self):
        for name in ("plan", "execute", "unanswered", "history", "previous-plan", "questions-left", "no-questions"):
            self.assertTrue(prompts.exists(f"changes/{name}"), name)
        plan = prompts.load("changes/plan")
        for word in ('"kind":"answer"', '"kind":"question"', '"kind":"plan"', "Project artifacts"):
            self.assertIn(word, plan)


class PlanModeTests(unittest.TestCase):
    """Phase 7: a real per-project plan on/off toggle, feeding `applies()`
    exactly where routing already decides plan-first vs. direct apply."""

    def test_a_project_that_never_set_it_keeps_todays_always_on_behavior(self):
        with mock.patch.object(changes.store, "get", return_value={"id": "p"}), \
             mock.patch("srs_agent.document.has_document", return_value=True):
            self.assertTrue(changes.applies("p"))

    def test_plan_mode_off_skips_planning_even_with_a_specification(self):
        with mock.patch.object(changes.store, "get", return_value={"id": "p", "plan_mode": False}), \
             mock.patch("srs_agent.document.has_document", return_value=True):
            self.assertFalse(changes.applies("p"))

    def test_plan_mode_on_is_unaffected(self):
        with mock.patch.object(changes.store, "get", return_value={"id": "p", "plan_mode": True}), \
             mock.patch("srs_agent.document.has_document", return_value=True):
            self.assertTrue(changes.applies("p"))

    def test_a_project_with_no_specification_still_never_plans_either_way(self):
        with mock.patch.object(changes.store, "get", return_value={"id": "p", "plan_mode": True}), \
             mock.patch("srs_agent.document.has_document", return_value=False):
            self.assertFalse(changes.applies("p"))

    def test_the_route_toggles_it_and_workflow_reports_it(self):
        with tempfile.TemporaryDirectory() as folder:
            original = config.PROJECTS_FILE
            config.PROJECTS_FILE = Path(folder) / "projects.json"
            original_workspaces = config.WORKSPACES
            config.WORKSPACES = Path(folder) / "workspaces"
            try:
                from server_modules import store
                record = store.create("an idea")
                project = record["id"]
                match = mock.Mock(group=lambda name: project)

                seen = httpd.workflow({"_match": match})
                self.assertTrue(seen["plan_mode"])   # never set yet -> on

                result = httpd.set_plan_mode({"_match": match, "enabled": False})
                self.assertFalse(result["plan_mode"])

                seen = httpd.workflow({"_match": match})
                self.assertFalse(seen["plan_mode"])
            finally:
                config.PROJECTS_FILE = original
                config.WORKSPACES = original_workspaces
                forget_project(project)


if __name__ == "__main__":
    unittest.main()
