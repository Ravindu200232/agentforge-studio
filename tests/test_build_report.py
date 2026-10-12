"""The report files are held to the template the Testing views read.

Found live: a build that passed every check (63 unit tests, every journey, accessibility,
visual, Lighthouse, ZAP) showed empty route names, empty gaps, "not run" and "no repair"
in the Testing views - the builder had written its report in keys of its own, because
the prompt said "the UI-compatible shape" without ever saying what that shape is.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "builder-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import build  # noqa: E402
from server_modules import bus  # noqa: E402
from server_modules.validation import build_report  # noqa: E402

GOOD_BUILD = {
    "app": "An app", "stack": "nextjs-supabase", "complete": True,
    "routes": [{"route": "/", "method": "", "verified": True, "how": "loaded by the smoke test"}],
    "commands": [{"phase": "unit", "command": "npx vitest run", "exit_code": 0, "note": "5 passed"}],
    "layers": [{"layer": "unit", "command": "npx vitest run", "exit_code": 0, "status": "passed",
                "result": "5 passed", "artifact": ".agentforge/qa/vitest.json"}],
    "requirements": [{"id": "FR-001", "status": "met", "evidence": "test/a.test.js"}],
    "gaps": [], "defects_found_and_fixed": [],
}
GOOD_QA = {
    "complete": True, "summary": {"pass": 1, "fail": 0, "warn": 0},
    "layers": GOOD_BUILD["layers"],
    "unit": {"status": "passed", "total": 5, "passed": 5, "failed": 0, "artifact": ".agentforge/qa/vitest.json"},
    "journeys": {"status": "passed", "contract": ".agentforge/srs/user-journeys.json",
                 "required": ["UJ-001"], "passed": ["UJ-001"], "failed": [], "tests": ["[UJ-001] a journey"]},
    "coverage": {"status": "passed", "covered": 1, "total": 1},
}
# The shape a real build wrote before the template existed.
FREEFORM_BUILD = {
    "app": "An app", "stack": "nextjs-supabase", "complete": True,
    "routes": ["/", "/shop"],
    "commands": [{"phase": "unit", "command": "npx vitest run", "exit_code": 0, "note": "5 passed"}],
    "gaps": [{"area": "Online payments", "detail": "no live credentials", "severity": "gap"}],
    "repairs": [{"phase": "a11y", "finding": "link contrast 4.0:1", "fix": "underlined links"}],
}


class TemplateTests(unittest.TestCase):
    def test_a_report_that_follows_the_template_has_no_problems(self):
        self.assertEqual(build_report.problems(GOOD_BUILD, "build"), [])
        self.assertEqual(build_report.problems(GOOD_QA, "qa"), [])

    def test_a_freeform_report_is_told_exactly_what_to_change(self):
        found = build_report.problems(FREEFORM_BUILD, "build")
        self.assertIn("`routes[0]` must be an object, not text", found)
        self.assertIn("`gaps[0].item` is missing", found)
        for key in ("layers", "requirements", "defects_found_and_fixed"):
            self.assertIn(f"`{key}` is missing", found)

    def test_a_prose_summary_and_a_missing_unit_entry_are_flagged(self):
        qa = {**GOOD_QA, "summary": "every layer passed"}
        del qa["unit"]
        found = build_report.problems(qa, "qa")
        self.assertIn("`summary` must be an object, not text", found)
        self.assertIn("`unit` is missing", found)

    def test_null_is_allowed_for_a_value_nothing_measured(self):
        report = {**GOOD_BUILD, "layers": [{**GOOD_BUILD["layers"][0], "exit_code": None,
                                            "status": "unavailable", "artifact": None}]}
        self.assertEqual(build_report.problems(report, "build"), [])

    def test_extra_keys_are_allowed(self):
        self.assertEqual(build_report.problems({**GOOD_BUILD, "tables": ["orders"]}, "build"), [])

    def test_the_template_is_staged_where_the_agent_can_read_it(self):
        with tempfile.TemporaryDirectory() as temp:
            path = build_report.stage_template(Path(temp))
            staged = json.loads((Path(temp) / path).read_text(encoding="utf-8"))
            self.assertEqual(staged, build_report.template())
            self.assertTrue(path.startswith(".agentforge/"))


class FakeSession:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.runs: list = []
        self.executed: list[tuple[str, str]] = []

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def execute_approved(self, request, plan, model=""):
        self.executed.append((request, plan))
        return self.runs.pop(0)(request, plan)


class ConformTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.session = FakeSession(Path(temp.name))
        self.logs: list[tuple[str, str]] = []
        self.enterContext(mock.patch.object(bus, "log", lambda project, level, text, **_: self.logs.append((level, text))))

    def test_a_report_already_in_shape_costs_no_extra_turn(self):
        self.session.write_record("build", "report.json", data=GOOD_BUILD)
        self.session.write_record("qa", "report.json", data=GOOD_QA)
        build._conform_reports("prj", self.session, "the plan")
        self.assertEqual(self.session.executed, [])

    def test_a_freeform_report_is_rewritten_in_the_same_conversation(self):
        self.session.write_record("build", "report.json", data=FREEFORM_BUILD)
        self.session.write_record("qa", "report.json", data=GOOD_QA)

        def rewrite(request, plan):
            self.session.write_record("build", "report.json", data=GOOD_BUILD)
            return {"status": "complete", "text": ""}

        self.session.runs.append(rewrite)
        build._conform_reports("prj", self.session, "the plan")
        request, plan = self.session.executed[0]
        self.assertEqual(plan, "the plan")
        self.assertIn(".agentforge/build/report-template/report.template.json", request)
        self.assertIn("build/report.json: `routes[0]` must be an object, not text", request)
        self.assertIn("do not run any build or test again", request)
        self.assertEqual(len(self.session.executed), 1)

    def test_a_report_that_stays_wrong_is_logged_never_a_failed_build(self):
        self.session.write_record("build", "report.json", data=FREEFORM_BUILD)
        self.session.runs.extend([lambda r, p: {"status": "complete"}] * build.REPORT_REPAIR_ROUNDS)
        build._conform_reports("prj", self.session, "plan")
        self.assertEqual(len(self.session.executed), build.REPORT_REPAIR_ROUNDS)
        self.assertEqual(self.logs[-1][0], "WARN")

    def test_a_missing_report_is_left_to_the_existing_gate(self):
        build._conform_reports("prj", self.session, "plan")
        self.assertEqual(self.session.executed, [])


if __name__ == "__main__":
    unittest.main()
