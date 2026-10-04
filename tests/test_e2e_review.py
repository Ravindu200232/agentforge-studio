"""After the end-to-end tests, a model that can look at pictures reviews their screenshots, and what it finds is fixed."""
from __future__ import annotations

import json
import ssl
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from qa_agent import e2e_review  # noqa: E402
from server_modules import bus, config  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402

OK = {"page": "x", "looks_ok": True, "summary": "A clean dashboard.", "defects": []}
JOURNEY = "[UJ-001] Customer places an order"
OTHER = "home page loads"


def defect(severity="high", viewport="mobile", problem="The order total overlaps the heading."):
    return {"severity": severity, "viewport": viewport, "where": "the order card", "problem": problem, "fix": "give the total its own line"}


def png(seed: str) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + seed.encode() * 100


def results(workspace: Path, tests: list[tuple[str, str, str, str, str]], name: str = "results.json", folder: str = "test-results") -> Path:
    """A Playwright JSON report: (spec file, title, project, status, picture seed) per test; the picture is written too."""
    specs: dict[str, list] = {}
    for file, title, project, status, seed in tests:
        picture = workspace / "test-results" / "artifacts" / f"{abs(hash((file, title, project))) % 10**8}" / "test-finished-1.png"
        picture.parent.mkdir(parents=True, exist_ok=True)
        picture.write_bytes(png(seed))
        specs.setdefault(file, []).append({
            "title": title, "file": file,
            "tests": [{"projectName": project, "status": {"passed": "expected", "failed": "unexpected"}.get(status, status),
                       "results": [{"status": status, "duration": 1200,
                                    "attachments": [{"name": "screenshot", "path": str(picture), "contentType": "image/png"}]}]}]})
    data = {"suites": [{"title": Path(file).name, "file": file, "specs": found} for file, found in specs.items()], "stats": {}}
    target = workspace / folder / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data), encoding="utf-8")
    return target


class FakeSession:
    def __init__(self, workspace: Path, model: str = "vision-model", fix=None):
        self.workspace = workspace
        self.cancelled = False
        self.model = model
        self.fix = fix
        self.requests: list[str] = []

    def agent(self, model: str = ""):
        return SimpleNamespace(model=self.model)

    def run_direct(self, request: str, model: str = ""):
        self.requests.append(request)
        if self.fix:
            self.fix(self.workspace)
        return {"status": "complete", "text": "Fixed.", "rounds": 1}


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.messages: list[dict] = []
        self.phases: list[tuple] = []
        for patch in (
            mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                              self.messages.append({"text": text, "title": title, "kind": kind, "images": images or []})),
            mock.patch.object(bus, "phase", lambda project, key, title, status="active", detail="", number=0, kind="run", agent="":
                              self.phases.append((key, status))),
            mock.patch.object(bus, "progress", lambda *a, **k: None),
            mock.patch.object(bus, "log", lambda *a, **k: None),
            mock.patch.object(config, "setting", lambda name, fallback=None: True if name == "e2e_visual_review" else fallback),
            mock.patch("server_modules.vision.supports", return_value=True),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def standard(self):
        results(self.workspace, [
            ("e2e/journeys.spec.js", JOURNEY, "desktop", "passed", "d1"), ("e2e/journeys.spec.js", JOURNEY, "mobile", "passed", "m1"),
            ("e2e/smoke.spec.js", OTHER, "desktop", "passed", "d2"), ("e2e/smoke.spec.js", OTHER, "mobile", "passed", "m2")])

    def answers(self, table):
        """The model's answer per test title: a dict, a list of them (one per ask) or an Exception."""
        counts: dict[str, int] = {}
        self.asked: list[tuple[str, int]] = []

        def complete_json(system, user, validator=None, label="", model="", images=None, project="", role="", **_):
            title = next(t for t in table if f"**{t}**" in user)
            counts[title] = counts.get(title, 0) + 1
            self.asked.append((title, len(images or [])))
            value = table[title]
            value = value[min(counts[title], len(value)) - 1] if isinstance(value, list) else value
            if isinstance(value, Exception):
                raise value
            return validator(value)

        return mock.patch("server_modules.llm.complete_json", side_effect=complete_json)


class WhichScreenshotsTests(Harness):
    def test_each_test_gets_one_entry_with_a_picture_per_browser_and_journeys_come_first(self):
        results(self.workspace, [
            ("e2e/smoke.spec.js", "a plain page", "desktop", "passed", "a"),
            ("e2e/journeys.spec.js", JOURNEY, "desktop", "passed", "b"), ("e2e/journeys.spec.js", JOURNEY, "mobile", "passed", "c")])
        found = e2e_review.screens(self.workspace)
        self.assertEqual([g["title"] for g in found], [JOURNEY, "a plain page"])
        self.assertEqual(sorted(found[0]["pictures"]), ["desktop", "mobile"])
        self.assertEqual(sorted(found[1]["pictures"]), ["desktop"])
        self.assertTrue(all((self.workspace / p).is_file() for g in found for p in g["pictures"].values()))

    def test_a_tests_status_is_failed_when_any_browser_failed_it(self):
        results(self.workspace, [("e2e/j.spec.js", JOURNEY, "desktop", "passed", "a"), ("e2e/j.spec.js", JOURNEY, "mobile", "failed", "b")])
        self.assertEqual(e2e_review.screens(self.workspace)[0]["status"], "failed")

    def test_accessibility_specs_and_other_browsers_are_left_out(self):
        results(self.workspace, [("e2e/a11y.spec.js", "axe check", "desktop", "passed", "a"),
                                 ("e2e/j.spec.js", JOURNEY, "webkit", "passed", "b"), ("e2e/j.spec.js", JOURNEY, "desktop", "passed", "c")])
        found = e2e_review.screens(self.workspace)
        self.assertEqual([g["title"] for g in found], [JOURNEY])
        self.assertEqual(list(found[0]["pictures"]), ["desktop"])

    def test_a_later_partial_run_replaces_only_the_tests_it_covered(self):
        results(self.workspace, [("e2e/j.spec.js", JOURNEY, "desktop", "passed", "old"), ("e2e/j.spec.js", "[UJ-002] Another", "desktop", "passed", "keep")])
        first = {g["title"]: g for g in e2e_review.screens(self.workspace)}
        kept = (self.workspace / first["[UJ-002] Another"]["pictures"]["desktop"]).read_bytes()
        later = results(self.workspace, [("e2e/j.spec.js", JOURNEY, "desktop", "passed", "NEW")], name="test-e2e-uj-001.json", folder=".agentforge/qa/runs")
        import os
        os.utime(later, (later.stat().st_atime + 100, later.stat().st_mtime + 100))        # a later run
        now = {g["title"]: g for g in e2e_review.screens(self.workspace)}
        self.assertIn(b"NEW", (self.workspace / now[JOURNEY]["pictures"]["desktop"]).read_bytes())
        self.assertEqual((self.workspace / now["[UJ-002] Another"]["pictures"]["desktop"]).read_bytes(), kept)

    def test_no_more_than_a_bounded_number_of_tests_are_reviewed_journeys_first(self):
        tests = [("e2e/smoke.spec.js", f"page {i}", "desktop", "passed", f"p{i}") for i in range(30)]
        tests += [("e2e/j.spec.js", f"[UJ-{i:03d}] journey", "desktop", "passed", f"j{i}") for i in range(5)]
        results(self.workspace, tests)
        found = e2e_review.screens(self.workspace)
        self.assertEqual(len(found), e2e_review.MAX_TESTS)
        self.assertEqual(len([g for g in found if g["title"].startswith("[UJ-")]), 5)

    def test_no_run_or_no_screenshots_is_an_empty_list(self):
        self.assertEqual(e2e_review.screens(self.workspace), [])


class SkipTests(Harness):
    def test_a_run_that_left_no_screenshots_is_skipped_without_a_word(self):
        self.assertEqual(e2e_review.run("p", FakeSession(self.workspace))["status"], "skipped")
        self.assertEqual(self.messages, [])

    def test_a_review_asked_for_says_why_when_there_are_no_screenshots(self):
        # A later run (the accessibility check) clears what the end-to-end run left; asking must not end in silence.
        result = e2e_review.run("p", FakeSession(self.workspace), force=True)
        self.assertEqual(result["status"], "skipped")
        self.assertEqual([m["title"] for m in self.messages], ["Screenshot review skipped"])
        self.assertIn("no end-to-end screenshots", self.messages[0]["text"])
        self.assertIn("run the end-to-end tests", self.messages[0]["text"])

    def test_a_model_that_cannot_look_at_pictures_skips_it_and_says_so(self):
        self.standard()
        with mock.patch("server_modules.vision.supports", return_value=False), \
                mock.patch("server_modules.llm.complete_json", side_effect=AssertionError("asked")):
            result = e2e_review.run("p", FakeSession(self.workspace, model="plain-model"))
        self.assertEqual(result["status"], "skipped")
        self.assertIn("vision", result["reason"])
        self.assertEqual([m["title"] for m in self.messages], ["Screenshot review skipped"])

    def test_a_model_nobody_could_ask_about_is_skipped(self):
        self.standard()
        with mock.patch("server_modules.vision.supports", return_value=None):
            result = e2e_review.run("p", FakeSession(self.workspace))
        self.assertEqual(result["status"], "skipped")

    def test_the_setting_turns_it_off_without_a_word(self):
        self.standard()
        with mock.patch.object(config, "setting", lambda name, fallback=None: False if name == "e2e_visual_review" else fallback):
            self.assertEqual(e2e_review.run("p", FakeSession(self.workspace)), {"status": "off"})
        self.assertEqual(self.messages, [])


class ReviewTests(Harness):
    def test_every_test_is_looked_at_with_both_its_pictures_and_clean_screens_change_nothing(self):
        self.standard()
        session = FakeSession(self.workspace)
        with self.answers({JOURNEY: OK, OTHER: OK}):
            result = e2e_review.run("p", session)
        self.assertEqual(result["status"], "done")
        self.assertEqual(sorted(self.asked), sorted([(JOURNEY, 2), (OTHER, 2)]))
        self.assertEqual(session.requests, [])
        self.assertIn("no problems found", self.messages[-1]["text"])
        self.assertEqual(self.phases[-1], (e2e_review.PHASE, "complete"))

    def test_the_prompt_tells_the_model_which_test_it_is_and_whether_it_failed(self):
        results(self.workspace, [("e2e/j.spec.js", JOURNEY, "desktop", "failed", "a"), ("e2e/j.spec.js", JOURNEY, "mobile", "passed", "b")])
        seen = []

        def complete_json(system, user, validator=None, images=None, **_):
            seen.append(user)
            return validator(OK)
        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            e2e_review.run("p", FakeSession(self.workspace))
        self.assertIn(f"**{JOURNEY}**", seen[0])
        self.assertIn("this test FAILED", seen[0])
        self.assertIn("picture 1 is the desktop browser and picture 2 is the mobile browser", seen[0])

    def test_the_chat_shows_each_tests_screenshots_from_the_workspace_with_what_was_found(self):
        self.standard()
        with self.answers({JOURNEY: {**OK, "looks_ok": False, "defects": [defect()]}, OTHER: OK}):
            e2e_review.run("p", FakeSession(self.workspace))
        shown = [m for m in self.messages if m["kind"] == "visual_review"]
        journey = next(m for m in shown if m["title"].startswith("[UJ-001]"))
        self.assertEqual(journey["title"], f"{JOURNEY} · 1 to fix")
        self.assertIn("**high** · mobile · the order card: The order total overlaps the heading.", journey["text"])
        self.assertEqual([i["label"] for i in journey["images"]], [f"{JOURNEY} · desktop", f"{JOURNEY} · mobile"])
        self.assertTrue(all(i["path"].startswith("test-results/") for i in journey["images"]))   # served by /qa-screenshot

    def test_the_problems_that_matter_go_to_the_agent_test_by_test_and_low_ones_are_left_alone(self):
        self.standard()
        session = FakeSession(self.workspace)
        answers = {JOURNEY: {**OK, "looks_ok": False, "defects": [defect("medium", "desktop", "Heading is cut off."), defect("low", "both", "Spacing is uneven.")]},
                   OTHER: {**OK, "looks_ok": False, "defects": [defect("high", "both", "An 'Application error' page is shown.")]}}
        with self.answers(answers):
            e2e_review.run("p", session)
        request = session.requests[0]
        self.assertIn(f"### {JOURNEY} — `e2e/journeys.spec.js`", request)
        self.assertIn("Heading is cut off.", request)
        self.assertIn(f"### {OTHER} — `e2e/smoke.spec.js`", request)
        self.assertIn("An 'Application error' page is shown.", request)
        self.assertNotIn("Spacing is uneven.", request)
        self.assertIn("npm run qa:e2e", request)                                # and the journeys are to be run again

    def test_after_the_fix_only_the_tests_with_problems_whose_screenshots_are_new_are_looked_at_again(self):
        self.standard()

        def fix(workspace):                                                      # the journey suite ran again: new pictures
            results(workspace, [("e2e/journeys.spec.js", JOURNEY, "desktop", "passed", "FIXED-d"),
                                ("e2e/journeys.spec.js", JOURNEY, "mobile", "passed", "FIXED-m")],
                    name="test-e2e.json", folder=".agentforge/qa/runs")
            import os
            for path in (workspace / ".agentforge/qa/runs").glob("*.json"):
                os.utime(path, (path.stat().st_atime + 100, path.stat().st_mtime + 100))

        session = FakeSession(self.workspace, fix=fix)
        answers = {JOURNEY: [{**OK, "looks_ok": False, "defects": [defect()]}, OK], OTHER: OK}
        with self.answers(answers):
            result = e2e_review.run("p", session)
        self.assertEqual([t for t, _ in self.asked].count(JOURNEY), 2)
        self.assertEqual([t for t, _ in self.asked].count(OTHER), 1)
        self.assertEqual(result["rechecked"], [JOURNEY])
        self.assertEqual(result["remaining"], [])
        self.assertIn("1 test screen looked at again after the fix, none left that matters.", self.messages[-1]["text"])

    def test_a_fix_whose_journeys_were_not_run_again_is_said_not_to_have_been_checked_by_looking(self):
        self.standard()
        session = FakeSession(self.workspace)                                    # the agent never re-ran the suite
        answers = {JOURNEY: {**OK, "looks_ok": False, "defects": [defect()]}, OTHER: OK}
        with self.answers(answers):
            result = e2e_review.run("p", session)
        self.assertEqual(result["rechecked"], [])
        self.assertEqual(result["not_rechecked"], [JOURNEY])
        self.assertIn("did not run again", self.messages[-1]["text"])
        self.assertIn(JOURNEY, self.messages[-1]["text"])

    def test_a_fix_that_stops_partway_does_not_end_the_review_the_tests_it_ran_again_are_looked_at_anyway(self):
        self.standard()

        def fix(workspace):                                                      # the suite ran again, then the model service dropped
            results(workspace, [("e2e/journeys.spec.js", JOURNEY, "desktop", "passed", "HALF-d"),
                                ("e2e/journeys.spec.js", JOURNEY, "mobile", "passed", "HALF-m")],
                    name="test-e2e.json", folder=".agentforge/qa/runs")
            import os
            for path in (workspace / ".agentforge/qa/runs").glob("*.json"):
                os.utime(path, (path.stat().st_atime + 100, path.stat().st_mtime + 100))
            raise ssl.SSLError(1, "[SSL: SSLV3_ALERT_BAD_RECORD_MAC] sslv3 alert bad record mac (_ssl.c:2580)")

        session = FakeSession(self.workspace, fix=fix)
        with self.answers({JOURNEY: [{**OK, "looks_ok": False, "defects": [defect()]}, OK], OTHER: OK}):
            result = e2e_review.run("p", session)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["rechecked"], [JOURNEY])
        self.assertIn("BAD_RECORD_MAC", result["fix_stopped"])
        self.assertTrue(any(m["text"].startswith("The fix stopped before it was finished") for m in self.messages))
        self.assertIn("The fix stopped before it was finished (", self.messages[-1]["text"])

    def test_a_problem_still_there_after_the_fix_is_reported_as_it_is_and_never_fixed_twice(self):
        self.standard()

        def fix(workspace):
            results(workspace, [("e2e/journeys.spec.js", JOURNEY, "desktop", "passed", "AGAIN-d")], name="test-e2e.json", folder=".agentforge/qa/runs")
            import os
            for path in (workspace / ".agentforge/qa/runs").glob("*.json"):
                os.utime(path, (path.stat().st_atime + 100, path.stat().st_mtime + 100))

        session = FakeSession(self.workspace, fix=fix)
        still = {**OK, "looks_ok": False, "defects": [defect(problem="The total still overlaps the heading.")]}
        with self.answers({JOURNEY: still, OTHER: OK}):
            result = e2e_review.run("p", session)
        self.assertEqual(len(session.requests), 1)
        self.assertEqual([r["problem"] for r in result["remaining"]], ["The total still overlaps the heading."])
        self.assertIn("1 problem still visible.", self.messages[-1]["text"])

    def test_the_report_is_saved_with_the_qa_records(self):
        self.standard()
        with self.answers({JOURNEY: OK, OTHER: OK}):
            e2e_review.run("p", FakeSession(self.workspace))
        saved = json.loads((self.workspace / e2e_review.REPORT).read_text(encoding="utf-8"))
        self.assertEqual((saved["model"], saved["tests"], saved["problems_found"]), ("vision-model", 2, 0))

    def test_a_test_the_model_failed_on_is_named_and_the_others_still_count(self):
        self.standard()
        with self.answers({JOURNEY: ValueError("no valid JSON"), OTHER: OK}):
            result = e2e_review.run("p", FakeSession(self.workspace))
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["tests_not_reviewed"], [JOURNEY])
        self.assertIn(f"Could not be reviewed: {JOURNEY}.", self.messages[-1]["text"])

    def test_an_error_anywhere_is_never_raised_into_the_testing(self):
        self.standard()
        with mock.patch("server_modules.llm.complete_json", side_effect=RuntimeError("engine down")):
            result = e2e_review.run("p", FakeSession(self.workspace))
        self.assertEqual(result["status"], "done")                                # each test's failure is that test's
        self.assertEqual(len(result["tests_not_reviewed"]), 2)
        with mock.patch.object(e2e_review, "screens", side_effect=OSError("disk gone")):
            self.assertEqual(e2e_review.run("p", FakeSession(self.workspace))["status"], "failed")
        self.assertEqual(self.phases[-1], (e2e_review.PHASE, "failed"))

    def test_stop_ends_the_review_with_the_runs_own_cancellation(self):
        self.standard()
        session = FakeSession(self.workspace)
        session.cancelled = True
        with self.answers({JOURNEY: OK, OTHER: OK}), self.assertRaises(RunCancelled):
            e2e_review.run("p", session)


class OnRequestTests(Harness):
    def test_a_review_only_looks_and_reports_and_changes_nothing(self):
        self.standard()
        session = FakeSession(self.workspace)
        with self.answers({JOURNEY: {**OK, "looks_ok": False, "defects": [defect()]}, OTHER: OK}):
            result = e2e_review.run("p", session, fix=False)
        self.assertEqual(session.requests, [])
        self.assertEqual(result["problems_found"], 1)
        self.assertIn("nothing was changed, this was a review only", self.messages[-1]["text"])

    def test_it_runs_when_asked_for_even_if_the_setting_turns_it_off(self):
        self.standard()
        off = lambda name, fallback=None: False if name == "e2e_visual_review" else fallback  # noqa: E731
        with mock.patch.object(config, "setting", off), self.answers({JOURNEY: OK, OTHER: OK}):
            self.assertEqual(e2e_review.run("p", FakeSession(self.workspace))["status"], "off")
            self.assertEqual(e2e_review.run("p", FakeSession(self.workspace), force=True)["status"], "done")


class WiredInTests(unittest.TestCase):
    def test_the_testing_run_and_the_build_both_look_at_the_screenshots_after_their_end_to_end_tests(self):
        verify = (ROOT / "qa-agent/qa_agent/verify.py").read_text(encoding="utf-8")
        build = (ROOT / "builder-agent/builder_agent/build.py").read_text(encoding="utf-8")
        for name, text, after in (("verify", verify, "result = session.run_task(request, audit=False)"),
                                  ("build", build, 'build_result = session.run_task(request, plan_directory="plan", audit=False)')):
            self.assertIn("e2e_review.run(project, session)", text, name)
            self.assertLess(text.index(after), text.index("e2e_review.run(project, session)"), name)
        self.assertLess(build.index("e2e_review.run(project, session)"), build.index("return _finish_run(project, session, build_result"))


if __name__ == "__main__":
    unittest.main()
