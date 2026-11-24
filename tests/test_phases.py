"""The build as numbered phases: the whole application is built however big it is, and a page that is not built fails the build by name."""
from __future__ import annotations

import json
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from builder_agent import build, journey_contract, phases  # noqa: E402
from server_modules import bus  # noqa: E402
from server_modules.session import PHASE_PLANNING_STEPS, PHASE_REPAIRS, Phases, ProjectSession, RunCancelled  # noqa: E402

REQUEST = ("# One sequential plan\n\nIntro.\n\n## Phase 1 — complete the real application\n\nFinish the entire application first. "
           "Report: REPORT-TEMPLATE-PATH.\n\n## Phase 2 — read the completed app and test business logic\n\nWrite UNIT-TEST-TEXT.\n\n"
           "## Phase 3 — reread the sources and run final product checks\n\nRun FINAL-CHECK-TEXT.\n")


def page(route, name=None, file=None, roles=("Visitor",)):
    return {"route": route, "file": file or (route.strip("/").replace("/", "-") or "index") + ".html", "name": name or route,
            "roles": list(roles)}


def routes(count):
    return [page(f"/page-{n}", f"Page {n}") for n in range(1, count + 1)]


class Workspace(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.record = self.workspace / ".agentforge"
        (self.record / "build").mkdir(parents=True)

    def prototype(self, rows):
        (self.record / "prototype").mkdir(parents=True, exist_ok=True)
        (self.record / "prototype" / "routes.json").write_text(json.dumps({"routes": rows}), encoding="utf-8")

    def progress(self, rows):
        (self.record / "build" / "progress.json").write_text(json.dumps({"routes": rows}), encoding="utf-8")

    def write(self, name, text="x = 1\n"):
        path = self.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


class RoutesTests(Workspace):
    def test_the_pages_are_the_approved_prototypes_in_its_own_order(self):
        self.prototype([page("/", "Home"), page("/phones", "Phones", roles=("Visitor", "Customer"))])
        rows = phases.routes_of(self.workspace)
        self.assertEqual([r["route"] for r in rows], ["/", "/phones"])
        self.assertEqual(rows[1]["roles"], ["Visitor", "Customer"])
        self.assertEqual(rows[0]["name"], "Home")

    def test_rows_without_a_route_and_repeats_are_left_out_and_no_prototype_means_no_pages(self):
        self.prototype([page("/a"), {"file": "x.html"}, "nonsense", page("/a", "again"), {"route": "  "}])
        self.assertEqual([r["route"] for r in phases.routes_of(self.workspace)], ["/a"])
        self.assertEqual(phases.routes_of(self.workspace / "nowhere"), [])
        (self.record / "prototype" / "routes.json").write_text("not json", encoding="utf-8")
        self.assertEqual(phases.routes_of(self.workspace), [])


class PlanTests(unittest.TestCase):
    def test_first_journey_is_after_foundation_and_owns_its_routes_once(self):
        rows = routes(6)
        first = {"id": "UJ-001", "name": "Place an order", "routes": ["/page-1", "/page-4"]}
        items = phases.plan(rows, first)
        self.assertEqual([item["kind"] for item in items[:3]], ["foundation", "first-journey", "pages"])
        self.assertEqual(items[2]["routes"], ["/page-2", "/page-3", "/page-5", "/page-6"])
        self.assertTrue(items[1]["required"])
        self.assertIn("e2e/journeys/UJ-001.spec.js", phases.request_for(items[1], 2, len(items), rows))

    def test_contract_preserves_approved_route_actor_outcome_and_sample_data(self):
        source = {"journeys": [{"id": "UJ-001", "workflow_name": "Order review", "who": "Customer", "steps": [
            {"id": "UJ-001-S01", "step": "Place an order", "route": "/page-1", "expected_outcome": "Order is saved"},
            {"id": "UJ-001-S02", "step": "The Admin approves it", "route": "/page-2", "test_data": {"status": "pending"}},
        ]}]}
        session = mock.Mock()
        session.read_record.return_value = source
        _, first = journey_contract.stage(session, {"roles": [{"role_name": "Admin"}]}, routes(3))
        self.assertEqual([step["actor"] for step in first["steps"]], ["Customer", "Admin"])
        self.assertEqual(first["steps"][0]["expected_outcome"], "Order is saved")
        self.assertEqual(first["steps"][1]["test_data"], {"status": "pending"})
        self.assertEqual(first["steps"][1]["prototype_file"], "page-2.html")
        session.write_record.assert_called_once()

    def test_a_big_application_is_split_into_the_foundation_pages_a_few_at_a_time_and_what_comes_after(self):
        items = phases.plan(routes(22))
        self.assertEqual([i["kind"] for i in items], ["foundation"] + ["pages"] * 6 + ["wiring", "tests", "checks"])
        self.assertEqual(len({i["id"] for i in items}), len(items))
        self.assertTrue(all(i["status"] == "pending" for i in items))
        pages = [i for i in items if i["kind"] == "pages"]
        self.assertEqual([len(i["routes"]) for i in pages], [4, 4, 4, 4, 4, 2])
        self.assertEqual(sum((i["routes"] for i in pages), []), [r["route"] for r in routes(22)])          # every page, once
        self.assertIn("Pages 1–4 of 22", pages[0]["title"])
        self.assertIn("Page 1", pages[0]["title"])
        self.assertIn("Pages 21–22 of 22", pages[-1]["title"])

    def test_one_page_and_no_page(self):
        one = phases.plan(routes(1))
        self.assertEqual([i["kind"] for i in one], ["foundation", "pages", "wiring", "tests", "checks"])
        self.assertIn("Page 1 of 1: Page 1", one[1]["title"])
        self.assertEqual([i["kind"] for i in phases.plan([])], ["foundation", "wiring", "tests", "checks"])

    def test_every_phase_says_in_plain_words_what_it_is_about_to_build(self):
        for item in phases.plan(routes(9)):
            self.assertTrue(item["detail"].strip(), item["id"])
        self.assertIn("Page 1, Page 2, Page 3, Page 4", phases.plan(routes(9))[1]["detail"])


class RequestTests(unittest.TestCase):
    def ask(self, item, number=2, total=9, rows=None):
        return phases.request_for(item, number, total, rows or routes(9))

    def test_a_phase_is_numbered_scoped_and_forbids_cutting_the_application_down(self):
        items = phases.plan(routes(9))
        text = self.ask(items[1], number=2, total=6)
        self.assertIn("# Phase 2 of 6 — Pages 1–4 of 9", text)
        self.assertIn("Never cut the application down", text)
        self.assertIn("coherent subset", text)
        self.assertIn("one or two plain sentences", text)                  # so the chat has words in it, not only files
        self.assertIn("Stay inside this phase", text)

    def test_the_pages_phase_lists_every_one_of_its_pages_with_its_prototype_page_and_asks_for_the_progress_record(self):
        rows = [page("/rooms", "Rooms", "rooms.html", ("Guest", "Staff")), page("/book", "Book", "book.html")] + routes(7)
        items = phases.plan(rows)
        text = self.ask(items[1], rows=rows)
        self.assertIn("`/rooms` — Rooms — prototype page `.agentforge/prototype/rooms.html` — roles: Guest, Staff", text)
        self.assertIn("`/book` — Book — prototype page `.agentforge/prototype/book.html`", text)
        self.assertNotIn("`/page-5`", text)                                 # the next phase's
        self.assertIn(".agentforge/build/progress/pages-1.json", text)
        self.assertIn('{"routes": {"/the/route"', text)

    def test_the_foundation_leaves_pages_seeding_and_tests_to_their_phases(self):
        items = phases.plan(routes(5))
        self.assertIn("Do **not** build the pages themselves, seed the database, or write or run tests", self.ask(items[0]))
        wiring = self.ask(items[-3])
        self.assertIn("the seed script", wiring)
        self.assertIn("Stop once wiring, seeding and compilation are verified", wiring)
        self.assertNotIn("Finish the entire application first", wiring)

    def test_unit_tests_and_browser_specs_have_separate_tasks(self):
        items = phases.plan(routes(5))
        tests, checks = self.ask(items[-2]), self.ask(items[-1])
        self.assertIn("Run that unit suite", tests)
        self.assertNotIn("e2e/journeys/", tests)
        self.assertIn("Stop\nafter writing the specs and route list", checks)
        self.assertNotIn("Run that unit suite", checks)

    def test_small_planner_brief_keeps_all_routes_in_the_fallback(self):
        rows = routes(30)
        items = phases.plan(rows)
        brief = phases.planning_prompt("nextjs-supabase", items, rows, {
            "app_name": "Shelf Check", "collections": [{"name": "stock"}],
            "authentication": {"login_required": False}, "workflows": [{"workflow_name": "Restock"}],
        }, "Approved theme: teal")
        for value in ("Shelf Check", "stock", "Restock", "Approved theme: teal", "/page-1", "6 additional routes"):
            self.assertIn(value, brief)
        self.assertNotIn("`/page-30`", brief)
        fallback = phases.fallback_plan(items, rows)
        for row in rows:
            self.assertIn(f"`{row['route']}`", fallback)

    def test_a_phase_that_is_not_finished_is_asked_for_again_with_what_is_missing(self):
        item = phases.plan(routes(5))[1]
        text = phases.repair_for(item, 2, 5, ["`/a` is not recorded", "`/b` is recorded, but none of the files exists"])
        self.assertIn("not finished yet", text)
        self.assertIn("- `/a` is not recorded", text)
        self.assertIn("do not decide that a page is out of scope", text)


class DeliveryTests(Workspace):
    def pages_phase(self, count=3):
        return phases.plan(routes(count))[1]

    def test_a_page_is_built_when_it_has_an_entry_naming_files_that_exist(self):
        self.write("client/a.jsx")
        self.progress({"/page-1": ["client/a.jsx"], "/page-2": ["client/missing.jsx"], "/page-3": []})
        phase = self.pages_phase()
        found = phases.problems(self.workspace, phase)
        self.assertEqual(len(found), 2)
        self.assertIn("`/page-2` is recorded, but none of the files it names exists", found[0])
        self.assertIn("`/page-3` is not recorded", found[1])

    def test_nothing_recorded_means_every_page_of_the_phase_is_missing(self):
        self.assertEqual(len(phases.problems(self.workspace, self.pages_phase())), 3)

    def test_an_empty_file_or_one_outside_the_workspace_is_not_a_page(self):
        self.write("client/empty.jsx", "")
        self.progress({"/page-1": ["client/empty.jsx"], "/page-2": ["../outside.txt", "/etc/passwd"]})
        self.assertEqual(len(phases.problems(self.workspace, self.pages_phase(2))), 2)

    def test_a_progress_file_that_is_not_what_it_should_be_records_nothing(self):
        for bad in ("not json", '["a"]', '{"routes": ["a"]}', '{"routes": {"/a": "x"}}'):
            (self.record / "build" / "progress.json").write_text(bad, encoding="utf-8")
            self.assertEqual(phases.recorded(self.workspace), {}, bad)

    def test_only_the_pages_and_the_foundation_are_checked(self):
        items = phases.plan(routes(2))
        self.assertTrue(phases.problems(self.workspace, items[0]))            # no package.json
        self.write("package.json", "{}")
        self.assertEqual(phases.problems(self.workspace, items[0]), [])
        for item in items[-3:]:
            self.assertEqual(phases.problems(self.workspace, item), [])

    def test_a_finished_pages_phase_is_told_to_the_chat_page_by_page_with_the_files_that_are_its_own(self):
        for name in ("a.jsx", "b.jsx", "c.jsx", "d.jsx", "e.jsx"):
            self.write(name)
        self.progress({"/page-1": ["a.jsx", "b.jsx", "c.jsx", "d.jsx", "gone.jsx"], "/page-2": ["e.jsx"]})
        said = phases.summary(self.workspace, self.pages_phase(3))
        self.assertEqual(said.splitlines()[0], "Built:")
        self.assertIn("- `/page-1` — a.jsx, b.jsx, c.jsx and 1 more", said)
        self.assertIn("- `/page-2` — e.jsx", said)
        self.assertNotIn("/page-3", said)                                       # not built: nothing to say about it
        self.assertEqual(phases.summary(self.workspace, phases.plan(routes(3))[0]), "")
        self.assertEqual(phases.summary(self.workspace, phases.plan(routes(3))[-1]), "")

    def test_the_pages_left_are_the_prototypes_pages_with_no_real_files(self):
        self.write("a.jsx")
        self.progress({"/page-1": ["a.jsx"]})
        self.assertEqual(phases.missing(self.workspace, routes(3)), ["/page-2", "/page-3"])


class FakeSession:
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.written: dict[tuple, object] = {}

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else fallback

    def write_record(self, *parts, data):
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path


class StateTests(Workspace):
    def setUp(self):
        super().setUp()
        self.session = FakeSession(self.workspace)
        self.items = phases.plan(routes(6))
        self.write("plan/developmentplan1.md", "the plan")
        self.finger = phases.fingerprint(routes(6), "vite-mongo", "")

    def saved(self, **more):
        state = {"fingerprint": self.finger, "plan_file": "plan/developmentplan1.md", "phases": self.items, "finished": False, **more}
        phases.save_state(self.session, state)

    def test_a_stopped_build_of_the_same_application_resumes_with_its_plan_and_the_phases_it_has_not_done(self):
        self.items[0]["status"] = "done"
        self.items[1]["status"] = "incomplete"
        self.saved()
        state = phases.resume_state(self.session, self.finger)
        self.assertEqual(state["plan_file"], "plan/developmentplan1.md")
        self.assertEqual([p["status"] for p in state["phases"][:3]], ["done", "pending", "pending"])      # unfinished is asked again

    def test_another_application_a_finished_build_or_a_plan_that_is_gone_starts_afresh(self):
        self.saved()
        self.assertIsNone(phases.resume_state(self.session, "another"))
        self.assertIsNone(phases.resume_state(FakeSession(self.workspace / "empty"), self.finger))
        (self.workspace / "plan" / "developmentplan1.md").unlink()
        self.assertIsNone(phases.resume_state(self.session, self.finger))
        self.write("plan/developmentplan1.md", "the plan")
        self.saved()
        phases.finish_state(self.session)
        self.assertIsNone(phases.resume_state(self.session, self.finger))

    def test_what_the_pages_the_stack_or_the_request_are_changes_the_fingerprint(self):
        base = phases.fingerprint(routes(3), "vite-mongo", "")
        self.assertEqual(base, phases.fingerprint(routes(3), "vite-mongo", "  "))
        self.assertNotEqual(base, phases.fingerprint(routes(4), "vite-mongo", ""))
        self.assertNotEqual(base, phases.fingerprint(routes(3), "nextjs-mongo", ""))
        self.assertNotEqual(base, phases.fingerprint(routes(3), "vite-mongo", "also add a blog"))

    def test_the_gate_refuses_a_build_with_a_page_not_built_by_name_and_a_finished_one_is_not_checked(self):
        self.prototype(routes(14))
        self.saved()
        with self.assertRaises(ValueError) as caught:
            phases.gate(self.session)
        message = str(caught.exception)
        self.assertIn("14 of the prototype's 14 pages were not built", message)
        self.assertIn("/page-1", message)
        self.assertIn("and 2 more", message)
        self.assertIn("Press Build again", message)
        self.write("x.jsx")
        self.progress({f"/page-{n}": ["x.jsx"] for n in range(1, 15)})
        phases.gate(self.session)                                             # every page has its files: it passes
        self.progress({})
        phases.finish_state(self.session)
        phases.gate(self.session)                                             # not a phased build any more: nothing to refuse

    def test_a_build_that_was_not_phased_has_no_gate(self):
        self.prototype(routes(3))
        phases.gate(self.session)


class ExecutionTests(unittest.TestCase):
    """`ProjectSession._run_phases` with a model that answers as it is told."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.asked: list[tuple[str, str, bool]] = []
        self.events: list[tuple] = []
        self.saves: list[str] = []
        self.script: list = []                  # what each turn does: a status string, an Exception, or a callable

        class Agent:
            def execute_plan(agent_self, request, plan, audit=True, parallel_write_limit=1, *, phase_task=""):
                self.asked.append((request, plan, audit))
                self.assertTrue(phase_task)
                step = self.script.pop(0) if self.script else "complete"
                if callable(step):
                    step = step()
                if isinstance(step, Exception):
                    raise step
                return SimpleNamespace(status=step, text=f"said: {request[:20]}", rounds=1)

        session = ProjectSession.__new__(ProjectSession)
        session.project = "prj_phases"
        session.role = bus.DEVELOPER
        session.stage = "build"
        session.workspace = self.workspace
        session.lock = threading.RLock()
        session._cancel = threading.Event()
        session.report_memory = lambda: None
        session.save_context = lambda: None
        session.agent = lambda model="": Agent()
        self.session = session
        for patch in (
            mock.patch.object(bus, "phase", lambda project, key, title, status="active", detail="", number=0, kind="run", agent="":
                              self.events.append(("phase", key, title, status, detail))),
            mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                              self.events.append(("msg", title, text))),
            mock.patch.object(bus, "agent_state", lambda *a, **k: None),
            mock.patch.object(bus, "log", lambda project, level, text, **k: self.events.append(("log", level, text))),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def phased(self, count=6, verify=None, summary=None):
        self.items = phases.plan(routes(count))
        return Phases(items=self.items, request_for=lambda n, p: f"ASK {n}: {p['title']}",
                      repair_for=lambda n, p, problems: f"REPAIR {n}: {'; '.join(problems)}",
                      verify=verify or (lambda p: []), save=self.saves.append, summary=summary or (lambda p: ""))

    def run_all(self, phased, plan="THE PLAN", plan_file="plan/developmentplan1.md"):
        return self.session._run_phases(self.session.agent(), plan, plan_file, phased)

    def test_remaining_pages_wait_if_the_required_first_journey_still_fails(self):
        phased = self.phased(2, verify=lambda item: ["Order did not persist"] if item["id"] == "first-journey" else [])
        phased.items = phases.plan(routes(2), {"id": "UJ-001", "name": "Place order", "routes": ["/page-1"]})
        result = self.run_all(phased)
        self.assertEqual(result["status"], "blocked")
        self.assertTrue(all("ASK 3" not in call[0] for call in self.asked))
        self.assertEqual(phased.items[2]["status"], "pending")
        phased.verify = lambda _item: []
        self.asked.clear()
        self.assertEqual(self.run_all(phased)["status"], "complete")
        self.assertFalse(any(call[0].startswith("ASK 1") for call in self.asked))

    def test_every_phase_is_given_in_order_numbered_and_each_with_its_own_request(self):
        phased = self.phased(6)
        result = self.run_all(phased)
        self.assertEqual(result["status"], "complete")
        total = len(self.items)
        self.assertEqual(len(self.asked), total)
        self.assertEqual([a[0] for a in self.asked], [f"ASK {n}: {p['title']}" for n, p in enumerate(self.items, 1)])
        self.assertTrue(all(p["status"] == "done" for p in self.items))
        self.assertTrue(all(audit is False for _, _, audit in self.asked))
        self.assertEqual(result["rounds"], total)

    def test_each_phase_receives_only_its_plan_section(self):
        phased = self.phased(2)
        phased.notes_for = phases.section
        self.run_all(phased, plan="## Phase 1\nOnly foundation\n\n## Phase 2\nOnly pages")
        self.assertEqual(self.asked[0][1], "## Phase 1\nOnly foundation")
        self.assertEqual(self.asked[1][1], "## Phase 2\nOnly pages")
        self.assertEqual(self.asked[2][1], "")

    def test_the_chat_gets_words_for_each_phase_not_only_files(self):
        self.run_all(self.phased(5))
        messages = [e for e in self.events if e[0] == "msg"]
        self.assertEqual(len(messages), len(self.items))
        self.assertEqual(messages[0][1], f"Phase 1 of {len(self.items)}")
        self.assertIn("Building what every page stands on", messages[0][2])
        stages = [e for e in self.events if e[0] == "phase"]
        self.assertEqual(stages[0][1:4], ("build:phase-1", f"Phase 1 of {len(self.items)} · {self.items[0]['title']}", "active"))
        self.assertEqual(stages[1][3], "complete")

    def test_what_a_finished_phase_delivered_is_told_in_words_but_not_for_one_that_is_not_finished(self):
        phased = self.phased(5, verify=lambda p: ["`/page-1` is not recorded"] if p["id"] == "pages-2" else [],
                             summary=lambda p: f"Built the {p['id']}" if p["kind"] == "pages" else "")
        self.run_all(phased)
        done = [e for e in self.events if e[0] == "msg" and e[1].endswith(" done")]
        self.assertEqual([e[2] for e in done], ["Built the pages-1"])
        self.assertEqual(done[0][1], f"Phase 2 of {len(self.items)} done")

    def test_a_phase_that_is_not_finished_is_asked_for_again_until_it_is(self):
        state = {"calls": 0}

        def verify(phase):
            if phase["kind"] != "pages" or phase["id"] != "pages-1":
                return []
            state["calls"] += 1
            return ["`/page-1` is not recorded"] if state["calls"] < 3 else []

        result = self.run_all(self.phased(4, verify))
        repairs = [a[0] for a in self.asked if a[0].startswith("REPAIR")]
        self.assertEqual(repairs, ["REPAIR 2: `/page-1` is not recorded"] * 2)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(self.items[1]["status"], "done")
        told = [e[2] for e in self.events if e[0] == "msg" and "is not finished yet" in e[2]]
        self.assertEqual(len(told), 2)
        self.assertIn("Finishing it (1 of 2)", told[0])

    def test_a_phase_that_stays_unfinished_is_recorded_as_such_and_the_build_goes_on_to_the_tests_and_the_checks(self):
        result = self.run_all(self.phased(4, lambda p: ["`/page-1` is not recorded"] if p["id"] == "pages-1" else []))
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(self.items[1]["status"], "incomplete")
        self.assertEqual(self.items[1]["problems"], ["`/page-1` is not recorded"])
        self.assertEqual([p["status"] for p in self.items if p["id"] != "pages-1"], ["done"] * (len(self.items) - 1))
        repairs = [a for a in self.asked if a[0].startswith("REPAIR")]
        self.assertEqual(len(repairs), PHASE_REPAIRS)                         # asked again, and not for ever
        failed = [e for e in self.events if e[0] == "phase" and e[3] == "failed"]
        self.assertEqual(len(failed), 1)
        self.assertIn("is not recorded", failed[0][4])

    def test_a_phase_the_model_calls_blocked_is_noted_and_the_rest_still_run(self):
        self.script = ["complete", "blocked"]
        result = self.run_all(self.phased(2))
        self.assertEqual(result["status"], "complete")                        # nothing it delivers is missing
        self.assertIn("said:", self.items[1]["note"])
        self.assertTrue(any(e[0] == "log" and e[1] == "WARN" and "ended blocked" in e[2] for e in self.events))
        self.assertEqual(len(self.asked), len(self.items))

    def test_the_state_is_saved_after_every_phase_and_the_phases_done_are_skipped_on_resume(self):
        phased = self.phased(3)
        self.run_all(phased)
        self.assertEqual(len(self.saves), len(self.items))
        self.asked.clear()
        self.items[3]["status"] = "pending"                                   # the way a stopped build looks
        self.items[4]["status"] = "pending"
        self.run_all(phased)
        self.assertEqual([a[0].split(":")[0] for a in self.asked], ["ASK 4", "ASK 5"])

    def test_stop_ends_the_build_between_phases_and_what_was_done_stays_done(self):
        phased = self.phased(4)
        self.script = ["complete", lambda: self.session._cancel.set() or "complete"]
        with self.assertRaises(RunCancelled):
            self.run_all(phased)
        self.assertEqual([p["status"] for p in self.items[:3]], ["done", "done", "pending"])
        self.assertEqual(len(self.asked), 2)

    def test_with_a_brief_every_phase_after_the_first_starts_a_fresh_conversation_that_begins_with_it(self):
        shed = []
        self.session.shed_history = lambda note="", keep_tokens=40_000: shed.append(keep_tokens) or 0
        phased = self.phased(4)
        phased.brief = "THE BUILD REQUEST"
        self.run_all(phased)
        total = len(self.items)
        self.assertEqual(shed, [0] * (total - 1))                              # the first phase follows its own plan
        self.assertEqual(self.asked[0][0], f"ASK 1: {self.items[0]['title']}")
        for request, _, _ in self.asked[1:]:
            self.assertTrue(request.startswith("THE BUILD REQUEST\n\n---\n\nASK "), request[:60])
        # A resumed build starts its first phase fresh too.
        shed.clear(), self.asked.clear()
        self.items[3]["status"] = "pending"
        self.session._run_phases(self.session.agent(), "THE PLAN", "plan/developmentplan1.md", phased, fresh_first=True)
        self.assertEqual((shed, self.asked[0][0][:17]), ([0], "THE BUILD REQUEST"))

    def test_pages_phases_are_built_at_the_same_time_and_each_is_still_checked_and_repaired(self):
        shed, lanes = [], []
        self.session.shed_history = lambda note="", keep_tokens=40_000: shed.append(keep_tokens) or 0

        def run_lanes(work, parallel_write_limit=1):
            lanes.append([request for request, _, _ in work])
            self.assertTrue(all("## Built at the same time as other phases" in task for _, _, task in work))
            return [{"status": "complete", "text": "built", "rounds": 1} for _ in work]

        self.session.run_lanes = run_lanes
        verified = {"pages-2": 0}

        def verify(phase):
            if phase["id"] == "pages-2" and verified["pages-2"] == 0:
                verified["pages-2"] += 1
                return ["`/page-5` is not recorded"]
            return []

        phased = self.phased(10, verify=verify)
        phased.brief = "THE BUILD REQUEST"
        phased.together = phases.together
        result = self.run_all(phased)
        kinds = [p["kind"] for p in self.items]
        pages = kinds.count("pages")
        self.assertEqual(len(lanes), 2)                                         # the pages, then the unit and journey tests
        self.assertEqual(len(lanes[0]), pages)
        self.assertEqual(len(lanes[1]), 2)
        self.assertTrue(all(r.startswith("THE BUILD REQUEST") and "## Built at the same time as other phases" in r
                            for r in lanes[0]))
        alone = [a[0] for a in self.asked]
        self.assertEqual(len([a for a in alone if "ASK " in a]), len(self.items) - pages - 2)   # the foundation and the wiring
        repairs = [a for a in alone if "REPAIR" in a]
        self.assertEqual(len(repairs), 1)
        self.assertTrue(repairs[0].startswith("THE BUILD REQUEST"))               # a repair of a phase built apart has the brief
        self.assertEqual(result["status"], "complete")

    def test_without_a_brief_the_phases_share_one_conversation_as_before(self):
        self.session.shed_history = lambda *a, **k: self.fail("nothing is shed without a brief")
        self.run_all(self.phased(2))
        self.assertTrue(all(request.startswith("ASK ") for request, _, _ in self.asked))

    def test_a_turn_that_fails_stops_the_build_with_its_error_and_the_phases_before_it_are_kept(self):
        phased = self.phased(2)
        self.script = ["complete", RuntimeError("the model service is down")]
        with self.assertRaisesRegex(RuntimeError, "model service is down"):
            self.run_all(phased)
        self.assertEqual(self.items[0]["status"], "done")
        self.assertEqual(self.items[1]["status"], "pending")


class RunTaskTests(unittest.TestCase):
    def test_run_task_plans_once_saves_the_plan_and_then_carries_it_out_phase_by_phase(self):
        with tempfile.TemporaryDirectory() as folder:
            session = ProjectSession.__new__(ProjectSession)
            session.project, session.role, session.stage = "prj_rt", bus.DEVELOPER, "build"
            session.workspace = Path(folder)
            session.lock = threading.RLock()
            session._cancel = threading.Event()
            session.report_memory = lambda: None
            session.save_context = lambda: None
            modes, turns = [], []

            class Agent:
                def set_mode(agent_self, mode):
                    modes.append(mode)

                def ask(agent_self, request):
                    return "1. everything"

                def execute_plan(agent_self, request, plan, audit=True, parallel_write_limit=1, *, phase_task=""):
                    turns.append((request, plan))
                    return SimpleNamespace(status="complete", text="ok", rounds=1)

            session.agent = lambda model="": Agent()
            saves = []
            items = phases.plan(routes(2))
            phased = Phases(items=items, request_for=lambda n, p: f"ASK {n}", repair_for=lambda *a: "", save=saves.append)
            with mock.patch.object(bus, "phase"), mock.patch.object(bus, "agent_msg"), mock.patch.object(bus, "agent_state"), \
                    mock.patch.object(bus, "log"):
                result = session.run_task("the request", plan_directory="plan", phases=phased)
                self.assertEqual(modes, ["plan"])                              # planned once
                self.assertEqual(saves[0], "plan/developmentplan1.md")        # and the plan is on disk before the first phase
                self.assertEqual(len(turns), len(items))
                self.assertEqual(result["plan_file"], "plan/developmentplan1.md")
                self.assertEqual((result["status"], result["plan"]), ("complete", "1. everything"))
                # A stopped build carries on with that plan, planning nothing.
                for item in items[2:]:
                    item["status"] = "pending"
                turns.clear()
                resumed = session.resume_phases("1. everything", "plan/developmentplan1.md", phased)
                self.assertEqual(modes, ["plan"])
                self.assertEqual(len(turns), len(items) - 2)
                self.assertEqual(resumed["plan_file"], "plan/developmentplan1.md")

    def test_the_bounded_planner_saves_the_route_plan_instead_of_the_tool_limit_message(self):
        with tempfile.TemporaryDirectory() as folder:
            session = ProjectSession.__new__(ProjectSession)
            session.project, session.role, session.stage = "prj_rt", bus.DEVELOPER, "build"
            session.workspace = Path(folder)
            session.lock = threading.RLock()
            session._cancel = threading.Event()
            session.report_memory = session.save_context = lambda: None
            session.shed_history = mock.Mock()
            agent = mock.Mock(tool_limit_reached=True)
            agent.ask.return_value = "Tool batch reached the limit"
            agent.execute_plan.return_value = SimpleNamespace(status="complete", text="ok", rounds=1)
            session.agent = lambda model="": agent
            items = phases.plan(routes(2))
            fallback = phases.fallback_plan(items, routes(2))
            phased = Phases(items=items, request_for=lambda n, p: f"ASK {n}", repair_for=lambda *a: "",
                            brief="Shared references", planning_prompt="Prepared SRS brief",
                            fallback_plan=fallback, notes_for=phases.section)
            with mock.patch.object(bus, "phase"), mock.patch.object(bus, "agent_msg"), \
                    mock.patch.object(bus, "agent_state"), mock.patch.object(bus, "log"):
                result = session.run_task("Old broad request", plan_directory="plan", phases=phased)
            agent.ask.assert_called_once_with("Prepared SRS brief", max_steps=PHASE_PLANNING_STEPS)
            self.assertEqual((session.workspace / result["plan_file"]).read_text(encoding="utf-8"), fallback)
            first = agent.execute_plan.call_args_list[0]
            self.assertEqual(first.args[0], "Shared references\n\n---\n\nASK 1")
            self.assertEqual(first.kwargs["phase_task"], "ASK 1")
            self.assertNotIn("## Phase 2", first.args[1])


class BuildWiringTests(Workspace):
    def session(self):
        session = FakeSession(self.workspace)
        session.calls = []

        def run_task(request, **options):
            session.calls.append(("run_task", request, options))
            return {"status": "complete", "plan": "p", "plan_file": "plan/developmentplan1.md", "text": "ok", "phases": []}

        def resume_phases(plan, plan_file, phased, model=""):
            session.calls.append(("resume", plan, plan_file, phased))
            return {"status": "complete", "plan": plan, "plan_file": plan_file, "text": "ok"}

        session.run_task, session.resume_phases = run_task, resume_phases
        return session

    def test_a_prototype_with_pages_is_built_phase_by_phase_with_the_whole_plan_made_once(self):
        self.prototype(routes(10))
        session = self.session()
        build._build_in_phases("p", session, "vite-mongo", REQUEST, "")
        kind, request, options = session.calls[0]
        self.assertEqual((kind, request, options["plan_directory"], options["audit"]), ("run_task", REQUEST, "plan", False))
        phased = options["phases"]
        self.assertEqual(len(phased.items), 1 + 3 + 3)                          # foundation, three page phases, wiring, tests, checks
        self.assertIn("# Phase 2 of 7", phased.request_for(2, phased.items[1]))
        self.assertIn("Never cut the application down", phased.request_for(2, phased.items[1]))
        self.assertTrue(phased.verify(phased.items[1]))                          # nothing is recorded yet
        phased.save("plan/developmentplan1.md")
        state = session.read_record("build", "phases.json")
        self.assertEqual((state["plan_file"], state["finished"], len(state["phases"])), ("plan/developmentplan1.md", False, 7))

    def test_a_stopped_build_resumes_from_its_saved_plan_and_does_not_plan_again(self):
        self.prototype(routes(5))
        self.write("plan/developmentplan1.md", "THE SAVED PLAN")
        session = self.session()
        items = phases.plan(routes(5))
        items[0]["status"] = "done"
        phases.save_state(session, {"fingerprint": phases.fingerprint(routes(5), "vite-mongo", "x"),
                                    "plan_file": "plan/developmentplan1.md", "phases": items, "finished": False})
        build._build_in_phases("p", session, "vite-mongo", REQUEST, "x")
        self.assertEqual([c[0] for c in session.calls], ["resume"])
        self.assertEqual((session.calls[0][1], session.calls[0][2]), ("THE SAVED PLAN", "plan/developmentplan1.md"))
        self.assertEqual(session.calls[0][3].items[0]["status"], "done")

    def test_a_different_request_plans_afresh(self):
        self.prototype(routes(5))
        self.write("plan/developmentplan1.md", "OLD")
        session = self.session()
        phases.save_state(session, {"fingerprint": phases.fingerprint(routes(5), "vite-mongo", "old direction"),
                                    "plan_file": "plan/developmentplan1.md", "phases": phases.plan(routes(5)), "finished": False})
        build._build_in_phases("p", session, "vite-mongo", REQUEST, "new direction")
        self.assertEqual([c[0] for c in session.calls], ["run_task"])

    def test_a_prototype_that_lists_no_pages_is_built_the_way_it_always_was(self):
        session = self.session()
        build._build_in_phases("p", session, "vite-mongo", REQUEST, "")
        self.assertEqual(session.calls[0][2], {"plan_directory": "plan", "audit": False})

    def test_the_build_ends_only_through_the_gate_and_the_next_build_starts_afresh(self):
        source = (ROOT / "builder-agent" / "builder_agent" / "build.py").read_text(encoding="utf-8")
        finish = source[source.index("def _finish_run("):source.index("def _check_decision")]
        self.assertLess(finish.index("build_phases.gate(session)"), finish.index("_conform_reports(project, session, plan)"))
        self.assertIn("build_phases.finish_state(session)", finish)
        self.assertLess(finish.index("store.advance(project, \"test\")"), finish.index("build_phases.finish_state(session)"))

    def test_the_build_request_tells_the_model_the_work_comes_in_phases_and_is_never_cut_down(self):
        text = (ROOT / "prompts" / "builder" / "generate.md").read_text(encoding="utf-8")
        self.assertIn("## How the work is given to you", text)
        self.assertIn("never cut down to fit", text.lower().replace("is never cut down", "never cut down"))
        self.assertIn("the Studio refuses a build in which one is not", text)
        for number in (1, 2, 3):
            self.assertTrue(phases.section(text, number), number)


if __name__ == "__main__":
    unittest.main()
