"""The Overview tells the app to someone who is not technical: a model writes it once from the specification, in plain words,
and writes it again only when the specification changes."""
from __future__ import annotations

import json
import sys
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
from srs_agent import plain_summary  # noqa: E402

WRITTEN = {
    "headline": "A simple way for one company to follow every item from the supplier to each shop.",
    "story": ["Today stock is counted on paper.", "With the app, every move is recorded."],
    "people": [{"who": "Head office staff", "does": "Order stock and send it to the shops."}],
    "what_you_can_do": [{"area": "Selling at the counter", "points": ["Ring up a sale.", "Give a receipt."]}],
    "a_day_with_it": [{"title": "A delivery arrives", "steps": ["The manager counts the boxes.", "The shop's stock goes up."]}],
    "how_it_feels": [{"topic": "Fast", "plain": "A sale is done in a second or two."}],
    "keeping_safe": ["Only the right people see each shop's figures."],
    "what_the_business_gets": ["Fewer lost items."],
}


class Case(unittest.TestCase):
    def setUp(self):
        self.envelope = {"srs_document": {
            "app_summary": {"app_name": "Stock", "short_description": "Follows stock.", "business_goal": "Lose less."},
            "roles": [{"role_name": "Admin", "description": "Runs head office."}],
            "functional_requirements": [{"id": "FR-001", "module": "Sales", "requirement": "The system shall record a sale."}],
            "non_functional_requirements": [{"id": "NFR-001", "category": "Performance", "requirement": "Checkout in 1500 ms."}],
            "security_requirements": ["Every page checks the role on the server."]}}
        self.asked: list[str] = []
        session = SimpleNamespace(write_record=self.write)
        for patch in (mock.patch.object(plain_summary.srs_document, "document", lambda project: json.loads(json.dumps(self.envelope))),
                      mock.patch.object(plain_summary, "session_for", lambda project: session),
                      mock.patch.object(plain_summary.store, "get", lambda project: {"language": "English"}),
                      mock.patch.object(bus, "log", lambda *a, **k: None)):
            self.enterContext(patch)

    def write(self, *parts, data):
        self.envelope = json.loads(json.dumps(data))

    def model(self, reply=WRITTEN):
        def complete_json(**kw):
            self.asked.append(kw["user"])
            return kw["validator"](json.loads(json.dumps(reply)))
        return mock.patch.object(plain_summary.llm, "complete_json", side_effect=complete_json)


class SummaryTests(Case):
    def test_it_is_written_once_and_kept(self):
        self.assertEqual(plain_summary.read("p")["status"], "missing")
        with self.model():
            made = plain_summary.write("p")
            plain_summary.write("p")
        self.assertEqual(len(self.asked), 1)
        self.assertEqual(made["status"], "ready")
        self.assertEqual(made["what_you_can_do"][0]["area"], "Selling at the counter")
        self.assertEqual(plain_summary.read("p")["status"], "ready")

    def test_a_changed_specification_makes_it_stale_and_it_is_written_again(self):
        with self.model():
            plain_summary.write("p")
            self.envelope["srs_document"]["functional_requirements"].append(
                {"id": "FR-002", "module": "Sales", "requirement": "The system shall print a receipt."})
            self.assertEqual(plain_summary.read("p")["status"], "stale")
            plain_summary.write("p")
        self.assertEqual(len(self.asked), 2)
        self.assertEqual(plain_summary.read("p")["status"], "ready")

    def test_the_model_is_given_the_whole_specification_and_told_to_use_no_technical_words(self):
        with self.model():
            plain_summary.write("p")
        prompt = self.asked[0]
        for needle in ("The system shall record a sale.", "Checkout in 1500 ms.", "Runs head office.", "not technical at all",
                       "No technical terms"):
            self.assertIn(needle, prompt)

    def test_an_answer_without_its_main_parts_is_refused_so_the_model_tries_again(self):
        with self.assertRaises(ValueError):
            plain_summary._clean({"headline": "x", "story": [], "what_you_can_do": []})

    def test_a_model_that_cannot_be_reached_says_so_and_keeps_what_was_there(self):
        with mock.patch.object(plain_summary.llm, "complete_json", side_effect=RuntimeError("down")):
            self.assertEqual(plain_summary.write("p")["status"], "failed")

    def test_the_routes_reach_it(self):
        with self.model():
            self.assertEqual(routes_srs.dispatch("POST", "/projects/p/plain-summary", {})["status"], "ready")
        self.assertEqual(routes_srs.dispatch("GET", "/projects/p/plain-summary")["status"], "ready")


if __name__ == "__main__":
    unittest.main()
