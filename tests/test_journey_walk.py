"""The prototype's journeys, clicked through in a browser with a picture at every step, then looked at (and fixed).

The prototype is one React app that routes by hash, so a page is a route (`/phones`) and the browser is on a page when the
app's hash says so."""
from __future__ import annotations

import copy
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import screenshot  # noqa: E402
from prototype_agent import journey_walk as jw  # noqa: E402
from prototype_agent.journey_driver import Driver, DriverError  # noqa: E402
from server_modules import bus, config, live, prompts, web_app  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402

ROWS = [{"route": "/", "file": "app/src/App.tsx", "name": "Home"},
        {"route": "/phones", "file": "app/src/App.tsx", "name": "Phone Catalogue"},
        {"route": "/phones/:id", "file": "app/src/App.tsx", "name": "Phone Detail"},
        {"route": "/cart", "file": "app/src/App.tsx", "name": "Cart"},
        {"route": "/wishlist", "file": "app/src/App.tsx", "name": "Wishlist"}]


class DriverStopTests(unittest.TestCase):
    def test_a_waiting_browser_call_stops_without_waiting_for_its_command_timeout(self):
        stop = threading.Event()
        driver = Driver(cancelled=stop.is_set)
        process = mock.Mock(pid=1234)
        process.poll.return_value = None
        driver._process = process
        threading.Timer(0.15, stop.set).start()
        started = time.monotonic()
        with mock.patch.object(driver, "close") as close, self.assertRaises(RunCancelled):
            driver.call("state", seconds=30)
        self.assertLess(time.monotonic() - started, 1.5)
        close.assert_called_once_with(fast=True)


def step(sid, text, route):
    return {"id": sid, "step": text, "route": route}


# --- a prototype that is a table, and a browser that is a pointer into it ---------------------------------------------

class FakeBrowser:
    """What `Driver` is to the real prototype, over a tiny made-up one: pages (routes) with the things on them, and what clicking each does."""

    def __init__(self, pages: dict[str, dict], start: str = "/"):
        self.pages, self.route, self.filled, self.calls = pages, start, {}, []
        self.menus_open = set()
        self.closed = False
        self.error_text: list[str] = []

    def start(self):
        return self

    def close(self):
        self.closed = True

    def reset(self):
        self.route, self.filled = "about:blank", {}          # a new profile opens on a blank tab
        self.menus_open = set()
        self.dialog = False

    def goto(self, bundle, route="/"):
        self.route = route
        self.calls.append(("goto", self.route))
        return self.state()

    def state(self):
        page = self.pages.get(self.route, {})
        return {"url": "file:///bundle.html#" + self.route, "title": page.get("title", self.route), "route": self.route,
                "heading": page.get("heading", "")}

    def text(self):
        return self.pages.get(self.route, {}).get("text", "")

    dialog = False

    def key(self, name):
        self.calls.append(("key", name))
        if name == "Escape":
            self.dialog = False
        return {"state": self.state()}

    def elements(self):
        found = []
        page = self.pages.get(self.route, {})
        shown = list(page.get("elements", [])) + ([{**e, "area": "dialog"} for e in page.get("dialog", [])] if self.dialog else [])
        for i, base in enumerate(shown):
            element = {"i": i, "menu": -1, "tag": "a", "type": "", "text": "", "label": "", "href": "", "route": "", "external": False,
                       "name": "", "placeholder": "", "area": "main", "disabled": False, "checked": False,
                       "value": "", "signOut": False, **base}
            if "opener" in base:                    # inside a menu: only usable once the menu button has been pressed
                element["menu"] = -1 if self.route in self.menus_open else base["opener"]
            found.append(element)
        return found

    menus_open: set

    def click(self, i):
        element = self.elements()[i]
        self.calls.append(("click", element["text"] or element["route"]))
        if self.dialog and element["area"] != "dialog":
            raise DriverError("something else covers it (dialog)")
        if element.get("opens_dialog"):
            self.dialog = True
            return {"state": self.state(), "navigated": False}
        if element.get("closes_dialog"):
            self.dialog = False
            return {"state": self.state(), "navigated": False}
        if element["tag"] == "summary":
            self.menus_open.add(self.route)
            return {"state": self.state(), "navigated": False}
        if element["menu"] >= 0:                    # a link in a menu that is shut: the click lands on nothing
            return {"state": self.state(), "navigated": False}
        if element.get("reveals") is not None:      # what the page shows after this (a filter cleared, say)
            self.pages[self.route] = {**self.pages[self.route], "elements": element["reveals"]}
        goes = element.get("goes") or (element["route"] if element["tag"] == "a" else "")
        before = self.route
        if goes:
            self.route = goes
        return {"state": self.state(), "navigated": self.route != before}

    def fill(self, i, value):
        element = self.elements()[i]
        self.calls.append(("fill", element["placeholder"] or element["label"], value))
        self.filled[i] = value
        return {"state": self.state()}

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"\xff\xd8shot-" + self.route.encode())
        return Path(path)

    def errors(self):
        found, self.error_text = self.error_text, []
        return found


def link(text, route, area="nav"):
    return {"tag": "a", "text": text, "route": route, "area": area}


SHOP = {
    "/": {"title": "Home", "heading": "Find your phone", "elements": [link("Phone Catalogue", "/phones"), link("Cart", "/cart"),
                                                                    link("Wishlist", "/wishlist")]},
    "/phones": {"title": "Phone Catalogue", "heading": "Phones", "text": "Phones\nPrices from Rs 30,000 to Rs 289,000", "elements": [
        link("Home", "/"), {"tag": "input", "type": "search", "placeholder": "Search model", "area": "main"},
        link("Apple iPhone 15", "/phones/12", "main")]},
    "/phones/12": {"title": "Phone Detail", "heading": "Apple iPhone 15", "elements": [
        link("Home", "/"), {"tag": "button", "text": "Add to cart", "goes": "/cart", "area": "main"}]},
    "/cart": {"title": "Cart", "heading": "Your cart", "elements": [link("Home", "/")]},
    "/wishlist": {"title": "Wishlist", "heading": "Wishlist", "elements": [link("Phone Catalogue", "/phones"), link("Cart", "/cart")]},
}


def judged(ids, ok=True, completes=True, defects=None):
    return {"journey": {"completes": completes, "summary": "A person can get through this."},
            "steps": [{"id": sid, "ok": ok, "summary": f"{sid} is shown.", "defects": (defects or {}).get(sid, [])} for sid in ids]}


def copy_of(pages):
    return copy.deepcopy(pages)


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.record = self.workspace / ".agentforge"
        self.root = self.record / "prototype"
        (self.root / "app" / "src").mkdir(parents=True)
        (self.root / "app" / "index.html").write_text("<div id=root></div>", encoding="utf-8")
        (self.root / "app" / "src" / "App.tsx").write_text("export default () => null", encoding="utf-8")
        (self.record / "srs").mkdir()
        self.messages: list[dict] = []
        self.sent: list[dict] = []
        self.progress: list[float] = []
        self.phases: list[tuple] = []
        self.rebuilt = 0

        def built(session, project, kind, agent=""):
            self.rebuilt += 1

        for patch in (
            mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                              self.messages.append({"text": text, "title": title, "kind": kind, "images": images or []})),
            mock.patch.object(bus, "phase", lambda project, key, title, status="active", detail="", number=0, kind="run", agent="":
                              self.phases.append((key, status))),
            mock.patch.object(bus, "progress", lambda project, label, pct, agent="": self.progress.append(pct)),
            mock.patch.object(bus, "log", lambda *a, **k: None),
            mock.patch.object(bus, "prototype_changed", lambda *a, **k: None),
            mock.patch.object(bus, "viewers", lambda: 0),
            mock.patch.object(live, "handle", lambda project, body: self.sent.append(body)),
            mock.patch.object(live, "finish", lambda project: self.sent.append({"kind": "end"})),
            mock.patch.object(web_app, "stage_skill", return_value=".agentforge/skills/web-artifacts-builder"),
            mock.patch.object(web_app, "ensure_built", side_effect=built),
            mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")),
            mock.patch("server_modules.vision.supports", return_value=True),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def journeys_file(self, journeys):
        (self.record / "srs" / "user-journeys.json").write_text(json.dumps({"schema": "x", "journeys": journeys}), encoding="utf-8")

    def session(self, fix=None, model="vision-model"):
        done = SimpleNamespace(record=self.record, workspace=self.workspace, cancelled=False, model=model, requests=[])
        done.agent = lambda m="": SimpleNamespace(model=m or model)

        def run_direct(request, model=""):
            done.requests.append(request)
            if fix:
                fix(self.root)
            return {"status": "complete", "text": "Fixed.", "rounds": 1}

        done.run_direct = run_direct
        return done

    def walk_with(self, pages=None, rows=None):
        return jw.Walk("p", "vision-model", self.root, rows or ROWS, FakeBrowser(copy.deepcopy(pages or SHOP)),
                       streaming=False, cancelled=lambda: False)


def change_the_app(root: Path, text: str = "changed") -> None:
    (root / "app" / "src" / "App.tsx").write_text(f"export default () => <h1>{text}</h1>", encoding="utf-8")


# --- what is read from the specification and the prototype ------------------------------------------------------------

class ReadingTests(Harness):
    def test_the_journeys_are_read_with_their_steps_and_a_step_past_the_bound_is_left_out(self):
        self.journeys_file([{"id": "UJ-001", "workflow_name": "Finding", "who": "Visitor",
                             "steps": [{"id": f"UJ-001-S{n:02d}", "step": f"step {n}", "route": "/"} for n in range(1, 15)]},
                            {"id": "UJ-002", "workflow_name": "No steps", "who": "Visitor", "steps": []}, "junk"])
        found = jw.load_journeys(self.record)
        self.assertEqual([j["id"] for j in found], ["UJ-001"])
        self.assertEqual(len(found[0]["steps"]), jw.MAX_STEPS)
        self.assertEqual(found[0]["steps"][0], {"id": "UJ-001-S01", "step": "step 1", "route": "/"})

    def test_no_journeys_file_is_no_journeys(self):
        self.assertEqual(jw.load_journeys(self.record), [])

    def test_a_route_is_its_prototype_page_and_an_unknown_one_is_none(self):
        self.assertEqual(jw.page_for("/phones/:id", ROWS), "/phones/:id")
        self.assertEqual(jw.page_for("/phones/[id]", ROWS), "/phones/:id")      # the same page, its parameter spelled another way
        self.assertEqual(jw.page_for("/phones/", ROWS), "/phones")
        self.assertEqual(jw.page_for("/nowhere", ROWS), "")

    def test_the_app_is_on_a_page_when_its_route_says_so_with_a_value_for_every_parameter(self):
        self.assertTrue(jw.at_page("/phones/12", "/phones/:id"))
        self.assertTrue(jw.at_page("/phones", "/phones"))
        self.assertTrue(jw.at_page("/", "/"))
        self.assertFalse(jw.at_page("/phones", "/phones/:id"))
        self.assertFalse(jw.at_page("/cart", "/phones"))
        self.assertFalse(jw.at_page("/phones", ""))

    def test_what_can_be_used_is_listed_without_signing_out_or_other_websites(self):
        elements = [{"i": 0, "tag": "a", "text": "Log out", "signOut": True}, {"i": 1, "tag": "a", "text": "Docs", "external": True},
                    {"i": 2, "tag": "button", "text": "Save", "signOut": False}]
        self.assertEqual([e["i"] for e in jw.describe(elements)], [2])
        self.assertEqual([e["i"] for e in jw.describe(elements, allow_sign_out=True)], [0, 2])

    def test_a_plan_is_checked_against_what_is_really_on_the_screen(self):
        elements = [{"i": 0, "tag": "input", "type": "text"}, {"i": 1, "tag": "button", "disabled": False},
                    {"i": 2, "tag": "button", "disabled": True}]
        plan = jw.check_plan({"actions": [{"do": "fill", "element": 0, "value": "Ada"}, {"do": "click", "element": 1}]}, elements)
        self.assertEqual(plan, [{"do": "fill", "element": 0, "value": "Ada"}, {"do": "click", "element": 1}])
        for bad in ({"actions": [{"do": "click", "element": 9}]}, {"actions": [{"do": "fill", "element": 1, "value": "x"}]},
                    {"actions": [{"do": "click", "element": 2}]}, {"nothing": 1}, "text"):
            with self.assertRaises(ValueError):
                jw.check_plan(bad, elements)
        self.assertEqual(jw.check_plan({"actions": []}, elements), [])
        many = {"actions": [{"do": "click", "element": 1}] * 20}
        self.assertEqual(len(jw.check_plan(many, elements)), jw.MAX_ACTIONS)


class TimeLimitTests(Harness):
    """A model call that has stopped answering must not stop the whole walk."""

    def test_an_answer_that_comes_in_time_is_returned_and_an_error_is_raised_as_it_is(self):
        self.assertEqual(jw._within(5, lambda a, b: a + b, 1, 2), 3)
        with self.assertRaisesRegex(ValueError, "no JSON"):
            jw._within(5, mock.Mock(side_effect=ValueError("no JSON")))

    def test_a_call_that_never_answers_is_given_up_on_after_its_time(self):
        release = threading.Event()
        self.addCleanup(release.set)
        with self.assertRaisesRegex(TimeoutError, "did not answer within"):
            jw._within(0.2, lambda: release.wait(30))

    def test_the_call_runs_with_the_stop_of_the_run_it_belongs_to(self):
        from server_modules import llm
        stop = threading.Event()
        llm.bind_stop(stop)
        self.addCleanup(llm.bind_stop, None)
        self.assertFalse(jw._within(5, llm._stopped))                # noqa: SLF001
        stop.set()
        self.assertTrue(jw._within(5, llm._stopped))                 # noqa: SLF001 - the run's Stop reaches the call

    def test_a_call_given_up_on_is_stopped_too_so_it_does_not_go_on_asking_the_model_service(self):
        from server_modules import llm
        seen = {}
        started, finished = threading.Event(), threading.Event()

        def call():
            started.set()
            seen["stopped"] = llm._wait_for_stop(30)                 # noqa: SLF001 - what a pause between attempts waits on
            finished.set()

        with self.assertRaisesRegex(TimeoutError, "did not answer within"):
            jw._within(0.2, call)
        self.assertTrue(finished.wait(5), "the abandoned call kept waiting")
        self.assertTrue(seen["stopped"])

    def test_a_step_the_model_does_not_answer_in_time_is_shown_as_it_is_and_the_walk_goes_on(self):
        release = threading.Event()
        self.addCleanup(release.set)
        walk = self.walk_with()
        journey = {"id": "UJ-001", "name": "Finding", "who": "Visitor",
                   "steps": [step("UJ-001-S01", "Visitor types a model into search", "/phones"),
                             step("UJ-001-S02", "Visitor opens Home", "/")]}
        with mock.patch.object(jw, "PLAN_SECONDS", 0.2), \
                mock.patch("server_modules.llm.complete_json", side_effect=lambda *a, **k: release.wait(30)):
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        first, second = walked["steps"]
        self.assertTrue(first["reached"])
        self.assertIn("did not answer within", first["notes"][0])
        self.assertTrue(second["reached"])

    def test_pictures_the_model_does_not_answer_about_in_time_leave_the_journey_walked_and_reported(self):
        release = threading.Event()
        self.addCleanup(release.set)
        self.journeys_file([{"id": "UJ-001", "workflow_name": "Finding", "who": "Visitor",
                             "steps": [step("UJ-001-S01", "Visitor opens Home", "/")]}])
        calls = []

        def complete_json(system, user, validator=None, label="", **_):
            calls.append(label)
            return release.wait(30)

        with mock.patch.object(jw, "JUDGE_SECONDS", 0.2), mock.patch("server_modules.llm.complete_json", side_effect=complete_json), \
                mock.patch.object(jw, "Driver", lambda *a, **k: FakeBrowser(copy_of(SHOP))):
            result = jw.run("p", self.session(), ROWS, fix=False)
        report = json.loads((self.root / "journeys" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "done")
        self.assertIn("did not answer within", report["results"][0]["judge_error"])
        self.assertEqual(report["results"][0]["steps"][0]["reached"], True)

    def test_the_stop_of_the_run_reaches_the_model_calls_made_on_the_lanes(self):
        from server_modules import llm
        stop = threading.Event()
        llm.bind_stop(stop)
        self.addCleanup(llm.bind_stop, None)
        self.journeys_file([{"id": "UJ-001", "workflow_name": "Finding", "who": "Visitor",
                             "steps": [step("UJ-001-S01", "Visitor types a model into search", "/phones")]}])
        seen = []

        def complete_json(system, user, validator=None, label="", **_):
            seen.append((label, llm._stop_event()))                    # noqa: SLF001
            return validator({"actions": []} if label == "journey step" else judged(["UJ-001-S01"]))

        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json), \
                mock.patch.object(jw, "Driver", lambda *a, **k: FakeBrowser(copy_of(SHOP))):
            jw.run("p", self.session(), ROWS, fix=False)
        self.assertEqual({label for label, _ in seen}, {"journey step", "journey review"})
        self.assertTrue(all(event is not None and not event.is_set() for _, event in seen), seen)
        stop.set()                                                     # the run's Stop is what each call's own stop follows
        self.assertTrue(all(event.is_set() for _, event in seen), seen)


# --- clicking through one journey -------------------------------------------------------------------------------------

class WalkTests(Harness):
    def planner(self, *plans):
        """The model's answers to "what do you press on this screen", one per call; once they run out, nothing to do."""
        answers = list(plans)

        def complete_json(system, user, validator=None, label="", **_):
            self.assertEqual(label, "journey step")
            return validator({"actions": answers.pop(0) if answers else []})
        return mock.patch("server_modules.llm.complete_json", side_effect=complete_json)

    def journey(self, who, *steps):
        return {"id": "UJ-001", "name": "Finding the right phone", "who": who, "steps": list(steps)}

    def test_every_step_is_reached_by_clicking_the_links_the_pages_have_and_a_picture_is_taken_of_each(self):
        walk = self.walk_with()
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens Home", "/"),
                               step("UJ-001-S02", "Visitor opens the Phone Catalogue", "/phones"),
                               step("UJ-001-S03", "Visitor reads a Phone Detail page", "/phones/:id"))
        with self.planner():
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertEqual([s["reached"] for s in walked["steps"]], [True, True, True])
        self.assertEqual(walked["steps"][2]["visited"], ["/phones", "/phones/12"])
        self.assertEqual([c for c in walk.driver.calls if c[0] == "click"], [("click", "Phone Catalogue"), ("click", "Apple iPhone 15")])
        self.assertEqual(walked["steps"][1]["actions"], ['clicked "Phone Catalogue"'])
        for s in walked["steps"]:
            self.assertTrue((self.root / "journeys" / "UJ-001" / s["shots"][-1]).is_file())

    def test_a_journey_starts_at_the_home_page_and_not_on_a_blank_tab_whoever_walks_it(self):
        walk = self.walk_with()
        journey = self.journey("Customer", step("UJ-001-S01", "Customer opens the Phone Catalogue", "/phones"))
        with self.planner():
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertEqual(walk.driver.calls[0], ("goto", "/"))
        self.assertTrue(walked["steps"][0]["reached"])
        self.assertEqual(walked["steps"][0]["visited"], ["/", "/phones"])
        self.assertIsNone(walked["setup"])
        self.assertNotIn("account", walked)                       # there is no sign-in to make

    def test_a_page_with_no_link_to_the_next_screen_is_a_step_that_could_not_be_done_and_the_walk_goes_on(self):
        pages = {**SHOP, "/": {"title": "Home", "elements": [link("Wishlist", "/wishlist")]}}
        walk = self.walk_with(pages)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Cart", "/cart"),
                               step("UJ-001-S02", "Visitor opens Home", "/"))
        with self.planner():
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        first, second = walked["steps"]
        self.assertFalse(first["reached"])
        self.assertIn("no link on / leads towards /cart", first["notes"][0])
        self.assertTrue((self.root / "journeys" / "UJ-001" / first["shots"][-1]).is_file())      # a picture even of that
        self.assertTrue(second["reached"])

    def test_a_link_inside_a_menu_that_is_shut_is_reached_by_opening_the_menu_first_like_a_person_does(self):
        # "Your account" holds My Orders: it is there, but a click on it lands on nothing until the menu is open.
        menu = [{"tag": "summary", "text": "Your account", "area": "nav"},
                {"tag": "a", "text": "My Orders", "route": "/account/orders", "area": "nav", "opener": 0}]
        pages = {**SHOP, "/": {"title": "Home", "elements": menu}, "/account/orders": {"title": "My Orders", "elements": []}}
        rows = ROWS + [{"route": "/account/orders", "file": "app/src/App.tsx", "name": "My Orders"}]
        walk = self.walk_with(pages, rows)
        with self.planner():
            walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor opens My Orders", "/account/orders")),
                               self.root / "journeys" / "UJ-001")
        done = walked["steps"][0]
        self.assertTrue(done["reached"], done["notes"])
        self.assertEqual(done["actions"], ['opened "Your account"', 'clicked "My Orders"'])

    def test_a_link_that_shows_before_one_in_a_menu_is_the_one_used(self):
        elements = [{"i": 0, "tag": "a", "text": "Cart", "route": "/cart", "area": "nav", "menu": 3},
                    {"i": 1, "tag": "a", "text": "Cart", "route": "/cart", "area": "footer", "menu": -1}]
        self.assertEqual(jw.Walk._best_link(elements, "/cart", {"step": "opens the cart"})["i"], 1)

    def test_a_link_to_a_page_with_a_parameter_is_found_by_the_value_it_has(self):
        elements = [{"i": 0, "tag": "a", "text": "Apple iPhone 15", "route": "/phones/12", "area": "main", "menu": -1}]
        self.assertEqual(jw.Walk._best_link(elements, "/phones/:id", {"step": "opens a phone"})["i"], 0)
        self.assertIsNone(jw.Walk._best_link(elements, "/cart", {"step": "opens the cart"}))

    def test_what_is_inside_a_shut_menu_is_not_offered_to_the_planner_until_the_menu_is_open(self):
        inside = {"i": 2, "tag": "a", "text": "Sign Up", "route": "/register", "menu": 1}
        elements = [{"i": 1, "tag": "summary", "text": "Your account", "menu": -1}, inside]
        self.assertEqual([e["i"] for e in jw.describe(elements)], [1])
        self.assertEqual([e["i"] for e in jw.describe(elements, include_menus=True)], [1, 2])

    def test_a_search_that_left_nothing_to_open_is_cleared_the_way_a_person_would_and_the_page_tried_again(self):
        pages = {**SHOP, "/phones": {"title": "Phone Catalogue", "elements": [
            link("Home", "/"),
            {"tag": "a", "text": "Clear search and filters", "route": "/phones", "area": "main",
             "reveals": [link("Home", "/"), link("Apple iPhone 15", "/phones/12", "main")]}]}}
        walk = self.walk_with(pages)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue", "/phones"),
                               step("UJ-001-S02", "Visitor reads a Phone Detail page", "/phones/:id"))
        with self.planner():
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertTrue(walked["steps"][1]["reached"], walked["steps"][1]["notes"])
        self.assertIn('clicked "Clear search and filters"', walked["steps"][1]["actions"])

    def test_when_no_link_leads_there_the_model_that_can_read_the_screen_is_asked_to_get_there(self):
        # The way is a button the links do not show: only a reader of the screen finds it.
        pages = {**SHOP, "/": {"title": "Home", "elements": [
            {"tag": "button", "text": "Shop the range", "goes": "/phones", "area": "main"}]}}
        asked = []

        def complete_json(system, user, validator=None, label="", **_):
            asked.append(user)
            return validator({"actions": [{"do": "click", "element": 0}]})

        walk = self.walk_with(pages)
        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue", "/phones")),
                               self.root / "journeys" / "UJ-001")
        done = walked["steps"][0]
        self.assertTrue(done["reached"], done["notes"])
        self.assertEqual(done["actions"], ['clicked "Shop the range"'])
        self.assertIn('Get to the "Phone Catalogue" screen (/phones)', asked[0])
        self.assertEqual(len(asked), 1)                          # once for the step, however many ways it was tried

    def test_a_model_that_cannot_find_the_way_either_leaves_the_step_not_reached_with_the_reason(self):
        pages = {**SHOP, "/": {"title": "Home", "elements": [link("Wishlist", "/wishlist")]}}
        walk = self.walk_with(pages)
        with self.planner([]):
            walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Cart", "/cart")), self.root / "journeys" / "UJ-001")
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertIn("no link on / leads towards /cart", walked["steps"][0]["notes"][0])

    def test_when_a_press_opens_a_menu_the_model_is_asked_again_with_the_menu_open(self):
        menu = [{"tag": "summary", "text": "Your account", "area": "nav"},
                {"tag": "a", "text": "Account Details", "route": "/account", "area": "nav", "opener": 0}]
        pages = {**SHOP, "/phones": {"title": "Phone Catalogue", "elements": menu}, "/account": {"title": "Account", "elements": []}}
        seen = []

        def complete_json(system, user, validator=None, label="", **_):
            seen.append(user)
            return validator({"actions": [{"do": "click", "element": 0}] if len(seen) == 1 else [{"do": "click", "element": 1}]})

        walk = self.walk_with(pages)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue, taps Your account and opens Account Details", "/phones"))
        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertEqual(len(seen), 2)
        self.assertNotIn('link "Account Details"', seen[0])           # shut: not offered the first time
        self.assertIn('link "Account Details" to /account', seen[1])
        self.assertEqual(walked["steps"][0]["actions"][-2:], ['clicked "Your account"', 'clicked "Account Details"'])
        self.assertEqual(walk.driver.route, "/account")

    ORDER_PAGES = {
        "/": {"title": "Home", "elements": [link("Orders", "/orders"), link("Cart", "/cart")]},
        "/orders": {"title": "Order", "elements": [
            {"tag": "button", "text": "Cancel order IM-1052", "opens_dialog": True, "area": "main"}, link("Home", "/")],
                    "dialog": [{"tag": "button", "text": "Cancel order", "closes_dialog": True},
                               {"tag": "button", "text": "Keep the order", "closes_dialog": True}]},
        "/cart": {"title": "Cart", "elements": [link("Home", "/")]},
    }

    def test_a_dialog_a_press_opened_is_confirmed_on_the_models_next_turn(self):
        # "taps Cancel order and confirms": the confirm button is in the dialog, which is only there once the first press was made.
        rows = ROWS + [{"route": "/orders", "file": "app/src/App.tsx", "name": "Order"}]
        turns = []

        def complete_json(system, user, validator=None, label="", **_):
            turns.append(user)
            click = 0 if len(turns) == 1 else 2             # the opener, then the dialog's own "Cancel order"
            return validator({"actions": [{"do": "click", "element": click}] if len(turns) <= 2 else []})

        walk = self.walk_with(copy_of(self.ORDER_PAGES), rows)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor taps Cancel order and confirms", "/orders"))
        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        done = walked["steps"][0]
        self.assertEqual(done["actions"][-2:], ['clicked "Cancel order IM-1052"', 'clicked "Cancel order"'])
        self.assertFalse(walk.driver.dialog)
        self.assertIn('button "Cancel order" (dialog)', turns[1])        # the dialog's buttons are in front of it the second time
        self.assertNotIn("(dialog)", turns[0])

    def test_a_dialog_left_open_is_closed_with_escape_before_the_next_step_so_it_does_not_cover_that_one(self):
        pages = copy_of(self.ORDER_PAGES)
        pages["/orders"]["elements"].append(link("Cart", "/cart"))
        rows = ROWS + [{"route": "/orders", "file": "app/src/App.tsx", "name": "Order"}]
        answers = iter([[{"do": "click", "element": 0}], [], []])
        walk = self.walk_with(pages, rows)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor taps Cancel order", "/orders"),
                               step("UJ-001-S02", "Visitor opens the Cart", "/cart"))
        with mock.patch("server_modules.llm.complete_json",
                        side_effect=lambda system, user, validator=None, **k: validator({"actions": next(answers, [])})):
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertTrue(walked["steps"][1]["reached"], walked["steps"][1]["notes"])
        self.assertIn(("key", "Escape"), walk.driver.calls)

    def test_a_link_that_is_there_but_does_nothing_is_a_failure(self):
        pages = {**SHOP, "/": {"title": "Home", "elements": [{"tag": "a", "text": "Cart", "route": "/cart", "goes": "/"}]}}
        walk = self.walk_with(pages)
        with self.planner():
            walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Cart", "/cart")), self.root / "journeys" / "UJ-001")
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertIn("did not open /cart", walked["steps"][0]["notes"][0])

    def test_what_a_step_says_to_do_is_done_with_what_the_model_picked_and_the_page_it_ends_on_is_kept(self):
        walk = self.walk_with()
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue and types a model into search", "/phones"))
        plan = [{"do": "fill", "element": 1, "value": "Samsung"}, {"do": "click", "element": 2}]
        with self.planner(plan):
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        done = walked["steps"][0]
        self.assertEqual(done["actions"], ['clicked "Phone Catalogue"', 'filled "Search model" with "Samsung"', 'clicked "Apple iPhone 15"'])
        self.assertEqual(walk.driver.filled, {1: "Samsung"})
        self.assertEqual(done["page"], "Phone Detail")
        self.assertEqual(len(done["shots"]), 2)                                      # on arrival, and after what was done
        self.assertTrue(done["reached"])

    def test_a_step_that_only_looks_asks_the_model_nothing_and_has_one_picture(self):
        walk = self.walk_with()
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor reads the Phone Catalogue", "/phones"))
        with mock.patch("server_modules.llm.complete_json", side_effect=AssertionError("asked")):
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertEqual(len(walked["steps"][0]["shots"]), 1)
        self.assertFalse((self.root / "journeys" / "UJ-001" / "S01-a.jpg").exists())

    def test_the_plan_is_asked_for_with_the_step_and_what_is_on_the_screen(self):
        walk = self.walk_with()
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor types a model into search", "/phones"))
        seen = []

        def complete_json(system, user, validator=None, **_):
            seen.append(user)
            return validator({"actions": []})

        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertIn("Visitor types a model into search", seen[0])
        self.assertIn('search field "Search model"', seen[0])
        self.assertIn('link "Home" to /', seen[0])
        self.assertIn("route `/phones`", seen[0])
        self.assertIn("What the screen says, from the top of it:", seen[0])
        self.assertIn("Prices from Rs 30,000", seen[0])          # words that are really on the page, to search and filter with
        for gone in ("signed in", "Signed in", "Nobody is signed in", "password"):
            self.assertNotIn(gone, seen[0])

    def test_a_model_that_cannot_plan_a_step_costs_that_step_its_actions_and_nothing_else(self):
        walk = self.walk_with()
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor types a model into search", "/phones"))
        with mock.patch("server_modules.llm.complete_json", side_effect=ValueError("no valid JSON")):
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertTrue(walked["steps"][0]["reached"])
        self.assertIn("could not say what to do", walked["steps"][0]["notes"][0])

    def test_the_pages_own_errors_in_the_browser_are_kept_with_the_step(self):
        walk = self.walk_with()
        walk.driver.error_text = ["TypeError: x is not a function"]
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor reads Home", "/"))
        with self.planner():
            walked = walk.walk(journey, self.root / "journeys" / "UJ-001")
        self.assertEqual(walked["steps"][0]["errors"], ["TypeError: x is not a function"])

    def test_stop_ends_the_walk_with_the_runs_own_cancellation(self):
        walk = self.walk_with()
        walk.cancelled = lambda: True
        with self.assertRaises(RunCancelled), self.planner():
            walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor reads Home", "/")), self.root / "journeys" / "UJ-001")

    def test_a_browser_that_has_gone_fails_every_step_with_what_it_said(self):
        walk = self.walk_with()
        walk.driver.reset = mock.Mock(side_effect=DriverError("the browser has stopped"))
        walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor reads Home", "/")), self.root / "journeys" / "UJ-001")
        self.assertEqual((walked["steps"][0]["reached"], walked["steps"][0]["notes"]), (False, ["the browser has stopped"]))

    def test_the_live_view_is_told_the_journey_each_step_and_the_end_only_when_it_is_the_one_shown(self):
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue", "/phones"))
        with self.planner():
            self.walk_with().walk(journey, self.root / "journeys" / "UJ-001")
        self.assertEqual(self.sent, [])                                  # not shown: nothing is sent
        shown = self.walk_with()
        shown.streaming = True
        with self.planner():
            shown.walk(journey, self.root / "journeys" / "UJ-001")
        states = [m["state"] for m in self.sent if m.get("kind") == "event"]
        self.assertEqual(states[0], "journey_start")
        self.assertEqual(states[-1], "journey_done")
        self.assertIn("step", states)
        self.assertIn("step_done", states)
        self.assertTrue(any(m.get("verb") == "CLICK" and m.get("label") == "Phone Catalogue" for m in self.sent))


# --- looking at the pictures and what is said about it ---------------------------------------------------------------

class JudgingTests(Harness):
    def walked(self, reached=(True, True), notes=((), ()), errors=((), ())):
        folder = self.root / "journeys" / "UJ-001"
        folder.mkdir(parents=True, exist_ok=True)
        steps = []
        for n, (ok, note, err) in enumerate(zip(reached, notes, errors), 1):
            (folder / f"S0{n}.jpg").write_bytes(b"jpg%d" % n)
            steps.append({"id": f"UJ-001-S0{n}", "step": f"step {n}", "route": "/", "expected": "/", "reached": ok,
                          "actions": [] if not ok else ["clicked a"], "notes": list(note), "visited": [], "shots": [f"S0{n}.jpg"],
                          "page": "Home", "errors": list(err)})
        return {"id": "UJ-001", "name": "Finding", "who": "Visitor", "setup": None, "steps": steps}

    JOURNEY = {"id": "UJ-001", "name": "Finding", "who": "Visitor", "steps": []}

    def test_the_pictures_go_to_the_model_in_the_order_of_the_steps_with_what_the_browser_did(self):
        seen = {}

        def complete_json(system, user, validator=None, label="", model="", images=None, **_):
            seen.update(user=user, images=images, model=model, label=label)
            return validator(judged(["UJ-001-S01", "UJ-001-S02"]))

        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            result = jw.judge("p", "vision-model", self.root, self.JOURNEY, self.walked())
        self.assertEqual(seen["images"], [b"jpg1", b"jpg2"])
        self.assertEqual(seen["label"], "journey review")
        self.assertIn("`UJ-001-S01` on /: \"step 1\" — picture 1.", seen["user"])
        self.assertIn("clicked a", seen["user"])
        self.assertTrue(result["completes"])
        self.assertEqual(set(result["steps"]), {"UJ-001-S01", "UJ-001-S02"})

    def test_an_answer_that_leaves_out_a_step_is_sent_back_to_be_completed(self):
        with self.assertRaisesRegex(ValueError, "missing: UJ-001-S02"):
            jw._clean_judgment(judged(["UJ-001-S01"]), ["UJ-001-S01", "UJ-001-S02"])
        with self.assertRaises(ValueError):
            jw._clean_judgment({"journey": {}}, ["UJ-001-S01"])

    def test_the_defects_are_cleaned_like_a_pages_and_kept_for_their_step(self):
        answer = judged(["UJ-001-S01"], defects={"UJ-001-S01": [
            {"severity": "HIGH", "where": "the menu", "problem": "cut off", "fix": "wrap it"}, {"problem": ""}, "junk"]})
        cleaned = jw._clean_judgment(answer, ["UJ-001-S01"])
        self.assertEqual(cleaned["steps"]["UJ-001-S01"]["defects"],
                         [{"severity": "high", "viewport": "desktop", "where": "the menu", "problem": "cut off", "fix": "wrap it"}])

    def test_everything_worth_fixing_in_a_journey_is_collected_from_the_walk_and_from_the_pictures(self):
        walked = self.walked(reached=(False, True), notes=(("no link on / leads towards /cart",), ()),
                             errors=((), ("TypeError: x",)))
        verdict = jw._clean_judgment(judged(["UJ-001-S01", "UJ-001-S02"], ok=False, completes=False,
                                            defects={"UJ-001-S02": [{"severity": "low", "problem": "tiny"},
                                                                    {"severity": "high", "where": "banner", "problem": "cut off"}]}),
                                     ["UJ-001-S01", "UJ-001-S02"])
        found = jw.problems(self.JOURNEY, walked, verdict)
        text = " | ".join(f"{p['step']}:{p['severity']}:{p['problem']}" for p in found)
        self.assertIn("UJ-001-S01:high:no link on / leads towards /cart", text)
        self.assertIn("UJ-001-S02:medium:the page reported an error in the browser: TypeError: x", text)
        # A prototype has no server: whether a screen shows the step's exact result is said, never sent to be fixed.
        self.assertIn("UJ-001-S02:low:the screenshot does not show the step done", text)
        self.assertIn("UJ-001-S02:high:cut off", text)
        self.assertIn("UJ-001-S02:low:tiny", text)
        self.assertEqual(len(jw._worth_fixing(found)), len(found) - 2)               # the low ones are reported, never fixed

    def test_a_home_page_that_would_not_open_is_a_problem_of_its_own(self):
        walked = {**self.walked(), "setup": {"ok": False, "note": "the browser could not open /", "shot": ""}}
        first = jw.problems(self.JOURNEY, walked, None)[0]
        self.assertEqual(first["step"], "start")
        self.assertNotIn("sign", first["where"].lower())

    def test_the_chat_shows_each_step_with_its_picture_and_what_was_found(self):
        walked = self.walked()
        verdict = jw._clean_judgment(judged(["UJ-001-S01", "UJ-001-S02"], defects={"UJ-001-S01": [
            {"severity": "high", "where": "menu", "problem": "cut off"}]}), ["UJ-001-S01", "UJ-001-S02"])
        jw._tell("p", self.JOURNEY, walked, verdict, jw.problems(self.JOURNEY, walked, verdict))
        shown = self.messages[-1]
        self.assertEqual(shown["title"], "[UJ-001] Finding · 1 to fix")
        self.assertEqual(shown["kind"], "visual_review")
        self.assertIn("**S01 ✓** step 1", shown["text"])
        self.assertIn("**high** · menu: cut off", shown["text"])
        self.assertEqual([i["path"] for i in shown["images"]],
                         [".agentforge/prototype/journeys/UJ-001/S01.jpg", ".agentforge/prototype/journeys/UJ-001/S02.jpg"])


# --- the whole test ---------------------------------------------------------------------------------------------------

class RunTests(Harness):
    def setUp(self):
        super().setUp()
        self.journeys_file([
            {"id": "UJ-001", "workflow_name": "Finding the right phone", "who": "Visitor", "steps": [
                step("UJ-001-S01", "Visitor opens Home", "/"), step("UJ-001-S02", "Visitor opens the Phone Catalogue", "/phones")]},
            {"id": "UJ-002", "workflow_name": "Buying", "who": "Customer", "steps": [
                step("UJ-002-S01", "Customer opens the Wishlist", "/wishlist"), step("UJ-002-S02", "Customer opens the Cart", "/cart")]}])
        self.browsers: list[FakeBrowser] = []
        self.pages = copy.deepcopy(SHOP)
        self.enterContext(mock.patch.object(jw, "Driver", self.make_driver))

    def make_driver(self, *args, **kwargs):
        browser = FakeBrowser(self.pages)
        self.browsers.append(browser)
        browser.args = kwargs
        return browser

    def models(self, verdicts=None, plan=None):
        """The model: a planner that has nothing to press, and a judge that finds the journey fine (or says what it is told)."""
        self.asked: list[tuple[str, int]] = []

        def complete_json(system, user, validator=None, label="", images=None, **_):
            self.asked.append((label, len(images or [])))
            if label == "journey step":
                return validator({"actions": plan or []})
            journey = "UJ-002" if "`UJ-002-S01`" in user else "UJ-001"
            ids = [f"{journey}-S01", f"{journey}-S02"]
            return validator((verdicts or {}).get(journey) or judged(ids))
        return mock.patch("server_modules.llm.complete_json", side_effect=complete_json)

    def run_test(self, session=None, **kwargs):
        return jw.run("p", session or self.session(), ROWS, **kwargs)

    def test_a_computer_with_no_browser_skips_it_with_a_line_saying_why(self):
        with mock.patch.object(screenshot, "working_browser", return_value=None):
            result = self.run_test()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual([m["title"] for m in self.messages], ["Journey test skipped"])
        self.assertEqual(self.browsers, [])

    def test_the_setting_turns_it_off_without_a_word_and_a_request_overrides_it(self):
        with mock.patch.object(config, "setting", lambda name, fallback=None: False if name == "prototype_journey_test" else fallback):
            self.assertEqual(self.run_test(), {"status": "off"})
            self.assertEqual(self.messages, [])
            with self.models():
                self.assertEqual(self.run_test(force=True)["status"], "done")

    def test_a_specification_with_no_journeys_has_nothing_to_click_through(self):
        self.journeys_file([])
        result = self.run_test()
        self.assertEqual((result["status"], result["reason"]), ("skipped", "no journeys"))

    def test_every_journey_is_walked_and_looked_at_and_the_report_and_the_chat_say_so(self):
        with self.models():
            result = self.run_test(fix=False)
        self.assertEqual((result["status"], result["journeys"], result["completing"], result["problems_found"]), ("done", 2, 2, 0))
        self.assertEqual(sorted(a for a in self.asked if a[0] == "journey review"), [("journey review", 2)] * 2)    # a picture a step
        titles = [m["title"] for m in self.messages]
        self.assertIn("[UJ-001] Finding the right phone · completes", titles)
        self.assertIn("[UJ-002] Buying · completes", titles)
        self.assertIn("2 can be completed. No problems found.", self.messages[-1]["text"])
        report = json.loads((self.root / "journeys" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual((report["model"], report["journeys"], report["completing"]), ("vision-model", 2, 2))
        self.assertEqual([r["id"] for r in report["results"]], ["UJ-001", "UJ-002"])
        self.assertEqual(self.phases[0], (jw.PHASE, "active"))
        self.assertEqual(self.phases[-1], (jw.PHASE, "complete"))
        self.assertEqual(self.progress[-1], 100)

    def test_a_journey_that_cannot_be_clicked_through_is_found_without_any_model_looking(self):
        self.pages["/"] = {"title": "Home", "elements": [link("Cart", "/cart"), link("Wishlist", "/wishlist")]}
        with self.models(), mock.patch("server_modules.vision.supports", return_value=False):
            result = self.run_test(fix=False)
        self.assertEqual(result["pictures_looked_at"], False)
        self.assertIn("cannot look at pictures", self.messages[0]["text"])
        self.assertEqual([a for a in self.asked if a[0] == "journey review"], [])
        self.assertTrue(any(p["problem"].startswith("no link on / leads towards /phones") for p in result["remaining"]))
        self.assertEqual(result["completing"], 1)        # the journey that starts from the wishlist still goes through

    def test_the_problems_that_matter_are_given_to_the_agent_the_app_is_built_again_and_the_journeys_that_had_them_are_walked_again(self):
        self.pages["/"] = {"title": "Home", "elements": [link("Cart", "/cart"), link("Wishlist", "/wishlist")]}

        def fix(root):
            change_the_app(root)
            self.pages["/"] = SHOP["/"]

        session = self.session(fix=fix)
        walked_before = len(self.browsers)
        with self.models():
            result = self.run_test(session)
        self.assertEqual(len(session.requests), 1)
        self.assertIn("`UJ-001`", session.requests[0])
        self.assertNotIn("`UJ-002`", session.requests[0])
        self.assertIn(".agentforge/prototype/app", session.requests[0])
        self.assertEqual(self.rebuilt, 1)
        self.assertEqual(result["fixed_journeys"], ["UJ-001"])
        self.assertEqual(result["remaining"], [])
        self.assertIn("1 journey changed to fix them", self.messages[-1]["text"])
        self.assertGreater(len(self.browsers), walked_before + 1)             # a browser again for the second walk

    def test_a_fix_that_changed_nothing_is_not_built_or_walked_again(self):
        self.pages["/"] = {"title": "Home", "elements": [link("Cart", "/cart"), link("Wishlist", "/wishlist")]}
        session = self.session(fix=lambda root: None)
        with self.models():
            result = self.run_test(session)
        self.assertEqual(self.rebuilt, 0)
        self.assertEqual(result["fixed_journeys"], [])
        self.assertTrue(result["remaining"])

    def test_a_review_only_changes_nothing_and_says_so(self):
        self.pages["/"] = {"title": "Home", "elements": [link("Cart", "/cart"), link("Wishlist", "/wishlist")]}
        session = self.session()
        with self.models():
            result = self.run_test(session, fix=False)
        self.assertEqual(session.requests, [])
        self.assertIn("nothing was changed, this was a test only", self.messages[-1]["text"])
        self.assertEqual(result["fixed_journeys"], [])

    def test_a_fix_that_stops_partway_does_not_end_the_test(self):
        self.pages["/"] = {"title": "Home", "elements": [link("Cart", "/cart"), link("Wishlist", "/wishlist")]}

        def fix(root):
            raise OSError("the model service dropped")

        with self.models():
            result = self.run_test(self.session(fix=fix))
        self.assertEqual(result["status"], "done")
        self.assertIn("the model service dropped", result["fix_stopped"])
        self.assertIn("The fix stopped before it was finished", self.messages[-1]["text"])

    def test_only_the_journey_on_screen_is_shown_live_and_it_is_the_only_one_walked_at_a_time(self):
        with mock.patch.object(bus, "viewers", lambda: 1), self.models():
            self.run_test(fix=False)
        self.assertEqual(len(self.browsers), 1)
        self.assertTrue(self.browsers[0].args["live"])
        self.assertTrue(callable(self.browsers[0].args["relay"]))
        states = [m["state"] for m in self.sent if m.get("kind") == "event"]
        self.assertEqual(states.count("journey_start"), 2)
        self.assertEqual(self.sent[-1], {"kind": "end"})                  # the preview is given back

    def test_with_nobody_watching_the_journeys_are_walked_in_parallel_and_nothing_is_streamed(self):
        with self.models():
            self.run_test(fix=False)
        self.assertEqual(len(self.browsers), 2)
        self.assertFalse(any(b.args["live"] for b in self.browsers))
        self.assertEqual([m for m in self.sent if m.get("kind") == "event"], [])
        self.assertTrue(all(b.closed for b in self.browsers))

    def test_stop_ends_the_test_and_gives_the_preview_back(self):
        session = self.session()
        session.cancelled = True
        with self.models(), self.assertRaises(RunCancelled):
            self.run_test(session)
        self.assertEqual(self.sent[-1], {"kind": "end"})

    def test_a_browser_that_will_not_start_is_a_failed_test_never_a_failed_prototype(self):
        with mock.patch.object(jw, "Driver", side_effect=lambda *a, **k: SimpleNamespace(
                start=mock.Mock(side_effect=DriverError("the browser did not start")), close=lambda: None)):
            result = self.run_test()
        self.assertEqual(result["status"], "failed")
        self.assertIn("did not start", result["reason"])
        self.assertEqual(self.phases[-1], (jw.PHASE, "failed"))


# --- the real browser, over a small real hash-routed app ---------------------------------------------------------------

APP = """<html><head><title>App</title></head><body><div id="app"></div><script>
var pages = {
  '/': '<h1>First</h1><a href="#/two">Go to two</a><input id="q" placeholder="Search"><select><option>A</option><option>B</option></select><a href="https://example.org/">Outside</a>',
  '/two': '<h1>Second</h1><a href="#/">Back</a>',
  '/menu': '<h1>Menu</h1><details class="acct"><summary>Your account</summary><div><a href="#/two">My Orders</a></div></details><p>Phones from Rs 30,000</p>',
  '/tall': '<div style="height:3200px"></div><a href="#/two">Far below</a><div style="height:1400px"></div>',
  '/swap': '<button onclick="document.getElementById(\\'a\\').hidden=true;document.getElementById(\\'c\\').hidden=false">swap</button><a id="a" href="#/">A</a><a id="c" href="#/two" hidden>C</a>',
  '/covered': '<a href="#/two" style="position:absolute;left:40px;top:40px;width:120px;height:30px">Under</a><div class="shield" style="position:fixed;left:0;top:0;width:100%;height:200px;background:#fff"></div>',
  '/modal': '<h1>Order</h1><dialog id="d"><button>Cancel order</button></dialog>'
};
function draw() {
  var route = location.hash.slice(1) || '/';
  document.getElementById('app').innerHTML = pages[route] || ('<h1>' + route + '</h1>');
  document.title = 'App ' + route;
  if (route === '/two') setTimeout(function () { throw new Error('boom') }, 50);
  if (route === '/modal') document.getElementById('d').showModal();
}
window.addEventListener('hashchange', draw);
html = document.documentElement; if (location.hash === '#/tall') html.style.scrollBehavior = 'smooth';
draw();
</script></body></html>"""


@unittest.skipUnless(screenshot.working_browser() and shutil.which("node"), "a browser and Node are needed to drive a real page")
class RealBrowserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.bundle = self.site / "bundle.html"
        self.bundle.write_text(APP, encoding="utf-8")
        self.frames: list[dict] = []

    def test_a_page_is_opened_its_things_listed_clicked_filled_photographed_and_its_errors_kept(self):
        with Driver(relay=self.frames.append, live=True) as driver:
            state = driver.goto(self.bundle, "/")
            self.assertEqual((state["route"], state["title"], state["heading"]), ("/", "App /", "First"))
            things = driver.elements()
            self.assertEqual([(e["tag"], e["route"], e["external"]) for e in things if e["tag"] == "a"],
                             [("a", "/two", False), ("a", "", True)])
            box = next(e for e in things if e["tag"] == "input")
            driver.fill(box["i"], "Samsung")
            self.assertEqual(next(e for e in driver.elements() if e["tag"] == "input")["value"], "Samsung")
            driver.fill(box["i"], "Nokia")                                  # what was there is replaced, not added to
            self.assertEqual(next(e for e in driver.elements() if e["tag"] == "input")["value"], "Nokia")
            choice = next(e for e in driver.elements() if e["tag"] == "select")
            self.assertEqual(choice["options"], ["A", "B"])
            driver.fill(choice["i"], "B")
            answer = driver.click(next(e for e in driver.elements() if e["route"] == "/two")["i"])
            self.assertEqual((answer["state"]["route"], answer["navigated"]), ("/two", True))
            picture = driver.screenshot(self.site / "shots" / "two.jpg")
            self.assertGreater(picture.stat().st_size, 500)
            self.assertTrue(any("boom" in e for e in driver.errors()))
            driver.reset()
            self.assertEqual(driver.goto(self.bundle, "/")["route"], "/")
        self.assertTrue(any(f.get("kind") == "frame" and f["frame"].startswith("data:image/jpeg") for f in self.frames))
        pointers = [f for f in self.frames if f.get("kind") == "cursor"]
        self.assertTrue(pointers)
        self.assertTrue(all("box" not in f["cursor"] for f in pointers))     # no rectangle is drawn round what is clicked

    def test_a_route_with_a_parameter_is_opened_with_a_sample_value(self):
        with Driver() as driver:
            self.assertEqual(driver.goto(self.bundle, "/orders/[id]")["route"], "/orders/1")
            self.assertEqual(driver.goto(self.bundle, "/orders/:id/edit")["route"], "/orders/1/edit")

    def test_what_is_inside_a_menu_that_is_shut_is_named_and_points_at_the_button_that_opens_it(self):
        with Driver() as driver:
            driver.goto(self.bundle, "/menu")
            things = driver.elements()
            button = next(e for e in things if e["tag"] == "summary")
            inside = next(e for e in things if e["route"] == "/two")
            self.assertEqual((inside["text"], inside["menu"]), ("My Orders", button["i"]))      # named, though it is shut
            self.assertEqual(button["menu"], -1)
            driver.click(button["i"])
            self.assertEqual(next(e for e in driver.elements() if e["route"] == "/two")["menu"], -1)
            self.assertIn("Phones from Rs 30,000", driver.text())

    def test_a_page_that_scrolls_smoothly_is_clicked_where_the_link_ends_up_not_where_it_was(self):
        with Driver() as driver:
            driver.goto(self.bundle, "/tall")
            link = next(e for e in driver.elements() if e["route"] == "/two")
            answer = driver.click(link["i"])
            self.assertEqual((answer["state"]["route"], answer["navigated"]), ("/two", True))

    def test_numbers_of_an_earlier_look_never_find_an_element_that_is_hidden_now(self):
        with Driver() as driver:
            driver.goto(self.bundle, "/swap")
            first = driver.elements()
            self.assertEqual([e["route"] for e in first if e["tag"] == "a"], ["/"])
            driver.click(first[0]["i"])
            later = driver.elements()
            shown = next(e for e in later if e["tag"] == "a")
            self.assertEqual(shown["route"], "/two")
            self.assertEqual(shown["i"], first[1]["i"])             # it was given the number the hidden one had
            self.assertEqual(driver.click(shown["i"])["state"]["route"], "/two")

    def test_a_link_with_something_laid_over_all_of_it_says_what_covers_it(self):
        with Driver() as driver:
            driver.goto(self.bundle, "/covered")
            link = next(e for e in driver.elements() if e["route"] == "/two")
            with self.assertRaisesRegex(DriverError, r"something else covers it \(div\.shield\)"):
                driver.click(link["i"])

    def test_escape_closes_a_dialog_that_is_open_over_the_page(self):
        with Driver() as driver:
            driver.goto(self.bundle, "/modal")
            self.assertEqual([e["area"] for e in driver.elements() if e["tag"] == "button"], ["dialog"])
            driver.key("Escape")
            self.assertEqual([e for e in driver.elements() if e["tag"] == "button"], [])

    def test_a_click_on_something_that_is_gone_says_so(self):
        with Driver() as driver:
            driver.goto(self.bundle, "/")
            with self.assertRaisesRegex(DriverError, "no longer on the page"):
                driver.click(99)


# --- the prompts, and where this is wired in ---------------------------------------------------------------------------

class WiringTests(unittest.TestCase):
    def test_the_prompts_resolve_and_tell_the_model_what_it_is_looking_at(self):
        plan = prompts.load("prototype/journey-plan", journey="Finding", who="Visitor", number=1, total=5, step="opens Home",
                            page="Home", route="/", heading="Find your phone",
                            text="Find your phone", elements='[0] link "Cart"', most=8)
        self.assertNotIn("{{", plan)
        self.assertIn('[0] link "Cart"', plan)
        self.assertIn("Find your phone", plan)
        self.assertIn("opens Home", plan)
        review = prompts.load("prototype/journey-review", who="A visitor", journey="Finding", id="UJ-001", steps="1. step", pictures="2 pictures in all.")
        self.assertNotIn("{{", review)
        self.assertIn("UJ-001-S01", review)
        self.assertIn('"completes"', review)
        fix = prompts.load("prototype/journey-fix", defects="### `UJ-001`", app=".agentforge/prototype/app",
                           skill=".agentforge/skills/web-artifacts-builder")
        self.assertNotIn("{{", fix)
        self.assertIn(".agentforge/prototype/app", fix)
        self.assertIn("replace_text", fix)
        # It is a prototype: the review is generous about what only a server could show, and nothing here is about accounts or HTML.
        self.assertIn("with sample data and no server behind it", review)
        self.assertIn("does not have to show up in another screen", review)
        self.assertIn("press the dialog's own button", plan)
        for text in (plan, review, fix):
            for gone in ("flow.js", "assets/app", "demo account", "signed-in", "HTML page", "static pages"):
                self.assertNotIn(gone, text)

    def test_the_prototype_is_clicked_through_after_its_pages_were_looked_at_and_before_it_is_handed_over(self):
        source = (ROOT / "prototype-agent/prototype_agent/prototype.py").read_text(encoding="utf-8")
        self.assertLess(source.index("visual_review.run(project, session, drawn)"), source.index("journey_walk.run(project, session"))
        self.assertLess(source.index("journey_walk.run(project, session"), source.index('"Prototype ready"'))

    def test_a_test_can_be_asked_for_on_a_project_that_already_has_a_prototype(self):
        from server_modules import runs

        started = []
        with mock.patch.object(runs, "_in_background", lambda *a, **k: started.append((a, k))), \
                mock.patch.object(runs.store, "require", return_value={}):
            answer = runs.review_screens({"project": "p", "what": "journeys", "fix": False})
            self.assertEqual(answer, {"ok": True, "project": "p", "what": "journeys", "fix": False})
            self.assertEqual(started[0][0][2], bus.DESIGNER)
            self.assertEqual(started[0][0][4:7], ("p", "journeys", False))
            with self.assertRaisesRegex(ValueError, "journeys"):
                runs.review_screens({"project": "p", "what": "everything"})

    def test_the_journeys_run_walks_the_prototype_and_reloads_the_preview_when_it_changed(self):
        from prototype_agent import prototype
        from server_modules import runs

        session = SimpleNamespace(cancelled=False)
        with mock.patch.object(prototype, "exists", return_value=True), mock.patch.object(prototype, "session_for", return_value=session), \
                mock.patch.object(prototype, "routes", return_value=ROWS), \
                mock.patch.object(prototype.journey_walk, "run", return_value={"status": "done", "fixed_journeys": ["UJ-001"]}) as walked, \
                mock.patch.object(prototype.bus, "prototype_changed") as changed:
            result = prototype.journeys("p", fix=True, model="m")
        self.assertEqual(result["status"], "done")
        self.assertEqual(walked.call_args.args, ("p", session, ROWS))
        self.assertEqual(walked.call_args.kwargs, {"fix": True, "model": "m", "force": True})
        changed.assert_called_once_with("p")
        self.assertIn("journeys", runs.HANDLERS["review_screens"].__doc__)

    def test_the_studio_has_the_button_and_the_live_view_for_it(self):
        pane = (ROOT / "studio/components/PrototypePane.jsx").read_text(encoding="utf-8")
        self.assertIn("api.reviewScreens(project, 'journeys', true)", pane)
        self.assertIn("<AgentBrowser />", pane)
        self.assertIn("<LiveE2EOverlay event={liveStep} />", pane)
        self.assertIn("reviewScreens:", (ROOT / "studio/lib/api.js").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
