"""The testing pages draw how the results were produced as a sentence, whatever shape the report recorded it in."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "qa-agent", "builder-agent"):
    sys.path.insert(0, str(ROOT / folder))

from qa_agent import verify  # noqa: E402


class ProvenanceTests(unittest.TestCase):
    def _report(self, saved):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(workspace=Path(directory))
            session.read_record.return_value = saved
            with patch.object(verify, "session_for", return_value=session):
                return verify.report("prj_abc123")

    def test_a_sentence_is_kept(self):
        self.assertEqual(verify.provenance_text("  Run by the scaffold's runners. "), "Run by the scaffold's runners.")

    def test_an_object_becomes_its_method_and_the_runner_files(self):
        text = verify.provenance_text({"method": "Every layer ran through the runner.",
                                       "runner_files": ["a.json", "b.json"], "database": "isolated"})
        self.assertEqual(text, "Every layer ran through the runner. Runner files: a.json, b.json.")

    def test_an_object_without_a_method_is_still_text(self):
        self.assertIsInstance(verify.provenance_text({"database": "isolated"}), str)

    def test_a_list_and_nothing_are_text(self):
        self.assertEqual(verify.provenance_text(["one", "two"]), "one two")
        self.assertEqual(verify.provenance_text(None), "")

    def test_the_report_the_studio_reads_has_a_text_provenance(self):
        result = self._report({"summary": "s", "complete": True,
                               "provenance": {"method": "Through the runner.", "runner_files": ["a.json"]}})
        self.assertEqual(result["provenance"], "Through the runner. Runner files: a.json.")

    def test_a_report_without_one_says_nothing_has_run(self):
        self.assertIn("no verification", self._report(None)["provenance"])


if __name__ == "__main__":
    unittest.main()
