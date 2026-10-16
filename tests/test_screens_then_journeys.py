"""The Studio tests a built app in one order: every page looked at first, then the journeys once, then the final checks.

The journeys used to run again and again: the agent ran the whole suite through Playwright's own script (`node
node_modules/@playwright/test/cli.js test`) six times in one build's last phase, the Studio ran it once more, and every round of
the screenshot review ran the journeys again only to take new pictures. Now:

- the pages are photographed by the Studio's own spec and looked at first; a round of fixes photographs only those pages;
- the journeys run once; while some fail, each further round is asked for - Yes fixes and runs only those, No moves on;
- a change made after the journeys (accessibility, security) is checked with the runtime test, never the journeys, and the
  journeys' run stays the app's.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from ollama_terminal import tools  # noqa: E402
from qa_agent import e2e_review, e2e_run, sequence  # noqa: E402
from server_modules import bus  # noqa: E402

from test_e2e_once import playwright  # noqa: E402


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.said: list[dict] = []
        self.enterContext(mock.patch.object(bus, "agent_msg", lambda project, text, **kw: self.said.append({"text": text, **kw})))
        self.enterContext(mock.patch.object(bus, "phase"))
        self.enterContext(mock.patch.object(bus, "log"))
        self.session = SimpleNamespace(workspace=self.workspace, cancelled=False, stage="build", project="p",
                                       fixes=[], run_unplanned=lambda request, model="": self.session.fixes.append(request))

    def app(self) -> None:
        """A project the Studio can run tests in: Playwright, a spec, and a build script."""
        (self.workspace / "package.json").write_text(json.dumps({
            "scripts": {"build": "next build"}, "devDependencies": {"@playwright/test": "1.64.1"}}), encoding="utf-8")
        (self.workspace / "e2e" / "journeys").mkdir(parents=True)
        (self.workspace / "e2e" / "journeys" / "UJ-001.spec.js").write_text("// a journey", encoding="utf-8")
        (self.workspace / "e2e" / "smoke.spec.js").write_text("// every page opens", encoding="utf-8")


class TheAgentStillCannotRunTheWholeSuiteTests(unittest.TestCase):
    def test_playwrights_own_script_is_a_whole_suite_run_too(self):
        for command in ("node scripts/with-server.mjs -- node node_modules/@playwright/test/cli.js test --project=desktop",
                        'node node_modules/@playwright/test/cli.js test --project=desktop --grep-invert "@visual|@a11y"',
                        "node node_modules/playwright/cli.js test"):
            self.assertTrue(tools.whole_e2e_suite(command), command)
        for command in ("node node_modules/@playwright/test/cli.js test e2e/journeys/UJ-001.spec.js",
                        'node node_modules/@playwright/test/cli.js test --project=desktop --grep "@a11y"',
                        "npx playwright install chromium"):
            self.assertFalse(tools.whole_e2e_suite(command), command)


class ThePagesAreTheStudiosOwnSpecTests(Workspace):
    def test_the_journeys_run_never_takes_the_page_pictures(self):
        self.assertIn("@pages", e2e_run.PLAYWRIGHT_ARGS[e2e_run.PLAYWRIGHT_ARGS.index("--grep-invert") + 1])

    def test_the_spec_is_put_in_place_and_does_not_count_as_a_change_to_the_app(self):
        self.app()
        before = e2e_run.fingerprint(self.workspace)
        self.assertTrue(e2e_run.ensure_pages_spec(self.workspace))
        self.assertEqual((self.workspace / e2e_run.PAGES_SPEC).read_bytes(), e2e_run.TEMPLATE_PAGES.read_bytes())
        self.assertEqual(e2e_run.fingerprint(self.workspace), before)

    def test_the_pages_are_photographed_with_their_own_spec_and_only_the_ones_named_again(self):
        self.app()
        ran: list[list[str]] = []

        def execute(project, session, command, env, seconds, label):
            ran.append(command)
            playwright(self.workspace, [("pages.spec.js", "Home (/)", "desktop", "passed"),
                                        ("pages.spec.js", "Orders (/orders)", "desktop", "passed")])
            return {"exit_code": 0, "timed_out": False, "output": "", "seconds": 3}

        with mock.patch.object(e2e_run, "_execute", execute), mock.patch.object(e2e_run, "_build_if_needed", return_value=None), \
                mock.patch.object(e2e_run, "command_environment", return_value={}), mock.patch.object(e2e_run.live, "finish"):
            first = e2e_run.pages("p", self.session)
            again = e2e_run.pages("p", self.session, titles=["Orders (/orders)"])
        self.assertEqual(first["status"], "done")
        self.assertIn(e2e_run.PAGES_SPEC, ran[0])
        self.assertNotIn("--grep", ran[0])
        self.assertEqual(ran[1][ran[1].index("--grep") + 1], e2e_run.grep_for(["Orders (/orders)"]))
        self.assertEqual(again["status"], "done")
        self.assertNotIn("full", e2e_run.record(self.workspace))           # pictures are never the journeys' run

    def test_a_skipped_page_is_said_with_why_and_its_blank_picture_is_never_looked_at(self):
        target = self.workspace / "test-results" / "results.json"
        target.parent.mkdir(parents=True)
        target.write_text(json.dumps({"suites": [{"title": "pages.spec.js", "file": "pages.spec.js", "specs": [
            {"title": "Order (/orders/[id])", "file": "pages.spec.js", "tests": [{
                "projectName": "desktop", "status": "skipped",
                "annotations": [{"type": "skip", "description": "no record to open it on: its list page links to none"}],
                "results": [{"status": "skipped", "attachments": []}]}]}]}]}), encoding="utf-8")
        self.assertEqual(e2e_run._skipped(self.workspace, 0),  # noqa: SLF001
                         [["Order (/orders/[id])", "no record to open it on: its list page links to none"]])
        self.assertEqual(e2e_review.screens(self.workspace, "pages"), [])


class ThePageReviewTests(Workspace):
    def test_only_page_pictures_are_pages_and_only_test_pictures_are_tests(self):
        for name in ("a.png", "b.png"):
            (self.workspace / name).write_bytes(b"png")
        run = {"at": "1", "rank": 1, "source": "test-results/results.json", "tests": [
            {"file": "pages.spec.js", "title": "Home (/)", "suite": "@pages signed out", "project": "desktop",
             "status": "passed", "screenshot": "a.png"},
            {"file": "UJ-001.spec.js", "title": "[UJ-001] Buy", "project": "desktop", "status": "passed", "screenshot": "b.png"}]}
        with mock.patch.object(e2e_review.build_evidence, "_runs_found", return_value=[run]):
            pages = e2e_review.screens(self.workspace, "pages")
            tests = e2e_review.screens(self.workspace)
        self.assertEqual([g["title"] for g in pages], ["Home (/)"])
        self.assertEqual(e2e_review._opened_as(pages[0]), "signed out")  # noqa: SLF001
        self.assertEqual([g["title"] for g in tests], ["[UJ-001] Buy"])

    def test_a_round_photographs_only_the_pages_that_had_problems_and_never_runs_the_journeys(self):
        groups = [{"file": "pages.spec.js", "title": "Home (/)", "suite": "@pages signed out", "kind": "pages",
                   "status": "passed", "pictures": {"desktop": "a.png"}}]
        (self.workspace / "a.png").write_bytes(b"one")
        bad = {"file": "pages.spec.js", "title": "Home (/)", "name": "Home (/)", "looks_ok": False, "summary": "",
               "defects": [{"severity": "high", "viewport": "both", "where": "header", "problem": "cut off", "fix": "wrap"}],
               "thumbs": [], "heading": "### Home (/) — opened signed out (desktop)"}
        with mock.patch.object(e2e_review, "screens", return_value=groups), \
                mock.patch.object(e2e_review, "_review_group", return_value=bad), \
                mock.patch.object(e2e_review.screen_review, "tell"), mock.patch.object(e2e_review.bus, "progress"), \
                mock.patch.object(e2e_review.screen_review, "run_fix", return_value="") as fixed, \
                mock.patch.object(e2e_run, "pages", return_value={"status": "done"}) as photographed, \
                mock.patch.object(e2e_run, "run") as journeys, \
                mock.patch.object(e2e_review.screen_review, "next_round", return_value=False):
            result = e2e_review._review("p", self.session, "vision", groups, kind="pages", continue_plan=True)  # noqa: SLF001
        photographed.assert_called_once_with("p", self.session, titles=["Home (/)"])
        journeys.assert_not_called()
        self.assertIn("Fix what the pages show", fixed.call_args.args[2])
        self.assertTrue((self.workspace / e2e_review.PAGES_REPORT).is_file())
        self.assertEqual(result["kind"], "pages")

    def test_pages_already_looked_at_on_this_very_app_are_not_photographed_again(self):
        self.app()
        target = self.workspace / e2e_review.PAGES_REPORT
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"fingerprint": e2e_run.fingerprint(self.workspace)}), encoding="utf-8")
        with mock.patch.object(e2e_run, "pages") as photographed:
            self.assertEqual(e2e_review.run("p", self.session, kind="pages")["status"], "reused")
        photographed.assert_not_called()


class TheOrderTests(Workspace):
    def test_the_pages_come_before_the_journeys(self):
        order = mock.Mock()
        order.journeys.return_value = {"status": "passed"}
        order.fixes.return_value = ("", [])
        with mock.patch.object(e2e_review, "run", order.pages), mock.patch.object(e2e_run, "run", order.journeys), \
                mock.patch.object(e2e_run, "fix_request", order.fixes):
            sequence.screens_then_journeys("p", self.session)
        self.assertEqual([c[0] for c in order.mock_calls][:2], ["pages", "journeys"])
        self.assertEqual(order.pages.call_args.kwargs, {"kind": "pages", "continue_plan": True})


class JourneyRoundsTests(Workspace):
    def rounds(self, answers: list[bool], failing: list[list[str]]):
        asked: list[str] = []

        def next_round(project, session, agent, done, remaining, where, title, **kw):
            asked.append(kw.get("left", ""))
            return answers.pop(0)

        fixes = iter([(f"fix {ids}", ids) for ids in failing])
        with mock.patch.object(sequence.screen_review, "next_round", next_round), \
                mock.patch.object(e2e_run, "fix_request", lambda workspace: next(fixes, ("", []))), \
                mock.patch.object(e2e_run, "run") as reran:
            done = sequence.journey_rounds("p", self.session, {"status": "failed"})
        return done, asked, reran

    def test_every_journey_passing_asks_nothing(self):
        done, asked, reran = self.rounds([], [[]])
        self.assertEqual((done, asked), (0, []))
        reran.assert_not_called()

    def test_yes_fixes_the_failing_ones_and_runs_only_them_again_and_asks_again_while_some_fail(self):
        done, asked, reran = self.rounds([True, True], [["UJ-001", "UJ-005"], ["UJ-005"], []])
        self.assertEqual(done, 2)
        self.assertEqual(asked, ["2 journeys still fail (UJ-001, UJ-005)", "1 journey still fails (UJ-005)"])
        self.assertEqual([c.kwargs["grep"] for c in reran.call_args_list], [["UJ-001", "UJ-005"], ["UJ-005"]])
        self.assertEqual(self.session.fixes, ["fix ['UJ-001', 'UJ-005']", "fix ['UJ-005']"])

    def test_no_moves_on_without_fixing_or_running_anything(self):
        done, asked, reran = self.rounds([False], [["UJ-001"]])
        self.assertEqual(done, 0)
        self.assertEqual(len(asked), 1)
        reran.assert_not_called()
        self.assertEqual(self.session.fixes, [])

    def test_a_run_that_did_not_happen_has_no_rounds(self):
        with mock.patch.object(e2e_run, "fix_request") as fixes:
            self.assertEqual(sequence.journey_rounds("p", self.session, {"status": "build_failed"}), 0)
        fixes.assert_not_called()


class AfterTheJourneysTests(Workspace):
    def full_run(self) -> None:
        e2e_run._save(self.workspace, {"full": {"at": 1, "exit_code": 0, "fingerprint": e2e_run.fingerprint(self.workspace)}})  # noqa: SLF001

    def test_nothing_changed_means_no_runtime_test(self):
        self.app()
        self.full_run()
        with mock.patch.object(e2e_run, "runtime_check") as runtime:
            self.assertEqual(sequence.after_changes("p", self.session)["status"], "unchanged")
        runtime.assert_not_called()

    def test_a_change_is_checked_with_the_runtime_test_and_the_journeys_run_stays_the_apps(self):
        self.app()
        self.full_run()
        (self.workspace / "e2e" / "smoke.spec.js").write_text("// changed for accessibility", encoding="utf-8")
        with mock.patch.object(e2e_run, "runtime_check", return_value={"status": "passed"}) as runtime, \
                mock.patch.object(e2e_run, "run") as journeys:
            sequence.after_changes("p", self.session)
        runtime.assert_called_once()
        journeys.assert_not_called()
        self.assertTrue(e2e_run.current(self.workspace))
        self.assertEqual(len(e2e_run.record(self.workspace)["full"]["carried_over"]), 1)

    def test_a_failing_runtime_test_is_asked_about_yes_fixes_and_checks_again(self):
        self.app()
        self.full_run()
        (self.workspace / "app.js").write_text("// changed", encoding="utf-8")
        checks = iter([{"status": "failed", "output": "TypeError: x is undefined"}, {"status": "passed"}])
        with mock.patch.object(e2e_run, "runtime_check", lambda project, session: next(checks)), \
                mock.patch.object(sequence.screen_review, "next_round", return_value=True) as asked:
            result = sequence.after_changes("p", self.session)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(asked.call_args.kwargs["left"], "the runtime test still fails")
        self.assertIn("TypeError: x is undefined", self.session.fixes[0])
        self.assertTrue(e2e_run.current(self.workspace))

    def test_no_leaves_a_failing_runtime_test_as_it_is_and_the_journeys_run_is_not_carried_over(self):
        self.app()
        self.full_run()
        (self.workspace / "app.js").write_text("// changed", encoding="utf-8")
        with mock.patch.object(e2e_run, "runtime_check", return_value={"status": "failed", "output": "boom"}), \
                mock.patch.object(sequence.screen_review, "next_round", return_value=False):
            self.assertEqual(sequence.after_changes("p", self.session)["status"], "failed")
        self.assertFalse(e2e_run.current(self.workspace))

    def test_the_runtime_test_is_the_build_then_every_page_opens_on_desktop(self):
        self.app()
        ran: list[list[str]] = []

        def execute(project, session, command, env, seconds, label):
            ran.append(command)
            playwright(self.workspace, [("smoke.spec.js", "Home opens", "desktop", "passed")])
            return {"exit_code": 0, "timed_out": False, "output": "", "seconds": 2}

        with mock.patch.object(e2e_run, "_execute", execute), mock.patch.object(e2e_run, "_build_if_needed", return_value=None), \
                mock.patch.object(e2e_run, "command_environment", return_value={}), mock.patch.object(e2e_run.live, "finish"):
            result = e2e_run.runtime_check("p", self.session)
        self.assertEqual(result["status"], "passed")
        self.assertIn(e2e_run.RUNTIME_SPEC, ran[0])
        self.assertIn("--project=desktop", ran[0])

    def test_a_runtime_test_whose_build_fails_runs_no_page(self):
        self.app()
        with mock.patch.object(e2e_run, "_build_if_needed", return_value={"exit_code": 1, "output": "Module not found"}), \
                mock.patch.object(e2e_run, "command_environment", return_value={}), \
                mock.patch.object(e2e_run, "_execute") as execute:
            result = e2e_run.runtime_check("p", self.session)
        self.assertEqual((result["status"], result["stage"]), ("failed", "build"))
        execute.assert_not_called()


if __name__ == "__main__":
    unittest.main()
