"""The specification's open decisions are asked as questions in their own tab and settled by the customer's answers.

Choosing the assumption settles a decision at once; another answer settles it too and is written into the specification by
the agent once no other run is working; an answer that could not be written in opens the decision again, saying so.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import bus, routes_srs  # noqa: E402
from srs_agent import decisions  # noqa: E402


def amb(ident, area="Customers", open_=True, **extra):
    return {"id": ident, "area": area, "description": f"{area} is not defined.", "assumption_made": f"{area} belongs to a branch.",
            "needs_clarification": open_, **extra}


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name)
        self.envelope = {"srs_document": {"ambiguities": [amb("AMB-001"), amb("AMB-002", "Sessions"), amb("AMB-003", open_=False,
                                                                                                         resolution="Done")]}}
        self.saved: list[dict] = []
        self.said: list[str] = []
        self.session = SimpleNamespace(write_record=self.write, begin=lambda stage: None, finish=lambda text="": None,
                                       fail=lambda text="": None, run_task=lambda request, **kw: {"status": "complete"})
        for patch in (mock.patch.object(decisions.srs_document, "document", lambda project: json.loads(json.dumps(self.envelope))),
                      mock.patch.object(decisions, "session_for", lambda project: self.session),
                      mock.patch.object(decisions.store, "get", lambda project: {"language": "English"}),
                      mock.patch.object(bus, "sync_state", lambda *a, **k: None),
                      mock.patch.object(bus, "agent_msg", lambda project, text, **kw: self.said.append(text)),
                      mock.patch.object(bus, "log", lambda *a, **k: None),
                      mock.patch.object(decisions, "_resume", lambda project: None)):
            self.enterContext(patch)

    def write(self, *parts, data):
        self.envelope = json.loads(json.dumps(data))
        self.saved.append(self.envelope)

    def entry(self, ident):
        return next(a for a in self.envelope["srs_document"]["ambiguities"] if a["id"] == ident)


class ListingTests(Case):
    def test_open_decisions_are_questions_and_settled_ones_show_their_answer(self):
        listing = decisions.listing("p")
        self.assertEqual([d["id"] for d in listing["open"]], ["AMB-001", "AMB-002"])
        self.assertEqual(listing["count"], 2)
        first = listing["open"][0]
        self.assertIn("Customers is not defined.", first["question"])
        self.assertEqual(first["options"], ["Keep the assumption: Customers belongs to a branch."])
        self.assertEqual(listing["settled"], [{"id": "AMB-003", "area": "Customers", "question": "Customers: Customers is not defined.",
                                              "answer": "Done", "by": "", "applying": False}])

    def test_the_questions_are_written_once_by_a_model_and_kept(self):
        written = {"decisions": [{"id": "AMB-001", "question": "Does each customer belong to one branch?",
                                  "options": ["Yes, to the branch that added them", "No, customers are shared by every branch"]},
                                 {"id": "AMB-002", "question": "Should sign-ins be kept?", "options": ["Yes", "No"]}]}
        with mock.patch.object(decisions.llm, "complete_json", side_effect=lambda **kw: kw["validator"](written)) as asked:
            listing = decisions.prepare("p")
            decisions.prepare("p")
        self.assertEqual(asked.call_count, 1)                         # kept: not written again
        self.assertEqual(listing["open"][0]["question"], "Does each customer belong to one branch?")
        self.assertEqual(len(listing["open"][0]["options"]), 2)

    def test_a_model_that_cannot_answer_leaves_each_decision_asked_as_written(self):
        with mock.patch.object(decisions.llm, "complete_json", side_effect=RuntimeError("down")):
            listing = decisions.prepare("p")
        self.assertEqual(listing["open"][0]["options"], ["Keep the assumption: Customers belongs to a branch."])


class AnsweringTests(Case):
    def setUp(self):
        super().setUp()
        self.entry("AMB-001")["options"] = ["Yes, to the branch that added them", "No, shared by every branch"]

    def test_keeping_the_assumption_settles_it_at_once_and_the_count_goes_down(self):
        listing = decisions.answer("p", "AMB-001", "Yes, to the branch that added them", option=0)
        self.assertEqual(listing["count"], 1)
        entry = self.entry("AMB-001")
        self.assertFalse(entry["needs_clarification"])
        self.assertNotIn(decisions.APPLYING, entry)

    def test_another_answer_settles_it_and_waits_to_be_written_into_the_specification(self):
        with mock.patch.object(decisions, "_resume") as resume:
            listing = decisions.answer("p", "AMB-001", "No, shared by every branch", option=1)
        self.assertEqual(listing["count"], 1)
        self.assertTrue(self.entry("AMB-001")[decisions.APPLYING])
        self.assertEqual(listing["settled"][0]["applying"], True)
        resume.assert_called_once_with("p")

    def test_own_words_are_an_answer_too(self):
        decisions.answer("p", "AMB-002", "Keep sign-ins for 90 days")
        self.assertEqual(self.entry("AMB-002")["resolution"], "Keep sign-ins for 90 days")

    def test_an_empty_answer_or_a_settled_decision_is_refused(self):
        with self.assertRaisesRegex(ValueError, "choose one of the answers"):
            decisions.answer("p", "AMB-001", "  ")
        with self.assertRaisesRegex(ValueError, "already settled"):
            decisions.answer("p", "AMB-003", "Something")


class WritingInTests(Case):
    def setUp(self):
        super().setUp()
        self.entry("AMB-001").update(needs_clarification=False, resolution="No, shared", **{decisions.APPLYING: True})

    def test_a_written_answer_stays_settled_even_when_the_agent_rewrote_the_decisions(self):
        def rewrite(request, **kw):
            self.envelope["srs_document"]["ambiguities"] = [amb("AMB-002", "Sessions")]     # the agent dropped AMB-001
            return {"status": "complete"}

        self.session.run_task = rewrite
        decisions.apply_answers("p")
        entry = self.entry("AMB-001")
        self.assertFalse(entry["needs_clarification"])
        self.assertEqual(entry["resolution"], "No, shared")
        self.assertNotIn(decisions.APPLYING, entry)
        self.assertIn("are in the specification", self.said[-1])

    def test_an_answer_that_could_not_be_written_in_opens_the_decision_again_saying_so(self):
        self.session.run_task = lambda request, **kw: {"status": "blocked", "text": "the model service was down"}
        decisions.apply_answers("p")
        entry = self.entry("AMB-001")
        self.assertTrue(entry["needs_clarification"])
        self.assertIn("Choose it again", entry[decisions.FAILED])
        self.assertEqual(decisions.listing("p")["open"][0]["error"], entry[decisions.FAILED])

    def test_the_request_names_each_answer(self):
        seen = []
        self.session.run_task = lambda request, **kw: seen.append(request) or {"status": "complete"}
        decisions.apply_answers("p")
        self.assertIn("AMB-001", seen[0])
        self.assertIn("No, shared", seen[0])


class RouteTests(Case):
    def test_the_routes_reach_the_decisions(self):
        with mock.patch.object(routes_srs.privacy, "screen", lambda project, text: text):
            self.assertEqual(routes_srs.dispatch("GET", "/projects/p/decisions")["count"], 2)
            listing = routes_srs.dispatch("POST", "/projects/p/decisions/AMB-002", {"answer": "Keep them", "option": None})
        self.assertEqual(listing["count"], 1)


if __name__ == "__main__":
    unittest.main()
