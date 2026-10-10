"""A model that can look at pictures reviews every screen of the React prototype, and what it finds is fixed (or skipped, saying why)."""
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

from ollama_terminal import screenshot  # noqa: E402
from prototype_agent import screens, visual_review  # noqa: E402
from server_modules import bus, config, screen_review  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402

ROWS = [{"route": "/", "file": "app/src/pages/home.tsx", "name": "Home", "roles": [], "signed_in": False},
        {"route": "/orders", "file": "app/src/pages/orders.tsx", "name": "Orders", "roles": [], "signed_in": False},
        {"route": "/dashboard", "file": "app/src/pages/dashboard.tsx", "name": "Dashboard", "roles": ["admin"], "signed_in": True}]
ACCOUNTS = [{"role": "Admin", "role_key": "admin", "email": "ada@example.test", "can_open": [{"route": "/dashboard"}]}]

OK = {"page": "x", "looks_ok": True, "summary": "Looks right.", "defects": []}


def defect(severity="high", viewport="mobile", problem="The menu runs off the screen."):
    return {"severity": severity, "viewport": viewport, "where": "the top menu", "problem": problem, "fix": "wrap it"}


class FakeSession:
    """What the review asks of a project's session: its folder, the model in use, Stop, and one agent turn to fix things."""

    def __init__(self, folder: Path, model: str = "vision-model", fix=None):
        self.record = folder / ".agentforge"
        self.root = self.record / "prototype"
        self.root.mkdir(parents=True)
        (self.root / "app" / "src" / "pages").mkdir(parents=True)
        (self.root / "app" / "src" / "index.css").write_text("body{}", encoding="utf-8")
        for row in ROWS:
            (self.root / row["file"]).write_text(f"export default () => <h1>{row['name']}</h1>", encoding="utf-8")
        self.cancelled = False
        self.model = model
        self.fix = fix
        self.requests: list[str] = []

    def agent(self, model: str = ""):
        return SimpleNamespace(model=self.model)

    def run_direct(self, request: str, model: str = ""):
        self.requests.append(request)
        if self.fix:
            self.fix(self.root)
        return {"status": "complete", "text": "Fixed.", "rounds": 1}


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.messages: list[dict] = []
        self.phases: list[tuple] = []
        for patch in (
            mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                              self.messages.append({"text": text, "title": title, "kind": kind, "images": images or []})),
            mock.patch.object(bus, "phase", lambda project, key, title, status="active", detail="", number=0, kind="run", agent="":
                              self.phases.append((key, status))),
            mock.patch.object(bus, "progress", lambda *a, **k: None),
            mock.patch.object(bus, "log", lambda *a, **k: None),
            mock.patch.object(config, "setting", lambda name, fallback=None: True if name == "prototype_visual_review" else fallback),
            mock.patch("server_modules.vision.supports", return_value=True),
            mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")),
            mock.patch("server_modules.screen_review.next_round", side_effect=self._next_round),
        ):
            patch.start()
            self.addCleanup(patch.stop)
        self.pictures: list[tuple[str, str]] = []

    def capture(self, root, pages, accounts, viewports=screens.VIEWPORTS, on_done=None, cancelled=None):
        """Stands in for the browser: a small PNG per page and width."""
        shots = []
        for row in pages:
            for viewport in viewports:
                path = root / "review" / f"{Path(row['file']).stem}-{viewport}.png"
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(b"\x89PNG" + viewport.encode() * 200)
                self.pictures.append((row["file"], viewport))
                shots.append({"route": row["route"], "file": row["file"], "viewport": viewport,
                              "path": path.relative_to(root).as_posix(), "error": ""})
        return shots

    def answers(self, table):
        """The model's answer per page file: a dict, a list of them (one per ask), or an Exception."""
        asked: list[tuple[str, int]] = []
        counts: dict[str, int] = {}

        def complete_json(system, user, validator=None, label="", model="", images=None, project="", role="", **_):
            file = next(row["file"] for row in ROWS if f"file `{row['file']}`" in user)
            counts[file] = counts.get(file, 0) + 1
            asked.append((file, len(images or [])))
            value = table[file]
            value = value[min(counts[file], len(value)) - 1] if isinstance(value, list) else value
            if isinstance(value, Exception):
                raise value
            return validator(value) if validator else value

        self.asked = asked
        return mock.patch("server_modules.llm.complete_json", side_effect=complete_json)

    def run_review(self, session, answers, accounts=ACCOUNTS):
        with mock.patch.object(screens, "capture_all", self.capture), self.answers(answers):
            return visual_review.run("prj_review", session, ROWS, accounts)


    def _next_round(self, project, session, agent, done, remaining, where, title):
        """The person's answer to "Run round N?": what the test queued in `self.round_answers`, else No."""
        self.rounds_asked = getattr(self, "rounds_asked", [])
        self.rounds_asked.append((done, remaining, where))
        answers = getattr(self, "round_answers", [])
        return answers.pop(0) if answers else False

class SkipTests(Harness):
    def test_a_model_that_cannot_look_at_pictures_skips_the_review_and_says_so_in_the_chat(self):
        session = FakeSession(self.folder, model="plain-model")
        with mock.patch("server_modules.vision.supports", return_value=False), \
                mock.patch.object(screens, "capture_all", side_effect=AssertionError("photographed")):
            result = visual_review.run("p", session, ROWS, ACCOUNTS)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("cannot look at pictures", result["reason"])
        self.assertIn("vision", result["reason"])
        self.assertEqual([m["title"] for m in self.messages], ["Visual review skipped"])
        self.assertEqual(self.phases, [])

    def test_a_model_nobody_could_ask_about_is_skipped_not_assumed_blind_or_sighted(self):
        with mock.patch("server_modules.vision.supports", return_value=None):
            result = visual_review.run("p", FakeSession(self.folder), ROWS, ACCOUNTS)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("could not be found out", result["reason"])

    def test_a_computer_with_no_browser_that_works_skips_it_too(self):
        with mock.patch.object(screenshot, "working_browser", return_value=None):
            result = visual_review.run("p", FakeSession(self.folder), ROWS, ACCOUNTS)
        self.assertEqual(result["status"], "skipped")
        self.assertIn("no browser", result["reason"])

    def test_the_setting_turns_it_off_without_a_word(self):
        with mock.patch.object(config, "setting", lambda name, fallback=None: False if name == "prototype_visual_review" else fallback):
            self.assertEqual(visual_review.run("p", FakeSession(self.folder), ROWS, ACCOUNTS), {"status": "off"})
        self.assertEqual(self.messages, [])


class ReviewTests(Harness):
    def test_every_page_is_looked_at_with_both_its_pictures_and_a_page_that_looks_right_changes_nothing(self):
        session = FakeSession(self.folder)
        result = self.run_review(session, {r["file"]: OK for r in ROWS})
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["problems_found"], 0)
        self.assertEqual(sorted(self.asked), sorted((r["file"], 2) for r in ROWS))      # desktop and mobile each
        self.assertEqual(session.requests, [])                                          # nothing to fix: the agent is not asked
        self.assertIn("no problems found", self.messages[-1]["text"])
        self.assertEqual(self.phases[0][0], visual_review.PHASE)
        self.assertEqual(self.phases[-1], (visual_review.PHASE, "complete"))

    def test_the_chat_shows_each_pages_pictures_and_what_was_found_under_them(self):
        session = FakeSession(self.folder)
        answers = {"app/src/pages/home.tsx": OK, "app/src/pages/orders.tsx": {**OK, "looks_ok": False, "defects": [defect()]}, "app/src/pages/dashboard.tsx": OK}
        self.run_review(session, answers)
        shown = [m for m in self.messages if m["kind"] == "visual_review"]
        self.assertEqual(len(shown), 3)
        orders = next(m for m in shown if m["title"].startswith("Orders"))
        self.assertEqual(orders["title"], "Orders · 1 to fix")
        self.assertIn("**high** · mobile · the top menu: The menu runs off the screen.", orders["text"])
        self.assertEqual([i["label"] for i in orders["images"]], ["app/src/pages/orders.tsx · desktop", "app/src/pages/orders.tsx · mobile"])
        self.assertEqual(orders["images"][0]["path"], ".agentforge/prototype/review/orders-desktop.png")   # served by /qa-screenshot
        self.assertTrue(next(m for m in shown if m["title"].startswith("Home"))["title"].endswith("looks right"))

    def test_a_signed_in_page_is_described_to_the_model_as_shown_signed_in(self):
        prompts_seen = []

        def complete_json(system, user, validator=None, **_):
            prompts_seen.append(user)
            return validator(OK)
        session = FakeSession(self.folder)
        with mock.patch.object(screens, "capture_all", self.capture), mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            visual_review.run("p", session, ROWS, ACCOUNTS)
        dashboard = next(p for p in prompts_seen if "app/src/pages/dashboard.tsx" in p)
        self.assertIn("shown signed in as the demo account ada@example.test", dashboard)
        self.assertIn("shown signed out", next(p for p in prompts_seen if "file `app/src/pages/home.tsx`" in p))
        self.assertIn("picture 1 is the desktop width and picture 2 is the mobile width", dashboard)

    def test_the_problems_that_matter_are_given_to_the_agent_page_by_page_and_low_ones_are_left_alone(self):
        session = FakeSession(self.folder)
        answers = {"app/src/pages/home.tsx": OK,
                   "app/src/pages/orders.tsx": {**OK, "looks_ok": False, "defects": [defect("medium", "desktop", "The totals overlap the heading."), defect("low", "both", "Slightly uneven spacing.")]},
                   "app/src/pages/dashboard.tsx": {**OK, "looks_ok": False, "defects": [defect("high", "both", "The table is cut off.")]}}
        self.run_review(session, answers)
        request = session.requests[0]
        self.assertIn("### `app/src/pages/orders.tsx`", request)
        self.assertIn("The totals overlap the heading.", request)
        self.assertIn("### `app/src/pages/dashboard.tsx`", request)
        self.assertIn("The table is cut off.", request)
        self.assertNotIn("uneven spacing", request)                    # a low one is reported, not fixed
        self.assertNotIn("### `app/src/pages/home.tsx`", request)
        self.assertLess(request.index("### `app/src/pages/orders.tsx`"), request.index("### `app/src/pages/dashboard.tsx`"))   # in the order of the pages

    def test_after_the_fix_only_the_pages_that_changed_are_photographed_and_looked_at_again(self):
        def fix(root):
            (root / "app/src/pages/orders.tsx").write_text("export default () => <h1>Orders, fixed</h1>", encoding="utf-8")

        session = FakeSession(self.folder, fix=fix)
        answers = {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK,
                   "app/src/pages/orders.tsx": [{**OK, "looks_ok": False, "defects": [defect()]}, OK]}
        result = self.run_review(session, answers)
        self.assertEqual(result["fixed_pages"], ["app/src/pages/orders.tsx"])
        again = [f for f, _ in self.asked]
        self.assertEqual(again.count("app/src/pages/orders.tsx"), 2)
        self.assertEqual(again.count("app/src/pages/home.tsx"), 1)
        self.assertEqual(self.pictures.count(("app/src/pages/orders.tsx", "desktop")), 2)
        self.assertEqual(self.pictures.count(("app/src/pages/home.tsx", "desktop")), 1)
        self.assertEqual(result["remaining"], [])
        self.assertIn("1 problem found, 1 screen changed to fix them; none left that matters.", self.messages[-1]["text"])

    def test_a_changed_shared_file_means_every_page_is_looked_at_again(self):
        session = FakeSession(self.folder, fix=lambda root: (root / "app" / "src" / "index.css").write_text("body{margin:0}", encoding="utf-8"))
        answers = {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK, "app/src/pages/orders.tsx": [{**OK, "defects": [defect()]}, OK]}
        result = self.run_review(session, answers)
        self.assertEqual(sorted(result["fixed_pages"]), ["app/src/pages/dashboard.tsx", "app/src/pages/home.tsx", "app/src/pages/orders.tsx"])
        self.assertEqual(len(self.asked), 6)

    def test_the_app_is_bundled_again_after_the_fix_and_before_the_pages_are_photographed_again(self):
        order: list[str] = []

        def fix(root):
            order.append("fix")
            (root / "app/src/pages/orders.tsx").write_text("export default () => <h1>fixed</h1>", encoding="utf-8")

        session = FakeSession(self.folder, fix=fix)
        answers = {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK,
                   "app/src/pages/orders.tsx": [{**OK, "looks_ok": False, "defects": [defect()]}, OK]}

        def capture(root, pages, accounts, viewports=screens.VIEWPORTS, on_done=None, cancelled=None):
            order.append("photograph " + ",".join(Path(p["file"]).stem for p in pages))
            return self.capture(root, pages, accounts, viewports, on_done, cancelled)

        with mock.patch.object(screens, "capture_all", capture), self.answers(answers):
            visual_review.run("p", session, ROWS, ACCOUNTS, rebuild=lambda: order.append("bundle"))
        self.assertEqual(order, ["photograph home,orders,dashboard", "fix", "bundle", "photograph orders"])

    def test_without_a_fix_the_app_is_not_bundled_again(self):
        bundled: list[int] = []
        session = FakeSession(self.folder)
        with mock.patch.object(screens, "capture_all", self.capture), self.answers({r["file"]: OK for r in ROWS}):
            visual_review.run("p", session, ROWS, ACCOUNTS, rebuild=lambda: bundled.append(1))
        self.assertEqual(bundled, [])

    def test_a_problem_still_there_after_the_fix_is_reported_as_it_is_never_fixed_twice(self):
        session = FakeSession(self.folder, fix=lambda root: (root / "app/src/pages/orders.tsx").write_text("export default () => <h1>changed</h1>", encoding="utf-8"))
        still = {**OK, "looks_ok": False, "defects": [defect(problem="The menu still runs off the screen.")]}
        result = self.run_review(session, {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK, "app/src/pages/orders.tsx": still})
        self.assertEqual(len(session.requests), 1)
        self.assertEqual([r["problem"] for r in result["remaining"]], ["The menu still runs off the screen."])
        self.assertIn("1 still visible after the fix.", self.messages[-1]["text"])

    def test_a_fix_that_stops_partway_does_not_end_the_review_what_it_changed_is_looked_at_anyway(self):
        def fix(root):
            (root / "app/src/pages/orders.tsx").write_text("export default () => <h1>half fixed</h1>", encoding="utf-8")
            raise ssl.SSLError(1, "[SSL: SSLV3_ALERT_BAD_RECORD_MAC] sslv3 alert bad record mac (_ssl.c:2580)")

        session = FakeSession(self.folder, fix=fix)
        answers = {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK, "app/src/pages/orders.tsx": [{**OK, "looks_ok": False, "defects": [defect()]}, OK]}
        result = self.run_review(session, answers)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["fixed_pages"], ["app/src/pages/orders.tsx"])                         # what it had changed is still checked
        self.assertIn("BAD_RECORD_MAC", result["fix_stopped"])
        self.assertEqual([f for f, _ in self.asked].count("app/src/pages/orders.tsx"), 2)
        self.assertTrue(any(m["text"].startswith("The fix stopped before it was finished") for m in self.messages))
        self.assertIn("The fix stopped before it was finished (", self.messages[-1]["text"])
        self.assertEqual(self.phases[-1], (visual_review.PHASE, "complete"))

    def test_stop_during_the_fix_still_ends_the_review(self):
        def fix(root):
            raise RunCancelled("p")

        with self.assertRaises(RunCancelled):
            self.run_review(FakeSession(self.folder, fix=fix),
                            {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK, "app/src/pages/orders.tsx": {**OK, "defects": [defect()]}})

    def test_the_report_is_saved_beside_the_pictures(self):
        session = FakeSession(self.folder)
        self.run_review(session, {r["file"]: OK for r in ROWS})
        report = json.loads((session.root / "review" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual((report["model"], report["pages"], report["problems_found"]), ("vision-model", 3, 0))

    def test_a_page_the_model_failed_on_is_named_and_the_others_still_count(self):
        session = FakeSession(self.folder)
        result = self.run_review(session, {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK, "app/src/pages/orders.tsx": ValueError("no valid JSON")})
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["pages_not_reviewed"], ["Orders"])
        self.assertIn("Could not be reviewed: Orders.", self.messages[-1]["text"])

    def test_a_browser_that_could_not_draw_a_single_screen_ends_the_review_without_failing_anything(self):
        session = FakeSession(self.folder)
        broken = [{"route": r["route"], "file": r["file"], "viewport": v, "path": "", "error": "took too long"}
                  for r in ROWS for v in screens.VIEWPORTS]
        with mock.patch.object(screens, "capture_all", return_value=broken):
            result = visual_review.run("p", session, ROWS, ACCOUNTS)
        self.assertEqual(result["status"], "failed")
        self.assertIn("could not draw any screen", result["reason"])
        self.assertEqual(self.phases[-1], (visual_review.PHASE, "failed"))

    def test_an_error_anywhere_in_the_review_is_never_raised_into_the_prototype(self):
        session = FakeSession(self.folder)
        with mock.patch.object(screens, "capture_all", side_effect=RuntimeError("disk full")):
            result = visual_review.run("p", session, ROWS, ACCOUNTS)
        self.assertEqual((result["status"], result["reason"]), ("failed", "disk full"))

    def test_stop_ends_the_review_with_the_runs_own_cancellation(self):
        session = FakeSession(self.folder)
        session.cancelled = True
        with mock.patch.object(screens, "capture_all", self.capture), self.answers({r["file"]: OK for r in ROWS}), \
                self.assertRaises(RunCancelled):
            visual_review.run("p", session, ROWS, ACCOUNTS)


class ReviewOnlyTests(Harness):
    def test_a_review_only_looks_and_reports_and_never_asks_the_agent_to_change_anything(self):
        session = FakeSession(self.folder)
        answers = {"app/src/pages/home.tsx": OK, "app/src/pages/orders.tsx": {**OK, "looks_ok": False, "defects": [defect(), defect("medium")]}, "app/src/pages/dashboard.tsx": OK}
        with mock.patch.object(screens, "capture_all", self.capture), self.answers(answers):
            result = visual_review.run("p", session, ROWS, ACCOUNTS, fix=False)
        self.assertEqual(session.requests, [])
        self.assertEqual(result["problems_found"], 2)
        self.assertEqual(result["fixed_pages"], [])
        self.assertIn("2 problems found; nothing was changed, this was a review only.", self.messages[-1]["text"])

    def test_it_runs_when_asked_for_even_if_the_setting_turns_it_off_and_the_model_given_is_the_one_used(self):
        picked = []

        class Session(FakeSession):
            def agent(self, model: str = ""):
                picked.append(model)
                return SimpleNamespace(model=model or "project-model")

        off = lambda name, fallback=None: False if name == "prototype_visual_review" else fallback  # noqa: E731
        with mock.patch.object(config, "setting", off):
            self.assertEqual(visual_review.run("p", Session(self.folder), ROWS, ACCOUNTS)["status"], "off")
            with mock.patch.object(screens, "capture_all", self.capture), self.answers({r["file"]: OK for r in ROWS}):
                forced = visual_review.run("p", Session(self.folder / "x"), ROWS, ACCOUNTS, model="vision-model", force=True)
        self.assertEqual(forced["status"], "done")
        self.assertEqual(forced["model"], "vision-model")
        self.assertIn("vision-model", picked)


class FingerprintTests(Harness):
    def test_a_page_is_its_own_file_and_everything_else_in_the_source_is_shared(self):
        session = FakeSession(self.folder)
        before = visual_review._fingerprint(session.root, ROWS)
        (session.root / "app/src/pages/orders.tsx").write_text("export default () => <h1>again</h1>", encoding="utf-8")
        after = visual_review._fingerprint(session.root, ROWS)
        changed = {name for name in before if before[name] != after[name]}
        self.assertEqual(changed, {"app/src/pages/orders.tsx"})
        (session.root / "app/src/components").mkdir()
        (session.root / "app/src/components/shell.tsx").write_text("export const Shell = () => null", encoding="utf-8")
        self.assertNotEqual(after[visual_review.SHARED], visual_review._fingerprint(session.root, ROWS)[visual_review.SHARED])

    def test_the_bundle_and_the_packages_are_not_part_of_what_the_pages_share(self):
        session = FakeSession(self.folder)
        before = visual_review._fingerprint(session.root, ROWS)
        (session.root / "app" / "bundle.html").write_text("<html></html>", encoding="utf-8")
        (session.root / "app" / "node_modules").mkdir()
        (session.root / "app" / "node_modules" / "x.js").write_text("1", encoding="utf-8")
        self.assertEqual(before, visual_review._fingerprint(session.root, ROWS))


class AnswerTests(unittest.TestCase):
    def test_the_models_answer_is_cleaned_and_a_malformed_one_says_what_to_fix(self):
        clean = visual_review._clean({"looks_ok": True, "summary": "ok", "defects": [
            {"severity": "LOW", "viewport": "tablet", "problem": "a"}, {"severity": "high", "problem": "b", "where": "x"},
            {"problem": "  "}, "junk", {"severity": "weird", "problem": "c"}]})
        self.assertEqual([(d["severity"], d["viewport"], d["problem"]) for d in clean["defects"]],
                         [("high", "both", "b"), ("medium", "both", "c"), ("low", "both", "a")])   # worst first
        self.assertFalse(clean["looks_ok"])                                                       # it listed problems: not ok
        for bad, message in (("text", "one JSON object"), ({"looks_ok": True}, '"defects" must be a list')):
            with self.subTest(bad=bad), self.assertRaisesRegex(ValueError, message):
                visual_review._clean(bad)

    def test_at_most_eight_problems_per_page(self):
        many = {"defects": [{"severity": "medium", "problem": f"p{i}"} for i in range(20)]}
        self.assertEqual(len(visual_review._clean(many)["defects"]), visual_review.MAX_DEFECTS)


class ReadsPicturesTests(Harness):
    def test_the_pictures_go_to_the_model_as_bytes_desktop_first(self):
        captured = {}

        def complete_json(system, user, validator=None, images=None, **_):
            captured["images"] = images
            return validator(OK)
        session = FakeSession(self.folder)
        with mock.patch.object(screens, "capture_all", self.capture), mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            visual_review.run("p", session, ROWS[:1], ACCOUNTS)
        self.assertEqual([i[:4] for i in captured["images"]], [b"\x89PNG", b"\x89PNG"])
        self.assertIn(b"desktop", captured["images"][0])
        self.assertIn(b"mobile", captured["images"][1])


if __name__ == "__main__":
    unittest.main()


class RoundTests(Harness):
    """After the first round of look, fix, look again, each further round is asked for - and only while problems are left."""

    def still_wrong_then(self, after):
        counter = [0]

        def fix(root):
            counter[0] += 1
            (root / "app/src/pages/orders.tsx").write_text(f"export default () => <h1>Orders {counter[0]}</h1>", encoding="utf-8")

        bad = {**OK, "looks_ok": False, "defects": [defect()]}
        return FakeSession(self.folder, fix=fix), {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK,
                                                   "app/src/pages/orders.tsx": [bad, bad, *after]}

    def test_nothing_is_asked_when_the_first_round_leaves_nothing_to_fix(self):
        def fix(root):
            (root / "app/src/pages/orders.tsx").write_text("export default () => <h1>fixed</h1>", encoding="utf-8")

        session = FakeSession(self.folder, fix=fix)
        self.run_review(session, {"app/src/pages/home.tsx": OK, "app/src/pages/dashboard.tsx": OK,
                                  "app/src/pages/orders.tsx": [{**OK, "looks_ok": False, "defects": [defect()]}, OK]})
        self.assertEqual(getattr(self, "rounds_asked", []), [])

    def test_with_problems_left_the_person_is_asked_and_no_ends_the_review(self):
        session, answers = self.still_wrong_then([OK])
        result = self.run_review(session, answers)
        self.assertEqual(self.rounds_asked, [(1, 1, "1 screen")])
        self.assertEqual(len(session.requests), 1)                      # no second fix
        self.assertEqual(len(result["remaining"]), 1)
        self.assertEqual([r["round"] for r in result["rounds"]], [1])

    def test_yes_runs_another_round_on_only_what_is_still_wrong(self):
        self.round_answers = [True]
        session, answers = self.still_wrong_then([OK])
        result = self.run_review(session, answers)
        self.assertEqual(len(session.requests), 2)
        self.assertIn("orders.tsx", session.requests[1])
        self.assertNotIn("home.tsx", session.requests[1])
        self.assertEqual(result["remaining"], [])
        self.assertEqual([r["round"] for r in result["rounds"]], [1, 2])
        self.assertEqual(len(self.rounds_asked), 1)                     # nothing left after round 2: not asked again
        self.assertEqual([f for f, _ in self.asked].count("app/src/pages/home.tsx"), 1)


class NextRoundTests(unittest.TestCase):
    """The question itself: a Yes/No card the run holds still for."""

    def setUp(self):
        self.said: list[str] = []
        self.enterContext(mock.patch.object(bus, "agent_msg", lambda project, text, **kw: self.said.append(text)))
        self.session = SimpleNamespace(cancelled=False)

    def ask(self, reply, **overrides):
        args = {"done": 1, "remaining": 3, "where": "2 screens"} | overrides
        with mock.patch.object(bus, "ask_and_wait", return_value=reply) as asked:
            answer = screen_review.next_round("p", self.session, "designer", args["done"], args["remaining"], args["where"],
                                              "Visual review")
        return answer, asked

    def test_yes_in_any_of_its_forms_runs_the_next_round(self):
        for reply in ("Yes", "yes please", "ow", "ඔව්", "OK"):
            self.assertTrue(self.ask(reply)[0], reply)

    def test_no_or_leaving_it_to_the_agent_ends_the_review(self):
        for reply in ("No", "", "not now"):
            self.assertFalse(self.ask(reply)[0], reply)

    def test_the_card_is_a_quick_yes_no_question_saying_what_is_left(self):
        _answer, asked = self.ask("Yes")
        args, kwargs = asked.call_args
        self.assertEqual(args[1], "question")
        self.assertIn("round 1 is done", args[2])
        self.assertIn("3 problems", args[2])
        self.assertIn("Run round 2", args[2])
        self.assertEqual([o["label"] for o in kwargs["options"]], ["Yes", "No"])
        self.assertTrue(kwargs["quick"])

    def test_nothing_left_is_never_asked(self):
        answer, asked = self.ask("Yes", remaining=0)
        self.assertFalse(answer)
        asked.assert_not_called()

    def test_the_review_stops_at_the_most_rounds_without_asking(self):
        answer, asked = self.ask("Yes", done=screen_review.MAX_ROUNDS)
        self.assertFalse(answer)
        asked.assert_not_called()

    def test_stop_while_waiting_stops_the_run(self):
        from server_modules.session import RunCancelled

        with self.assertRaises(RunCancelled):
            self.ask(None)
