"""Every approved update leaves a version file: v1, v2, ... with its summary, files and test results."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import config, versions  # noqa: E402
from tests.test_changes import PLAN, ChangesTestCase, PROJECT  # noqa: E402
from server_modules import changes  # noqa: E402


class VersionFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        patch = mock.patch.object(config, "record_dir", lambda project: self.workspace / ".agentforge")
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, name: str, data) -> None:
        target = self.workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")

    def test_numbers_count_up_and_the_list_is_newest_first(self):
        self.assertEqual(versions.next_number("p"), 1)
        for number in (1, 2, 3):
            versions.record("p", number, {"id": f"c{number}", "request": "r", "plan": dict(PLAN)}, {}, {}, {}, {}, "done")
        self.assertEqual(versions.next_number("p"), 4)
        self.assertEqual([row["id"] for row in versions.listing("p")], ["v3", "v2", "v1"])

    def test_a_version_says_what_was_asked_planned_and_changed(self):
        before = {"app/a.js": (1, 10), "app/gone.js": (1, 5), "lib/same.js": (1, 1)}
        after = {"app/a.js": (2, 12), "test/a.test.js": (2, 30), "e2e/a.spec.js": (2, 9), "lib/same.js": (1, 1)}
        row = versions.record("p", 1, {"id": "chg-1", "request": "add a due date", "revision": 2,
                                        "plan": dict(PLAN)}, before, after,
                              {"unit": {"total": 10, "passed": 10, "failed": 0}},
                              {"unit": {"total": 14, "passed": 13, "failed": 1}}, "Changed the model.")
        self.assertEqual((row["title"], row["summary"], row["revisions"]), ("Add a due date", "Tasks get a due date.", 2))
        self.assertEqual(row["files"]["added"], ["e2e/a.spec.js", "test/a.test.js"])
        self.assertEqual(row["files"]["changed"], ["app/a.js"])
        self.assertEqual(row["files"]["removed"], ["app/gone.js"])
        self.assertEqual(row["tests"]["files"], ["e2e/a.spec.js", "test/a.test.js"])   # test files created
        self.assertEqual((row["tests"]["before"]["unit"]["total"], row["tests"]["after"]["unit"]["total"]), (10, 14))
        self.assertEqual(row["warnings"], [])
        markdown = (self.workspace / ".agentforge/versions/v1.md").read_text(encoding="utf-8")
        for text in ("# v1: Add a due date", "> add a due date", "unit 10/10 passed", "unit 13/14 passed", "- test/a.test.js",
                     "Wireframes: not changed"):
            self.assertIn(text, markdown)
        self.assertEqual(json.loads((self.workspace / ".agentforge/versions/v1.json").read_text())["number"], 1)

    def test_results_that_shrank_are_flagged(self):
        row = versions.record("p", 1, {"id": "c", "request": "r", "plan": dict(PLAN)}, {}, {},
                              {"unit": {"total": 10, "passed": 10, "failed": 0}},
                              {"unit": {"total": 4, "passed": 4, "failed": 0}}, "")
        self.assertEqual(len(row["warnings"]), 1)
        self.assertIn("held 10 before", row["warnings"][0])

    def test_the_counts_come_from_the_records_the_testing_view_reads(self):
        self.write(".agentforge/qa/vitest.json", {"numTotalTests": 12, "numPassedTests": 11, "numFailedTests": 1})
        self.write("test-results/results.json", {"stats": {"expected": 5, "unexpected": 1, "flaky": 0, "skipped": 2}})
        counts = versions.test_counts(self.workspace)
        self.assertEqual(counts["unit"], {"total": 12, "passed": 11, "failed": 1})
        self.assertEqual(counts["browser"], {"total": 8, "passed": 5, "failed": 1})
        self.assertEqual(versions.test_counts(self.workspace / "nowhere"), {})

    def test_the_results_are_copied_aside_before_an_update_can_touch_them(self):
        self.write(".agentforge/qa/vitest.json", {"numTotalTests": 12})
        self.write(".agentforge/build/report.json", {"commands": []})
        self.write("test-results/results.json", {"stats": {}})
        self.assertEqual(versions.result_records(self.workspace),
                         [".agentforge/build/report.json", ".agentforge/qa/vitest.json", "test-results/results.json"])
        versions.preserve_results("p", 3, self.workspace)
        kept = self.workspace / ".agentforge/versions/v3/results-before"
        self.assertEqual(json.loads((kept / ".agentforge/qa/vitest.json").read_text())["numTotalTests"], 12)
        self.assertTrue((kept / "test-results/results.json").is_file())


class UpdateLeavesAVersionTests(ChangesTestCase):
    def approve(self):
        self.session.replies = [dict(PLAN)]
        change_id = self.submit("add a due date to every task")
        with mock.patch("builder_agent.build.built", lambda project: False):
            changes.decide(PROJECT, change_id, "approve")
            self.settle(change_id)
        return change_id

    def test_an_approved_update_becomes_v1_and_the_next_one_v2(self):
        self.session.edits = ["test/a.test.js", ".agentforge/srs/srs.json"]
        change_id = self.approve()
        self.assertEqual(changes._load(PROJECT, change_id)["version"], 1)
        self.assertEqual([row["id"] for row in versions.listing(PROJECT)], ["v1"])
        v1 = versions.listing(PROJECT)[0]
        self.assertEqual(v1["title"], "Add a due date")
        self.assertIn("test/a.test.js", v1["tests"]["files"])
        self.assertEqual(v1["account"], "Done: changed what the plan said.")
        self.assertEqual(self.of_type("change")[-1]["version"], 1)              # the plan card can say "saved as v1"

        self.session.replies = [dict(PLAN, title="Second update")]
        again = self.approve()
        self.assertEqual(changes._load(PROJECT, again)["version"], 2)
        self.assertEqual([row["id"] for row in versions.listing(PROJECT)], ["v2", "v1"])

    def test_the_executor_is_told_which_result_records_exist_and_to_edit_not_replace_them(self):
        (self.workspace / ".agentforge/qa").mkdir(parents=True, exist_ok=True)
        (self.workspace / ".agentforge/qa/vitest.json").write_text(json.dumps({"numTotalTests": 10, "numPassedTests": 10}))
        self.approve()
        request = " ".join(self.session.executed[0][0].split())
        self.assertIn("- .agentforge/qa/vitest.json", self.session.executed[0][0])
        self.assertIn("Update saved result records only for checks actually run; preserve earlier entries.", request)

    def test_overwritten_results_are_kept_aside_and_flagged_in_the_version(self):
        record = self.workspace / ".agentforge/qa/vitest.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps({"numTotalTests": 10, "numPassedTests": 10, "numFailedTests": 0}))
        original_execute = self.session.execute_approved

        def overwrite(request, plan, model=""):                      # a run that replaced the record with a partial one
            record.write_text(json.dumps({"numTotalTests": 3, "numPassedTests": 3, "numFailedTests": 0}))
            return original_execute(request, plan, model)

        self.session.execute_approved = overwrite
        self.approve()
        v1 = versions.listing(PROJECT)[0]
        self.assertTrue(v1["warnings"])
        kept = self.workspace / ".agentforge/versions/v1/results-before/.agentforge/qa/vitest.json"
        self.assertEqual(json.loads(kept.read_text())["numTotalTests"], 10)      # nothing was lost

    def test_the_version_files_are_not_counted_as_part_of_the_update(self):
        self.session.edits = ["app/page.jsx"]
        self.approve()
        self.assertNotIn(".agentforge/versions/v1.json", versions.listing(PROJECT)[0]["files"]["added"])

    def test_a_failed_update_leaves_no_version(self):
        self.session.execution = {"status": "blocked", "text": "no db", "rounds": 1}
        self.approve()
        self.assertEqual(versions.listing(PROJECT), [])


if __name__ == "__main__":
    unittest.main()
