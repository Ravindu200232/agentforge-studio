"""The end-to-end journeys run once, by the Studio, and never again by themselves.

They ran again and again: inside the build's last phase (where a ten-minute command limit killed the suite half-way), after
every screenshot-review fix, in the Testing stage straight after a build that had just run them, and in a whole new build
every time one journey failed - which failed the build, which was fixed, which ran everything again. These tests hold the
pieces that stop that: the agent may not run the whole suite, a journey is judged on its newest desktop result, the Studio
knows when the app is exactly what the last run tested, a failed journey is a result (never a failed build), and a fix the
person asks for is written from the results on disk and re-runs only the journeys it fixed.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from ollama_terminal import tools  # noqa: E402
from qa_agent import build_evidence, e2e_run  # noqa: E402
from server_modules import journeys  # noqa: E402


def contract(workspace: Path, ids: list[str]) -> None:
    target = workspace / ".agentforge" / "srs" / "user-journeys.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"schema": journeys.JOURNEY_SCHEMA,
                                  "journeys": [{"id": i, "workflow_name": f"Journey {i}", "who": "Visitor",
                                                "steps": [{"step": "Open the page"}]} for i in ids]}), encoding="utf-8")


def playwright(workspace: Path, rows: list[tuple], where: str = "test-results/results.json", age: float = 0) -> Path:
    """A Playwright JSON report: (file, title, project, status[, error]) per test, `status` "flaky" for passed-on-retry."""
    specs: dict[str, list] = {}
    for row in rows:
        file, title, project, status = row[:4]
        error = row[4] if len(row) > 4 else ""
        attempts = ([{"status": "failed", "error": {"message": "first try"}}, {"status": "passed"}] if status == "flaky"
                    else [{"status": status, **({"error": {"message": error + "\n    at line 3"}} if error else {})}])
        specs.setdefault(file, []).append({"title": title, "file": file, "tests": [{
            "projectName": project, "status": {"passed": "expected", "failed": "unexpected"}.get(status, status),
            "results": attempts}]})
    target = workspace / where
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"suites": [{"title": Path(f).name, "file": f, "specs": s} for f, s in specs.items()]}),
                      encoding="utf-8")
    if age:
        stamp = time.time() - age
        os.utime(target, (stamp, stamp))
    return target


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)


class TheAgentDoesNotRunTheWholeSuiteTests(unittest.TestCase):
    def test_a_whole_suite_run_is_told_apart_from_one_journey_or_a_grep(self):
        for command in ("npm run qa:e2e", "npm run test:e2e", "npx playwright test",
                        "node scripts/with-server.mjs -- npx playwright test --project=desktop"):
            self.assertTrue(tools.whole_e2e_suite(command), command)
        for command in ("node scripts/with-server.mjs -- npx playwright test e2e/journeys/UJ-001.spec.js --project=desktop",
                        'npx playwright test --grep "UJ-003"', "npx playwright test -g UJ-003", "npm run qa:visual",
                        "npm run qa:e2e -- e2e/journeys/UJ-002.spec.js", "npx playwright show-report", "npm run build"):
            self.assertFalse(tools.whole_e2e_suite(command), command)

    def test_the_refusal_says_how_to_run_one_journey_instead(self):
        workspace = tools.WorkspaceTools.__new__(tools.WorkspaceTools)
        workspace.studio_runs_e2e = True
        workspace.permission = None
        with self.assertRaises(ValueError) as caught:
            tools.WorkspaceTools.tool_run_command(workspace, "npm run qa:e2e")
        self.assertIn("e2e/journeys/UJ-001.spec.js", str(caught.exception))

    def test_starting_a_server_is_caught_but_the_words_inside_a_string_are_not(self):
        for command in ("npm run dev", "npx next start -p 3000", "cd app; npm start",
                        "node node_modules/next/dist/bin/next start"):
            self.assertTrue(tools.server_command(command), command)
        for command in ('Get-Content results.json | Select-String "next start"', 'echo "npm run dev"', "npm run build"):
            self.assertFalse(tools.server_command(command), command)


class AJourneyIsJudgedOnItsDesktopTestTests(Workspace):
    def test_a_failure_at_phone_width_is_a_warning_not_a_failed_journey(self):
        contract(self.workspace, ["UJ-001"])
        found = journeys.e2e_coverage(self.workspace, [
            {"title": "[UJ-001] Order", "project": "desktop", "status": "passed"},
            {"title": "[UJ-001] Order", "project": "mobile", "status": "failed"}])
        self.assertEqual(found["status"], "passed")
        self.assertEqual(found["mobileWarnings"], ["UJ-001"])

    def test_a_desktop_failure_fails_the_journey(self):
        contract(self.workspace, ["UJ-001"])
        found = journeys.e2e_coverage(self.workspace, [
            {"title": "[UJ-001] Order", "project": "desktop", "status": "failed"},
            {"title": "[UJ-001] Order", "project": "mobile", "status": "passed"}])
        self.assertEqual(found["failed"], ["UJ-001"])

    def test_a_journey_that_passed_on_its_retry_passes_and_is_marked_flaky(self):
        contract(self.workspace, ["UJ-001"])
        playwright(self.workspace, [("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "flaky")])
        found = journeys.e2e_coverage(self.workspace, build_evidence.newest_tests(self.workspace))
        self.assertEqual(found["status"], "passed")
        self.assertEqual(found["flaky"], ["UJ-001"])

    def test_a_journey_run_again_on_its_own_counts_for_itself(self):
        contract(self.workspace, ["UJ-001", "UJ-002"])
        playwright(self.workspace, [("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "failed"),
                                    ("e2e/journeys/UJ-002.spec.js", "[UJ-002] Pay", "desktop", "passed")],
                   where=".agentforge/qa/runs/full.json", age=60)
        playwright(self.workspace, [("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "passed")])
        found = journeys.e2e_coverage(self.workspace, build_evidence.newest_tests(self.workspace))
        self.assertEqual(found["status"], "passed")

    def test_runs_older_than_the_studios_last_full_run_no_longer_speak_for_a_journey(self):
        contract(self.workspace, ["UJ-001"])
        playwright(self.workspace, [("e2e/journeys.spec.js", "[UJ-001] Old name", "desktop", "failed")],
                   where=".agentforge/qa/runs/old.json", age=3600)
        playwright(self.workspace, [("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "passed")])
        e2e_run._save(self.workspace, {"full": {"at": time.time() - 30, "fingerprint": "x", "exit_code": 0}})
        found = journeys.e2e_coverage(self.workspace, build_evidence.newest_tests(self.workspace))
        self.assertEqual(found["status"], "passed")


class TheStudioKnowsWhenTheAppIsWhatItTestedTests(Workspace):
    def setUp(self):
        super().setUp()
        (self.workspace / "app").mkdir()
        (self.workspace / "app" / "page.jsx").write_text("export default () => null", encoding="utf-8")

    def test_a_run_on_this_very_source_is_current_and_a_change_to_the_source_is_not(self):
        e2e_run._save(self.workspace, {"full": {"fingerprint": e2e_run.fingerprint(self.workspace), "exit_code": 1}})
        self.assertTrue(e2e_run.current(self.workspace))
        (self.workspace / "app" / "page.jsx").write_text("export default () => 'changed'", encoding="utf-8")
        self.assertFalse(e2e_run.current(self.workspace))

    def test_what_a_build_or_a_test_run_writes_does_not_count_as_a_change(self):
        before = e2e_run.fingerprint(self.workspace)
        for folder in ("node_modules", ".next", "test-results", "playwright-report", ".agentforge"):
            (self.workspace / folder).mkdir(exist_ok=True)
            (self.workspace / folder / "x.json").write_text("{}", encoding="utf-8")
        self.assertEqual(e2e_run.fingerprint(self.workspace), before)

    def test_only_a_full_run_makes_the_app_current(self):
        e2e_run._save(self.workspace, {"last": {"fingerprint": e2e_run.fingerprint(self.workspace), "exit_code": 0}})
        self.assertFalse(e2e_run.current(self.workspace))

    def test_a_current_run_is_reused_instead_of_run_again_unless_the_person_asked(self):
        (self.workspace / "package.json").write_text(json.dumps({"devDependencies": {"@playwright/test": "1"}}), encoding="utf-8")
        (self.workspace / "e2e").mkdir()
        (self.workspace / "e2e" / "a.spec.js").write_text("", encoding="utf-8")
        e2e_run.ensure_runner("p", self.workspace)                         # as the run that recorded it left it
        e2e_run._save(self.workspace, {"full": {"fingerprint": e2e_run.fingerprint(self.workspace), "exit_code": 0}})
        session = mock.Mock(workspace=self.workspace, cancelled=False, stage="test")
        with mock.patch.object(e2e_run, "_execute") as execute, mock.patch.object(e2e_run.bus, "agent_msg"):
            self.assertEqual(e2e_run.run("p", session, reason="test")["status"], "reused")
        execute.assert_not_called()


class ARunIsCurrentRightAfterItRanTests(Workspace):
    """Found on a real project: the runner was replaced after the source was fingerprinted, so the run that replaced it
    looked out of date at once and the next call built and ran everything again."""

    def test_a_run_that_brings_the_runner_up_to_date_is_current_afterwards(self):
        (self.workspace / "package.json").write_text(json.dumps({"devDependencies": {"@playwright/test": "1"}}), encoding="utf-8")
        (self.workspace / "e2e").mkdir()
        (self.workspace / "e2e" / "a.spec.js").write_text("", encoding="utf-8")
        (self.workspace / "scripts").mkdir()
        (self.workspace / "scripts" / "with-server.mjs").write_text("// an older copy", encoding="utf-8")
        session = mock.Mock(workspace=self.workspace, cancelled=False, stage="test")
        finished = {"exit_code": 0, "timed_out": False, "output": "", "seconds": 1.0}
        with mock.patch.object(e2e_run, "_execute", return_value=finished), \
                mock.patch.object(e2e_run, "_build_if_needed", return_value=None), \
                mock.patch.object(e2e_run, "command_environment", return_value={}), \
                mock.patch.object(e2e_run.bus, "agent_msg"), mock.patch.object(e2e_run.bus, "phase"), \
                mock.patch.object(e2e_run.bus, "log"), mock.patch.object(e2e_run.live, "finish"):
            e2e_run.run("p", session, reason="build")
            self.assertTrue(e2e_run.current(self.workspace))
            self.assertEqual(e2e_run.run("p", session, reason="test")["status"], "reused")


class TheRunnerScriptIsTheStudiosTests(Workspace):
    def test_an_older_copy_is_replaced_and_kept(self):
        (self.workspace / "scripts").mkdir()
        (self.workspace / "scripts" / "with-server.mjs").write_text("// old", encoding="utf-8")
        with mock.patch.object(e2e_run.bus, "log"):
            e2e_run.ensure_runner("p", self.workspace)
        self.assertEqual((self.workspace / "scripts" / "with-server.mjs").read_bytes(), e2e_run.TEMPLATE_RUNNER.read_bytes())
        self.assertEqual((self.workspace / ".agentforge" / "qa" / "with-server.before.mjs").read_text(encoding="utf-8"), "// old")

    def test_the_test_database_name_fits_atlas_limit(self):
        text = e2e_run.TEMPLATE_RUNNER.read_text(encoding="utf-8")
        self.assertIn("MAX_DATABASE_NAME = 38", text)
        self.assertNotIn("Date.now() + '_' + process.pid + '_e2e'", text)


class AFixThePersonAsksForTests(Workspace):
    def test_the_words_and_the_button_are_understood(self):
        for said in ("fix the failing journeys", "Fix the failed journeys please", "please fix failing journeys"):
            self.assertTrue(e2e_run.fix_asked(said), said)
        for said in ("add a journeys page", "fix the header colour", "the journeys look fine"):
            self.assertFalse(e2e_run.fix_asked(said), said)

    def test_the_request_names_each_failed_journey_its_file_and_why(self):
        contract(self.workspace, ["UJ-001", "UJ-002"])
        (self.workspace / "e2e" / "journeys").mkdir(parents=True)
        (self.workspace / "e2e" / "journeys" / "UJ-001.spec.js").write_text("", encoding="utf-8")
        playwright(self.workspace, [
            ("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "failed", "Timeout 60000ms exceeded."),
            ("e2e/journeys/UJ-002.spec.js", "[UJ-002] Pay", "desktop", "passed")])
        request, ids = e2e_run.fix_request(self.workspace, "fix the failing journeys")
        self.assertEqual(ids, ["UJ-001"])
        self.assertIn("UJ-001", request)
        self.assertIn("e2e/journeys/UJ-001.spec.js", request)
        self.assertIn("Timeout 60000ms exceeded.", request)
        self.assertNotIn("UJ-002", request)
        self.assertIn("Do not run the whole suite", request)

    def test_nothing_to_fix_when_every_journey_passed(self):
        contract(self.workspace, ["UJ-001"])
        playwright(self.workspace, [("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "passed")])
        self.assertEqual(e2e_run.fix_request(self.workspace), ("", []))

    def test_a_grep_matches_journey_ids_and_whole_titles(self):
        self.assertEqual(e2e_run.grep_for(["UJ-003", "UJ-005"]), r"\bUJ-003\b|\bUJ-005\b")
        self.assertIn("Customer", e2e_run.grep_for(["[UJ-001] Customer places an order"]))


class Record:
    """The part of a session `_finish_run` reads and writes."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.finished: list[str] = []

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def note(self, text):
        pass

    def finish(self, text=""):
        self.finished.append(text)


class AFailedJourneyIsAResultNotAFailedBuildTests(Workspace):
    def setUp(self):
        super().setUp()
        from builder_agent import build

        self.build = build
        (self.workspace / "package.json").write_text("{}", encoding="utf-8")
        self.session = Record(self.workspace)
        self.session.write_record("build", "report.json", data={"routes": ["/"], "gaps": []})
        contract(self.workspace, ["UJ-001", "UJ-002"])
        playwright(self.workspace, [("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "failed", "Timeout"),
                                    ("e2e/journeys/UJ-002.spec.js", "[UJ-002] Pay", "desktop", "passed")])
        self.said: list[dict] = []
        self.updates: list[dict] = []
        for patch in (mock.patch.object(build, "session_for", lambda project: self.session),
                      mock.patch.object(build.build_phases, "gate"), mock.patch.object(build, "_conform_reports"),
                      mock.patch.object(build, "show_preview"), mock.patch.object(build.plugins, "consume_handoff"),
                      mock.patch.object(build.bus, "phase"), mock.patch.object(build.bus, "log"),
                      mock.patch.object(build.store, "advance"),
                      mock.patch.object(build.store, "update", lambda project, **kw: self.updates.append(kw)),
                      mock.patch.object(build.bus, "agent_msg", lambda project, text, **kw: self.said.append({"text": text, **kw}))):
            self.enterContext(patch)

    def test_the_build_completes_with_the_failed_journeys_listed_and_a_fix_offered(self):
        self.build._finish_run("p", self.session, {"status": "complete"})
        self.assertEqual(self.updates[0]["status"], "tested-with-failures")
        failed = next(row for row in self.said if row.get("title") == "Journeys that failed")
        self.assertIn("UJ-001", failed["text"])
        self.assertIn("not run again by themselves", failed["text"])
        self.assertEqual(failed["actions"][0]["prompt"], self.build.FIX_JOURNEYS)
        self.assertTrue(e2e_run.fix_asked(failed["actions"][0]["prompt"]))

    def test_a_report_the_agent_never_marked_complete_is_completed_not_a_failure(self):
        self.session.write_record("qa", "report.json", data={"summary": "ran things"})
        self.build._finish_run("p", self.session, {"status": "complete"})
        saved = self.session.read_record("qa", "report.json")
        self.assertIs(saved["complete"], True)
        self.assertTrue(saved["studioNotes"])

    def test_a_report_that_was_never_written_is_written(self):
        self.build._finish_run("p", self.session, {"status": "complete"})
        self.assertIs(self.session.read_record("qa", "report.json")["complete"], True)

    def test_every_journey_passing_is_a_tested_build_with_nothing_offered(self):
        playwright(self.workspace, [("e2e/journeys/UJ-001.spec.js", "[UJ-001] Order", "desktop", "passed"),
                                    ("e2e/journeys/UJ-002.spec.js", "[UJ-002] Pay", "desktop", "passed")])
        self.build._finish_run("p", self.session, {"status": "complete"})
        self.assertEqual(self.updates[0]["status"], "tested")
        self.assertFalse([row for row in self.said if row.get("actions")])


if __name__ == "__main__":
    unittest.main()
