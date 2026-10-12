"""No interview: the plan is written from the idea and the chosen stack, and says what it assumed."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", ".deps/py312"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, routes_srs, store  # noqa: E402
from srs_agent import interview  # noqa: E402

PROJECT = "prj_skip_test"


class FakeSession:
    def __init__(self):
        self.records: dict[tuple, object] = {}
        self.notes: list[str] = []
        self.role = ""

    def read_record(self, *parts, fallback=None):
        return self.records.get(parts, fallback)

    def write_record(self, *parts, data=None):
        self.records[parts] = data

    def note(self, text):
        self.notes.append(text)


class SkipTests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.advanced: list[tuple] = []
        for patch in (mock.patch.object(interview, "session_for", lambda project: self.session),
                      mock.patch.object(store, "advance", lambda project, stage: self.advanced.append((project, stage))),
                      mock.patch.object(bus, "log", lambda *a, **k: None),
                      mock.patch.object(bus, "agent_state", lambda *a, **k: None)):
            patch.start()
            self.addCleanup(patch.stop)

    def test_skipping_ends_the_interview_and_moves_the_project_to_the_plan(self):
        view = interview.skip(PROJECT)
        self.assertTrue(view["done"])
        self.assertIsNone(view["question"])
        self.assertEqual(self.advanced, [(PROJECT, "plan")])
        self.assertEqual(len(self.session.notes), 1)

    def test_the_plan_is_told_nothing_was_asked_instead_of_reading_an_empty_interview(self):
        interview.skip(PROJECT)
        said = interview.transcript_text(interview.state(self.session))
        self.assertIn("chose not to be interviewed", said)
        self.assertIn("state each of those decisions as an assumption", said)
        self.assertNotEqual(said, "(nothing yet)")

    def test_what_was_answered_before_is_kept(self):
        data = interview.state(self.session)
        data["transcript"] = [{"id": "app_type", "question": "What kind of product?"}]
        data["answers"]["app_type"] = {"question_id": "app_type", "text": "A booking site", "value": "booking"}
        data["order"] = ["app_type"]
        interview.save(self.session, data)
        interview.skip(PROJECT)
        said = interview.transcript_text(interview.state(self.session))
        self.assertIn("A booking site", said)
        self.assertIn("chose not to be interviewed", said)

    def test_skipping_twice_changes_nothing_the_second_time(self):
        interview.skip(PROJECT)
        interview.skip(PROJECT)
        self.assertEqual(self.advanced, [(PROJECT, "plan")])
        self.assertEqual(interview.state(self.session)["order"].count(interview.SKIPPED_ID), 1)

    def test_it_is_a_route_of_the_srs_router_and_the_interview_screen_uses_it_when_nothing_was_answered(self):
        with mock.patch.object(interview, "skip", return_value={"done": True}) as skipped:
            self.assertEqual(routes_srs.dispatch("POST", f"/projects/{PROJECT}/interview/skip", {}), {"done": True})
        skipped.assert_called_once_with(PROJECT)
        screen = (ROOT / "studio/components/srs/Interview.jsx").read_text(encoding="utf-8")
        self.assertIn("/interview/skip", screen)


if __name__ == "__main__":
    unittest.main()
