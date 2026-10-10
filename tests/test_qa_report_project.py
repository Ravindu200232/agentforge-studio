"""The testing results belong to the project by its id, whatever the agent that wrote the report put there."""
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


class ReportProjectTests(unittest.TestCase):
    def _report(self, saved):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(workspace=Path(directory))
            session.read_record.return_value = saved
            with patch.object(verify, "session_for", return_value=session):
                return verify.report("prj_abc123")

    def test_a_name_the_agent_wrote_does_not_replace_the_projects_id(self):
        # The studio shows a report only when its project is the one that is open; a name there left the page blank.
        result = self._report({"project": "Athenaeum - the public library", "complete": True,
                               "summary": "all layers pass"})
        self.assertEqual(result["project"], "prj_abc123")
        self.assertIs(result["complete"], True)

    def test_a_report_without_a_project_gets_the_id(self):
        self.assertEqual(self._report({"summary": "s", "complete": True})["project"], "prj_abc123")

    def test_no_report_yet_is_still_the_projects_own(self):
        result = self._report(None)
        self.assertEqual(result["project"], "prj_abc123")
        self.assertIs(result["complete"], False)


if __name__ == "__main__":
    unittest.main()
