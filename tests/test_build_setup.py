"""Before a build is planned, it settles with the customer everything it needs from them.

The questions are the model's own; this checks the flow around them: asked one at a time before anything is
built, every answer carried into the next turn, the database carried out exactly as settled, a setup that fails
turned into a question, and what was settled handed to the build so it is never asked again.
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
for folder in (".", "builder-agent", "srs-agent", "prototype-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import build, setup  # noqa: E402
from server_modules import bus  # noqa: E402
from support import isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


PROJECT = "prj_build_setup_test"
REAL_BUILD = build._build
FACTS = {"supabase": {"this_project": None,
                      "account": {"connected": True, "organizations": [{"id": "org-free", "name": "Mine", "plan": "free"}],
                                  "projects": []}}}
READY = {"kind": "ready", "database": {"supabase": {"use": "new", "organization": "org-free", "region": "ap-south-1"}},
         "decisions": ["A new Supabase project on the free plan, in Mumbai"]}


class Agent:
    def __init__(self):
        self.modes = []

    def set_mode(self, mode):
        self.modes.append(mode)


class FakeSession:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.lock = threading.RLock()
        self.replies: list = []
        self.prompts: list[str] = []
        self.finished: list[str] = []
        self.failed: list[str] = []
        self._agent = Agent()

    def begin(self, stage, role=None, run_id=""):
        pass

    def finish(self, text=""):
        self.finished.append(text)

    def fail(self, text):
        self.failed.append(text)

    def agent(self, model=""):
        return self._agent

    def ask_json(self, prompt, validator=None, model="", attempts=3):
        self.prompts.append(prompt)
        return validator(self.replies.pop(0))

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path


class SetupFlowCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = FakeSession(Path(self.temp.name))
        bus._pending_decisions.clear()
        self.built = []
        for target, value in [
            (mock.patch.object(build, "session_for", lambda project: self.session), None),
            (mock.patch.object(build.store, "require", return_value={"stack": "nextjs-supabase", "name": "Shop"}), None),
            (mock.patch.object(setup, "facts", return_value=FACTS), None),
            (mock.patch.object(build, "_build", lambda project, session, state: self.built.append(state)
                               or {"status": "building"}), None),
            (mock.patch("srs_agent.document.has_document", return_value=True), None),
            (mock.patch("srs_agent.document.document", return_value={"srs_document": {}}), None),
        ]:
            self.enterContext(target)

    def question(self, text, **extra):
        return {"kind": "question", "question": text, "why": "", "assumption": "",
                "options": [{"label": "Yes"}, {"label": "No"}], **extra}


class SetupTests(SetupFlowCase):
    def test_the_build_asks_its_own_questions_before_anything_is_planned(self):
        self.session.replies.append(self.question("Where should this shop's data live?"))
        result = build.run(PROJECT)
        self.assertEqual(result["status"], "asking")
        self.assertEqual(self.built, [])
        self.assertEqual(build.waiting(PROJECT)["mode"], "setup")
        decision = bus.pending_decisions()[0]
        self.assertEqual((decision["flow"], decision["question"]), ("build", "Where should this shop's data live?"))
        self.assertEqual(self.session._agent.modes, ["plan", "act"])
        self.assertIn('"org-free"', self.session.prompts[0])

    def test_each_answer_reaches_the_next_turn_and_the_build_starts_once_settled(self):
        self.session.replies += [self.question("Where should this shop's data live?"), READY]
        build.run(PROJECT, direction="make it quick")
        result = build.answer(PROJECT, "A new free project in Mumbai")
        self.assertEqual(result, {"status": "building"})
        self.assertIn("Q: Where should this shop's data live?\n  A: A new free project in Mumbai", self.session.prompts[1])
        self.assertIn("make it quick", self.session.prompts[1])
        state = self.built[0]
        self.assertEqual(state["database"]["supabase"], {"use": "new", "organization": "org-free", "region": "ap-south-1"})
        self.assertEqual(state["decisions"], READY["decisions"])
        self.assertIsNone(build.waiting(PROJECT))

    def test_a_secret_is_asked_for_in_the_private_box(self):
        self.session.replies.append(self.question("What is the Stripe secret key for this shop?"))
        build.run(PROJECT)
        decision = bus.pending_decisions()[0]
        self.assertTrue(decision["secret"])
        self.assertEqual(decision["variable"], "STRIPE_SECRET_KEY")

    def test_a_supabase_value_is_never_asked_when_the_project_is_connected(self):
        self.session.replies += [self.question("Paste the Supabase anon key", variable="SUPABASE_ANON_KEY", secret=True),
                                 READY]
        with mock.patch.object(build.supabase_connect, "record", return_value={"ref": "abc"}):
            result = build.run(PROJECT)
        self.assertEqual(result, {"status": "building"})
        self.assertEqual(bus.pending_decisions(), [])
        self.assertIn("already connected", self.session.prompts[1])

    def test_the_slow_account_facts_are_read_once_per_setup(self):
        setup.facts.side_effect = None
        self.session.replies += [self.question("Free or paid?"), READY]
        with mock.patch.object(setup, "facts", wraps=lambda project, stack, earlier=None: earlier or FACTS) as facts:
            build.run(PROJECT)
            build.answer(PROJECT, "Free")
        self.assertIsNone(facts.call_args_list[0].args[2])
        self.assertEqual(facts.call_args_list[1].args[2], FACTS)

    def test_a_fresh_project_still_gets_its_template_after_the_setup(self):
        """The setup stages the stack's guides before the build installs the template: they go in the record
        folder, never the app root, where any folder made `scaffold.install` keep a fresh workspace as it is."""
        from builder_agent import scaffold

        installed = []
        self.enterContext(mock.patch.object(
            build, "_build", lambda project, session, state:
            installed.append(scaffold.install(session.workspace, "nextjs-supabase")) or {"status": "building"}))
        self.session.replies.append(READY)
        build.run(PROJECT)
        self.assertTrue(installed[0]["scaffolded"], installed[0].get("existing"))
        self.assertTrue((self.session.workspace / ".agentforge" / "build" / "guides" / "pitfalls.md").is_file())
        self.assertFalse((self.session.workspace / "build").exists())

    def test_an_earlier_builds_settled_decisions_are_not_asked_again(self):
        self.session.write_record(*build.SETUP, data={"status": "ready", "decisions": ["Keep the Mumbai project"]})
        self.session.replies.append(READY)
        build.run(PROJECT)
        self.assertIn("Keep the Mumbai project", self.session.prompts[0])


class DatabaseFailureTests(SetupFlowCase):
    def test_a_database_that_cannot_be_set_up_becomes_a_question(self):
        self.enterContext(mock.patch.object(build, "_build", REAL_BUILD))
        self.session.replies += [READY, self.question("The free plan already has two projects. What should we do?")]
        with mock.patch.object(setup, "apply", side_effect=ValueError("free plan limit: 2 active projects")):
            result = build.run(PROJECT)
        self.assertEqual(result["status"], "asking")
        self.assertIn("free plan limit: 2 active projects", self.session.prompts[1])
        self.assertEqual(build._setup_state(self.session)["failures"], 1)


class CheckTests(unittest.TestCase):
    def test_a_question_is_cleaned_like_every_other_question(self):
        asked = setup.check({"kind": "question", "question": "Free or paid?", "options": ["Free", "Paid"]},
                            True, "nextjs-supabase", FACTS)
        self.assertEqual([o["label"] for o in asked["options"]], ["Free", "Paid"])
        with self.assertRaisesRegex(ValueError, "no more questions"):
            setup.check({"kind": "question", "question": "One more?"}, False, "nextjs-supabase", FACTS)

    def test_the_database_must_be_something_that_can_be_carried_out(self):
        with self.assertRaisesRegex(ValueError, "no Supabase project yet"):
            setup.check({**READY, "database": {"supabase": {"use": "this"}}}, True, "nextjs-supabase", FACTS)
        with self.assertRaisesRegex(ValueError, "organization ids"):
            setup.check({**READY, "database": {"supabase": {"use": "new", "organization": "org-other"}}},
                        True, "nextjs-supabase", FACTS)
        mongo_facts = {**FACTS, "mongodb": {"atlas_connected": False, "connection_string_saved": False}}
        base = {"supabase": READY["database"]["supabase"]}
        with self.assertRaisesRegex(ValueError, "no Atlas account"):
            setup.check({**READY, "database": {**base, "mongodb": {"use": "atlas"}}}, True, "vite-mongo", mongo_facts)
        with self.assertRaisesRegex(ValueError, "no connection string is saved"):
            setup.check({**READY, "database": {**base, "mongodb": {"use": "saved"}}}, True, "vite-mongo", mongo_facts)
        ready = setup.check({**READY, "database": {**base, "mongodb": {"use": "local"}}}, True, "vite-mongo", mongo_facts)
        self.assertEqual(ready["database"]["mongodb"]["use"], "local")

    def test_where_the_data_lives_is_carried_out_exactly(self):
        database = {"supabase": {"use": "new", "organization": "org-pro", "region": "eu-west-2"},
                    "mongodb": {"use": "atlas", "region": "EU_WEST_2"}}
        with mock.patch.object(setup.supabase_connect, "record", return_value={"ref": "old"}), \
             mock.patch.object(setup.supabase_connect, "ensure_project") as ensure, \
             mock.patch.object(setup.mongo_connect, "ensure_cluster") as cluster:
            setup.apply(PROJECT, "Shop", database, say=print)
        self.assertEqual(ensure.call_args.kwargs | {"log": None},
                         {"name": "Shop", "log": None, "region": "eu-west-2", "org_id": "org-pro", "fresh": True})
        self.assertEqual(cluster.call_args.kwargs["region"], "EU_WEST_2")

    def test_what_was_settled_is_handed_to_the_build(self):
        text = setup.settled_block({"answers": [{"question": "Demo accounts or yours?", "answer": "Demo"}],
                                    "decisions": ["A new free Supabase project"]})
        self.assertIn("do not ask any of them again", text)
        self.assertIn("Q: Demo accounts or yours?\n  A: Demo", text)
        self.assertIn("- A new free Supabase project", text)
        self.assertEqual(setup.settled_block({}), "")



class AnswerInBackgroundTests(unittest.TestCase):
    def test_an_answer_carries_on_in_the_background(self):
        from server_modules import runs

        done = threading.Event()
        calls = []

        def answer(project, reply):
            calls.append((project, reply, threading.current_thread().name))
            done.set()

        with mock.patch.object(runs.builder, "answer", answer):
            self.assertEqual(runs.answer_build(PROJECT, "Free plan"), {"ok": True})
            self.assertTrue(done.wait(5))
        self.assertEqual(calls[0][:2], (PROJECT, "Free plan"))
        self.assertEqual(calls[0][2], f"build:{PROJECT}")


if __name__ == "__main__":
    unittest.main()
