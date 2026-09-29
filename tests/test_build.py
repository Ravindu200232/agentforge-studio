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
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "builder-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import build  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
