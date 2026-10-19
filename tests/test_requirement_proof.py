"""A requirement is met, failed or untested by the Studio's reading of the test results, never by what the builder wrote.

One store's 116 requirements were all still "untested" in the build report after every unit and journey test had passed,
and the Testing screen said 0/116 met.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "qa-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import journeys  # noqa: E402
from qa_agent import requirement_proof  # noqa: E402


class ProofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        srs = self.workspace / ".agentforge" / "srs"
        srs.mkdir(parents=True)
        (srs / "srs.json").write_text(json.dumps({"srs_document": {"requirement_traceability_matrix": [
            {"requirement_id": "FR-001", "pages": ["/login", "/branches"]},
            {"requirement_id": "FR-002", "pages": ["/orders/[id]"]},
            {"requirement_id": "FR-003", "pages": ["/customers"]},
            {"requirement_id": "FR-004", "pages": ["/suppliers"]},
        ]}}), encoding="utf-8")
        (self.workspace / journeys.JOURNEY_ARTIFACT).parent.mkdir(parents=True, exist_ok=True)
        (self.workspace / journeys.JOURNEY_ARTIFACT).write_text(json.dumps({"schema": journeys.JOURNEY_SCHEMA, "journeys": [
            {"id": "UJ-001", "steps": [{"route": "/login"}, {"route": "/Branches/"}]},
            {"id": "UJ-002", "steps": [{"route": "/login"}, {"route": "/orders/[orderId]"}]},
        ]}), encoding="utf-8")
        self.coverage = {"journeys": [{"id": "UJ-001", "status": "passed", "tests": [1]},
                                      {"id": "UJ-002", "status": "failed", "tests": [1]}]}

    def test_journeys_through_its_pages_decide_and_a_page_no_journey_reaches_is_untested(self):
        found = requirement_proof.statuses(self.workspace, self.coverage)
        self.assertEqual({k: v["status"] for k, v in found.items()},
                         {"FR-001": "met", "FR-002": "failed", "FR-003": "untested", "FR-004": "untested"})
        self.assertIn("UJ-001", found["FR-001"]["evidence"])
        self.assertIn("/customers", found["FR-003"]["evidence"])

    def test_a_test_that_names_the_requirement_decides_it_and_phone_width_does_not_count(self):
        tests = [{"title": "[FR-003] lists the branch's customers", "status": "passed", "project": "desktop", "file": "c.spec.js"},
                 {"title": "[FR-004] lists the suppliers", "status": "failed", "project": "desktop", "file": "s.spec.js"},
                 {"title": "[FR-002] opens an order", "status": "passed", "project": "mobile", "file": "o.spec.js"}]
        found = requirement_proof.statuses(self.workspace, self.coverage, tests)
        self.assertEqual((found["FR-003"]["status"], found["FR-004"]["status"], found["FR-002"]["status"]),
                         ("met", "failed", "failed"))

    def test_the_build_report_is_set_from_the_results(self):
        build = {"requirements": [{"id": "FR-001", "status": "untested", "evidence": "No behavioural test yet"}]}
        self.assertEqual(requirement_proof.apply(self.workspace, build, self.coverage), 1)
        self.assertEqual((build["requirements"][0]["status"], build["requirements"][0]["decided_by"]), ("met", "studio"))

    def test_without_journey_results_nothing_is_decided(self):
        self.assertEqual(requirement_proof.statuses(self.workspace, None), {})


if __name__ == "__main__":
    unittest.main()
