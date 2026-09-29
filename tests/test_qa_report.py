"""Compatibility tests for the QA report handoff between agent and Studio."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server_modules.qa_report import summary_counts  # noqa: E402


class QaReportShapeTests(unittest.TestCase):
    def test_machine_summary_keeps_the_exact_counts(self):
        self.assertEqual(summary_counts({"summary": {"pass": 103, "fail": 0, "warn": 2}}),
                         {"pass": 103, "fail": 0, "warn": 2})

    def test_prose_summary_uses_the_structured_layer_outcomes(self):
        report = {
            "summary": "All checks completed and the evidence is recorded.",
            "layers": [
                {"status": "passed"}, {"status": "passed"},
                {"status": "partial"}, {"status": "failed"}, "not a layer",
            ],
        }
        self.assertEqual(summary_counts(report), {"pass": 2, "fail": 1, "warn": 1})

    def test_invalid_report_shapes_are_neutral_not_an_exception(self):
        self.assertEqual(summary_counts("completed"), {"pass": 0, "fail": 0, "warn": 0})
        self.assertEqual(summary_counts({"summary": []}), {"pass": 0, "fail": 0, "warn": 0})


if __name__ == "__main__":
    unittest.main()
