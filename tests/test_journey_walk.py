"""The React prototype's journeys, clicked through in a browser with a picture at every step, then looked at (and fixed)."""
from __future__ import annotations

import copy
import json
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import screenshot  # noqa: E402
from prototype_agent import journey_walk as jw  # noqa: E402
from prototype_agent.journey_driver import Driver, DriverError  # noqa: E402
from server_modules import bus, config, live, prompts  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402

ROWS = [{"route": "/", "file": "app/src/pages/home.tsx", "name": "Home"},
        {"route": "/phones", "file": "app/src/pages/phones.tsx", "name": "Phone Catalogue"},
        {"route": "/phones/[id]", "file": "app/src/pages/phones-id.tsx", "name": "Phone Detail"},
        {"route": "/cart", "file": "app/src/pages/cart.tsx", "name": "Cart"},
        {"route": "/login", "file": "app/src/pages/login.tsx", "name": "Sign In"},
        {"route": "/wishlist", "file": "app/src/pages/wishlist.tsx", "name": "Wishlist"},
        {"route": "/account/orders", "file": "app/src/pages/account-orders.tsx", "name": "My Orders"}]
ACCOUNTS_DOC = {"sign_in": "/login", "accounts": [
    {"role": "Customer", "role_key": "customer", "display_name": "Demo Customer", "email": "customer@example.com",
     "password": "Demo!2026", "lands_on": "/wishlist"},
    {"role": "Shop Owner", "role_key": "shop_owner", "display_name": "Demo Owner", "email": "owner@example.com",
     "password": "Demo!2026", "lands_on": "/admin"}]}


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

    def test_the_prototype_is_opened_with_its_address_and_moved_between_screens_by_the_hash(self):
        driver = Driver()
        with mock.patch.object(driver, "call", return_value={"state": {"path": "/x"}}) as call:
            driver.goto(Path("bundle.html"), "?as=a#/x")
            driver.hash("/y")
        self.assertEqual(call.call_args_list[0].args, ("goto",))
        self.assertEqual(call.call_args_list[0].kwargs, {"file": "bundle.html", "suffix": "?as=a#/x"})
        self.assertEqual(call.call_args_list[1].kwargs, {"route": "/y"})


def step(sid, text, route):
    return {"id": sid, "step": text, "route": route}


# --- a prototype that is a table, and a browser that is a pointer into it ---------------------------------------------

class FakeBrowser:
    """What `Driver` is to the real prototype, over a tiny made-up one: screens (by route) with the things on them, and what pressing
    each does. The address is a path, as the app's hash is."""

    def __init__(self, pages: dict[str, dict], rows=ROWS):
        self.pages, self.rows = pages, rows
        self.path, self.user, self.filled, self.calls = "/", "", {}, []
        self.dialog, self.menu = False, False
        self.closed = False
        self.error_text: list[str] = []
        self.args: dict = {}

    def start(self):
        return self

    def close(self):
        self.closed = True

    def reset(self):
        self.path, self.user, self.filled, self.dialog, self.menu = "/blank", "", {}, False, False     # a new profile: a blank tab

    def page(self) -> dict:
        found = jw.page_for(self.path, self.rows)
        return self.pages.get(found["route"], {}) if found else {}

    def goto(self, file, suffix=""):
        signed = re.search(r"\?as=([^#]*)", suffix or "")
        self.user = unquote(signed.group(1)) if signed else ""
        self.path = "/" + (suffix.split("#", 1)[1].strip("/") if "#" in (suffix or "") else "")
        self.dialog = self.menu = False
        self.calls.append(("goto", self.path, self.user))
        return self.state()

    def hash(self, route):
        self.path = route
        return self.state()

    def state(self):
        page = self.page()
        return {"url": "file:///bundle.html#" + self.path, "title": "App", "path": self.path, "heading": page.get("heading", ""),
                "user": self.user, "failed": page.get("failed", "")}

    def text(self):
        return self.page().get("text", "")

    def key(self, name):
        self.calls.append(("key", name))
        if name == "Escape":
            self.dialog = self.menu = False
        return {"state": self.state()}

    def elements(self):
        page = self.page()
        shown = list(page.get("elements", []))
        if self.dialog:
            shown += [{**e, "area": "dialog"} for e in page.get("dialog", [])]
        if self.menu:
            shown += [{**e, "area": "dialog"} for e in page.get("menu", [])]
        found = []
        for i, base in enumerate(shown):
            found.append({"i": i, "tag": "a", "type": "", "role": "", "text": "", "label": "", "href": "", "to": "", "external": False,
                          "name": "", "placeholder": "", "area": "main", "popup": False, "disabled": False, "checked": False,
                          "value": "", "signOut": False, **base})
        return found

    def click(self, i):
        element = self.elements()[i]
        self.calls.append(("click", element["text"] or element["to"]))
        if (self.dialog or self.menu) and element["area"] != "dialog":
            raise DriverError("something else covers it (dialog)")
        before = self.path
        if element.get("opens_dialog"):
            self.dialog = True
        elif element.get("closes_dialog"):
            self.dialog = False
        elif element.get("opens_menu"):
            self.menu = True
        elif element.get("signs_out"):
            self.user, self.path, self.menu, self.dialog = "", "/", False, False
        elif element.get("signs_in") is not None:
            email = self.filled_by_label("email")
            secret = self.filled_by_label("password")
            wanted = element["signs_in"]
            if not wanted or (email == wanted["email"] and secret == wanted["password"]):
                self.user = (wanted or {}).get("email", "customer@example.com")
                self.path = element.get("goes", "/wishlist")
        else:
            if element.get("reveals") is not None:
                self.pages[jw.page_for(self.path, self.rows)["route"]] = {**self.page(), "elements": element["reveals"]}
            goes = element.get("goes") or (element["to"] if element["tag"] == "a" else "")
            if goes:
                self.path = goes
            self.menu = False
        return {"state": self.state(), "navigated": self.path != before}

    def filled_by_label(self, what):
        for i, value in self.filled.items():
            element = self.elements()[i]
            if what in f'{element["label"]} {element["placeholder"]} {element["type"]}'.lower():
                return value
        return ""

    def fill(self, i, value):
        element = self.elements()[i]
        self.calls.append(("fill", element["placeholder"] or element["label"], value))
        self.filled[i] = value
        return {"state": self.state()}

    def screenshot(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(b"\xff\xd8shot-" + self.path.encode())
        return Path(path)

    def errors(self):
        found, self.error_text = self.error_text, []
        return found


def link(text, to, area="nav"):
    return {"tag": "a", "text": text, "to": to, "area": area}


SIGN_IN_FORM = [
    {"tag": "input", "type": "email", "label": "Email", "placeholder": "you@example.com"},
    {"tag": "input", "type": "password", "label": "Password"},
    {"tag": "button", "type": "submit", "text": "Sign in", "signs_in": {"email": "customer@example.com", "password": "Demo!2026"}}]

SHOP = {
    "/": {"heading": "Find your phone", "elements": [link("Phone Catalogue", "/phones"), link("Cart", "/cart"), link("Sign in", "/login")]},
    "/phones": {"heading": "Phones", "text": "Phones\nPrices from Rs 30,000 to Rs 289,000", "elements": [
        link("Home", "/"), {"tag": "input", "type": "search", "placeholder": "Search model", "area": "main"},
        link("Apple iPhone 15", "/phones/7", "main")]},
    "/phones/[id]": {"heading": "Apple iPhone 15", "elements": [
        link("Home", "/"), {"tag": "button", "text": "Add to cart", "goes": "/cart", "area": "main"}]},
    "/cart": {"heading": "Your cart", "elements": [link("Home", "/")]},
    "/login": {"heading": "Sign in", "elements": SIGN_IN_FORM},
    "/wishlist": {"heading": "Wishlist", "elements": [link("Phone Catalogue", "/phones"), link("Cart", "/cart")]},
    "/account/orders": {"heading": "My orders", "elements": []},
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
        self.record = Path(self.temp.name) / ".agentforge"
        self.root = self.record / "prototype"
        (self.root / "app" / "src" / "pages").mkdir(parents=True)
        (self.root / "app" / "src" / "components").mkdir(parents=True)
        (self.root / "app" / "bundle.html").write_text("<html></html>", encoding="utf-8")
        for route, page in SHOP.items():
            row = next(r for r in ROWS if r["route"] == route)
            links = "".join(f"<Link to=\"{e['to']}\">{e.get('text')}</Link>" for e in page["elements"] if e.get("to"))
            (self.root / row["file"]).write_text(f"export default () => <main>{links}</main>", encoding="utf-8")
        (self.record / "srs").mkdir()
        self.messages: list[dict] = []
        self.sent: list[dict] = []
        self.progress: list[float] = []
        self.phases: list[tuple] = []
        for patch in (
            mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                              self.messages.append({"text": text, "title": title, "kind": kind, "images": images or []})),
            mock.patch.object(bus, "phase", lambda project, key, title, status="active", detail="", number=0, kind="run", agent="":
                              self.phases.append((key, status))),
            mock.patch.object(bus, "progress", lambda project, label, pct, agent="": self.progress.append(pct)),
            mock.patch.object(bus, "log", lambda *a, **k: None),
            mock.patch.object(bus, "viewers", lambda: 0),
            mock.patch.object(live, "handle", lambda project, body: self.sent.append(body)),
            mock.patch.object(live, "finish", lambda project: self.sent.append({"kind": "end"})),
            mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")),
            mock.patch("server_modules.vision.supports", return_value=True),
            mock.patch("server_modules.screen_review.next_round", side_effect=self._next_round),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _next_round(self, project, session, agent, done, remaining, where, title):
        """The person's answer to "Run round N?": what the test queued in `self.round_answers`, else No."""
        self.rounds_asked = getattr(self, "rounds_asked", [])
        self.rounds_asked.append((done, remaining, where))
        answers = getattr(self, "round_answers", [])
        return answers.pop(0) if answers else False

    def journeys_file(self, journeys):
        (self.record / "srs" / "user-journeys.json").write_text(json.dumps({"schema": "x", "journeys": journeys}), encoding="utf-8")

    def session(self, fix=None, model="vision-model"):
        done = SimpleNamespace(record=self.record, cancelled=False, model=model, requests=[])
        done.agent = lambda m="": SimpleNamespace(model=m or model)

        def run_direct(request, model=""):
            done.requests.append(request)
            if fix:
                fix(self.root)
            return {"status": "complete", "text": "Fixed.", "rounds": 1}

        done.run_direct = run_direct
        return done

    def walk_with(self, pages=None, rows=ROWS):
        return jw.Walk("p", "vision-model", self.root, rows, ACCOUNTS_DOC, jw.link_graph(self.root, rows),
                       FakeBrowser(copy.deepcopy(pages or SHOP), rows), streaming=False, cancelled=lambda: False)


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

    def test_a_screen_is_the_route_that_takes_an_address_in_and_a_route_written_exactly_wins(self):
        self.assertEqual(jw.page_for("/phones/7", ROWS)["route"], "/phones/[id]")
        self.assertEqual(jw.page_for("/phones", ROWS)["route"], "/phones")
        self.assertEqual(jw.page_for("/", ROWS)["route"], "/")
        self.assertIsNone(jw.page_for("/nowhere", ROWS))
        rows = ROWS + [{"route": "/phones/new", "file": "app/src/pages/phones-new.tsx", "name": "New"}]
        self.assertEqual(jw.page_for("/phones/new", rows)["route"], "/phones/new")
        self.assertEqual(jw.page_for("/phones/7", rows)["route"], "/phones/[id]")

    def test_a_step_names_its_screen_however_the_value_in_the_route_is_written(self):
        self.assertEqual(jw.page_route("/phones/:id", ROWS), "/phones/[id]")
        self.assertEqual(jw.page_route("/phones/[phoneId]", ROWS), "/phones/[id]")
        self.assertEqual(jw.page_route("/phones/", ROWS), "/phones")
        self.assertEqual(jw.page_route("/phones/12", ROWS), "/phones/[id]")
        self.assertEqual(jw.page_route("/nowhere", ROWS), "")

    def test_a_visitor_never_signs_in_and_a_role_is_its_demo_account(self):
        accounts = ACCOUNTS_DOC["accounts"]
        self.assertIsNone(jw.account_for("Visitor", accounts))
        self.assertIsNone(jw.account_for("", accounts))
        self.assertEqual(jw.account_for("Customer", accounts)["email"], "customer@example.com")
        self.assertEqual(jw.account_for("Shop Owner", accounts)["email"], "owner@example.com")
        self.assertEqual(jw.account_for("shop_owner", accounts)["role_key"], "shop_owner")
        self.assertIsNone(jw.account_for("Somebody Else", accounts))

    def test_the_way_between_two_screens_is_found_from_the_links_in_the_source(self):
        graph = {"/a": {"/b"}, "/b": {"/c"}, "/c": {"/d"}, "/d": set()}
        self.assertEqual(jw._way(graph, "/a", "/d"), "/b")
        self.assertEqual(jw._way(graph, "/a", "/b"), "/b")
        self.assertEqual(jw._way(graph, "/d", "/a"), "")
        found = jw.link_graph(self.root, ROWS)
        self.assertEqual(found["/"], {"/phones", "/cart", "/login"})
        self.assertEqual(found["/phones"], {"/", "/phones/[id]"})            # a link to /phones/7 is a link to the detail screen

    def test_what_the_shared_navigation_links_to_every_screen_links_to(self):
        (self.root / "app" / "src" / "components" / "shell.tsx").write_text(
            "export const Shell = () => <nav><Link to='/wishlist'>W</Link><a href={`#/phones/${id}`}>x</a>"
            "<Link to=\"/nowhere\">n</Link></nav>", encoding="utf-8")
        found = jw.link_graph(self.root, ROWS)
        self.assertIn("/wishlist", found["/cart"])
        self.assertNotIn("/nowhere", found["/cart"])
        self.assertNotIn("/cart", found["/cart"])                          # never a link to itself

    def test_a_component_of_the_toolkit_is_not_shared_navigation(self):
        (self.root / "app" / "src" / "components" / "ui").mkdir()
        (self.root / "app" / "src" / "components" / "ui" / "button.tsx").write_text("const x = '/wishlist'", encoding="utf-8")
        self.assertNotIn("/wishlist", jw.link_graph(self.root, ROWS)["/cart"])

    def test_what_can_be_used_is_listed_without_signing_out_or_other_websites(self):
        elements = [{"i": 0, "tag": "a", "text": "Log out", "signOut": True}, {"i": 1, "tag": "a", "text": "Docs", "external": True},
                    {"i": 2, "tag": "button", "text": "Save", "signOut": False}]
        self.assertEqual([e["i"] for e in jw.describe(elements)], [2])
        self.assertEqual([e["i"] for e in jw.describe(elements, allow_sign_out=True)], [0, 2])

    def test_the_planner_is_told_what_each_thing_is_and_whether_it_opens_a_menu(self):
        lines = [jw._line(e) for e in (
            {"i": 0, "tag": "a", "text": "Cart", "to": "/cart", "area": "nav"},
            {"i": 1, "tag": "button", "text": "Account", "popup": True, "area": "nav"},
            {"i": 2, "tag": "button", "role": "tab", "text": "All", "area": "main"},
            {"i": 3, "tag": "button", "role": "switch", "text": "Alerts", "checked": True, "area": "main"},
            {"i": 4, "tag": "input", "type": "password", "label": "Password", "value": ""})]
        self.assertEqual(lines[0], '[0] link "Cart" to /cart (nav)')
        self.assertIn("(opens a list or menu)", lines[1])
        self.assertTrue(lines[2].startswith('[2] tab "All"'))
        self.assertIn("(ticked)", lines[3])
        self.assertEqual(lines[4], '[4] password field "Password"')

    def test_a_plan_is_checked_against_what_is_really_on_the_screen(self):
        elements = [{"i": 0, "tag": "input", "type": "text"}, {"i": 1, "tag": "button", "disabled": False},
                    {"i": 2, "tag": "button", "disabled": True}, {"i": 3, "tag": "button", "role": "switch", "checked": False},
                    {"i": 4, "tag": "button", "role": "switch", "checked": True}]
        plan = jw.check_plan({"actions": [{"do": "fill", "element": 0, "value": "Ada"}, {"do": "click", "element": 1}]}, elements)
        self.assertEqual(plan, [{"do": "fill", "element": 0, "value": "Ada"}, {"do": "click", "element": 1}])
        for bad in ({"actions": [{"do": "click", "element": 9}]}, {"actions": [{"do": "fill", "element": 1, "value": "x"}]},
                    {"actions": [{"do": "click", "element": 2}]}, {"nothing": 1}, "text"):
            with self.assertRaises(ValueError):
                jw.check_plan(bad, elements)
        self.assertEqual(jw.check_plan({"actions": []}, elements), [])
        many = {"actions": [{"do": "click", "element": 1}] * 20}
        self.assertEqual(len(jw.check_plan(many, elements)), jw.MAX_ACTIONS)

    def test_ticking_a_custom_switch_is_a_press_and_one_already_on_is_left_alone(self):
        elements = [{"i": 3, "tag": "button", "role": "switch", "checked": False}, {"i": 4, "tag": "button", "role": "switch", "checked": True}]
        self.assertEqual(jw.check_plan({"actions": [{"do": "fill", "element": 3, "value": "yes"}]}, elements),
                         [{"do": "click", "element": 3}])
        self.assertEqual(jw.check_plan({"actions": [{"do": "fill", "element": 4, "value": "yes"}]}, elements), [])


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
        with mock.patch.object(jw, "JUDGE_SECONDS", 0.2), mock.patch("server_modules.llm.complete_json", side_effect=lambda *a, **k: release.wait(30)), \
                mock.patch.object(jw, "Driver", lambda *a, **k: FakeBrowser(copy_of(SHOP))):
            result = jw.run("p", self.session(), ROWS, ACCOUNTS_DOC, fix=False)
        report = json.loads((self.root / "journeys" / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(result["status"], "done")
        self.assertIn("did not answer within", report["results"][0]["judge_error"])
        self.assertEqual(report["results"][0]["steps"][0]["reached"], True)


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

    def go(self, walk, journey, *plans):
        with self.planner(*plans):
            return walk.walk(journey, self.root / "journeys" / "UJ-001")

    def test_every_step_is_reached_by_clicking_the_links_the_screens_have_and_a_picture_is_taken_of_each(self):
        walk = self.walk_with()
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens Home", "/"),
                               step("UJ-001-S02", "Visitor opens the Phone Catalogue", "/phones"),
                               step("UJ-001-S03", "Visitor reads a Phone Detail page", "/phones/:id"))
        walked = self.go(walk, journey)
        self.assertEqual([s["reached"] for s in walked["steps"]], [True, True, True])
        self.assertEqual(walked["steps"][2]["visited"], ["/phones", "/phones/[id]"])
        self.assertEqual([c for c in walk.driver.calls if c[0] == "click"], [("click", "Phone Catalogue"), ("click", "Apple iPhone 15")])
        self.assertEqual(walked["steps"][1]["actions"], ['clicked "Phone Catalogue"'])
        self.assertEqual(walked["steps"][2]["page"], "Phone Detail")
        for s in walked["steps"]:
            self.assertTrue((self.root / "journeys" / "UJ-001" / s["shots"][-1]).is_file())

    def test_someone_who_never_signs_in_starts_at_the_home_page_and_not_on_a_blank_tab(self):
        walk = self.walk_with()
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue", "/phones")))
        self.assertEqual(walk.driver.calls[0], ("goto", "/", ""))
        self.assertTrue(walked["steps"][0]["reached"])
        self.assertEqual(walked["steps"][0]["visited"], ["/", "/phones"])

    def test_a_person_who_signs_in_does_it_on_the_sign_in_page_by_typing_the_demo_account_into_its_form(self):
        walk = self.walk_with()
        walked = self.go(walk, self.journey("Customer", step("UJ-001-S01", "Customer opens the Wishlist", "/wishlist")))
        self.assertTrue(walked["setup"]["ok"], walked["setup"])
        self.assertEqual(walk.driver.calls[0], ("goto", "/login", ""))                    # signed out, on the sign-in page
        self.assertIn(("fill", "you@example.com", "customer@example.com"), walk.driver.calls)
        self.assertIn(("fill", "Password", "Demo!2026"), walk.driver.calls)
        self.assertIn(("click", "Sign in"), walk.driver.calls)
        self.assertEqual(walked["account"], "customer@example.com")
        self.assertTrue(walked["steps"][0]["reached"])
        self.assertTrue((self.root / "journeys" / "UJ-001" / "S00.jpg").is_file())
        self.assertFalse(any(call[0] == "goto" and call[2] for call in walk.driver.calls))      # never opened pre-signed-in

    def test_a_sign_in_page_with_a_button_for_the_role_and_no_form_is_used_through_the_button(self):
        pages = {**SHOP, "/login": {"heading": "Sign in", "elements": [
            {"tag": "button", "text": "Continue as Customer", "signs_in": None, "goes": "/wishlist", "area": "main"}]}}
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Customer", step("UJ-001-S01", "Customer opens the Wishlist", "/wishlist")))
        self.assertTrue(walked["setup"]["ok"], walked["setup"])
        self.assertIn(("click", "Continue as Customer"), walk.driver.calls)

    def test_a_sign_in_page_that_has_no_way_in_is_said_and_the_journey_still_walks_signed_in_by_the_address(self):
        pages = {**SHOP, "/login": {"heading": "Sign in", "elements": []}}
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Customer", step("UJ-001-S01", "Customer opens the Wishlist", "/wishlist")))
        self.assertFalse(walked["setup"]["ok"])
        self.assertIn("no form for the demo account customer@example.com", walked["setup"]["note"])
        self.assertIn(("goto", "/wishlist", "customer@example.com"), walk.driver.calls)
        self.assertEqual(walk.driver.user, "customer@example.com")
        self.assertTrue(walked["steps"][0]["reached"])

    def test_a_form_that_signs_nobody_in_is_a_problem_of_the_journey(self):
        pages = {**SHOP, "/login": {"heading": "Sign in", "elements": [
            *SIGN_IN_FORM[:2], {**SIGN_IN_FORM[2], "signs_in": {"email": "somebody@else.com", "password": "x"}}]}}
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Customer", step("UJ-001-S01", "Customer opens the Wishlist", "/wishlist")))
        self.assertFalse(walked["setup"]["ok"])
        self.assertIn("but nobody was signed in", walked["setup"]["note"])
        self.assertEqual(jw.problems(self.journey("Customer"), walked, None)[0]["step"], "sign-in")

    def test_an_app_that_does_not_say_who_is_signed_in_is_signed_in_when_the_sign_in_page_was_left(self):
        pages = {**SHOP, "/login": {"heading": "Sign in", "elements": [
            *SIGN_IN_FORM[:2], {**SIGN_IN_FORM[2], "goes": "/wishlist"}]}}
        walk = self.walk_with(pages)
        original = walk.driver.state

        def state():
            return {**original(), "user": ""}              # an app made before the app said who is signed in
        walk.driver.state = state
        walked = self.go(walk, self.journey("Customer", step("UJ-001-S01", "Customer opens the Wishlist", "/wishlist")))
        self.assertTrue(walked["setup"]["ok"], walked["setup"])

    def test_a_journey_that_begins_with_signing_in_is_walked_signed_out_and_its_first_step_signs_in(self):
        walk = self.walk_with()
        journey = self.journey("Customer", step("UJ-001-S01", "Customer types their email and password and gets in", "/login"),
                               step("UJ-001-S02", "Customer opens the Wishlist", "/wishlist"))
        walked = self.go(walk, journey)
        self.assertIsNone(walked["setup"])                                    # nobody was signed in beforehand
        self.assertEqual(walk.driver.calls[0], ("goto", "/login", ""))
        first, second = walked["steps"]
        self.assertTrue(first["reached"], first["notes"])
        self.assertEqual(first["actions"], ['the demo account was typed in and "Sign in" pressed'])
        self.assertEqual(walk.driver.user, "customer@example.com")
        self.assertTrue(second["reached"])
        self.assertEqual(jw.problems(journey, walked, None), [])

    def test_a_first_step_that_signs_in_with_a_form_that_does_not_work_is_not_reached_and_says_so(self):
        pages = {**SHOP, "/login": {"heading": "Sign in", "elements": [
            *SIGN_IN_FORM[:2], {**SIGN_IN_FORM[2], "signs_in": {"email": "somebody@else.com", "password": "x"}}]}}
        walked = self.go(self.walk_with(pages), self.journey("Customer", step("UJ-001-S01", "Customer signs in", "/login")))
        first = walked["steps"][0]
        self.assertFalse(first["reached"])
        self.assertIn("did not sign anyone in", first["notes"][0])

    def test_a_first_step_that_signs_in_on_a_page_with_no_way_in_says_so(self):
        pages = {**SHOP, "/login": {"heading": "Sign in", "elements": []}}
        walked = self.go(self.walk_with(pages), self.journey("Customer", step("UJ-001-S01", "Customer signs in", "/login")))
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertIn("no form for the demo account", walked["steps"][0]["notes"][0])

    SIGN_OUT = {"tag": "button", "text": "Sign out", "signOut": True, "signs_out": True, "area": "nav"}

    def test_a_signed_in_person_signs_out_once_to_reach_a_sign_in_or_sign_up_screen(self):
        pages = {**SHOP, "/wishlist": {"heading": "Wishlist", "elements": [self.SIGN_OUT]}}
        walk = self.walk_with(pages)
        journey = self.journey("Customer", step("UJ-001-S01", "Customer reads the Wishlist", "/wishlist"),
                               step("UJ-001-S02", "Customer opens Sign In again", "/login"))
        walked = self.go(walk, journey)
        second = walked["steps"][1]
        self.assertTrue(second["reached"], second["notes"])
        self.assertEqual(second["actions"], ['clicked "Sign out"', 'clicked "Sign in"'])
        self.assertEqual(walk.driver.user, "")

    def test_the_sign_out_that_is_in_a_menu_is_found_by_opening_the_menu(self):
        pages = {**SHOP, "/wishlist": {"heading": "Wishlist", "elements": [
            {"tag": "button", "text": "Account", "popup": True, "opens_menu": True, "area": "nav"}], "menu": [self.SIGN_OUT]}}
        walk = self.walk_with(pages)
        journey = self.journey("Customer", step("UJ-001-S01", "Customer reads the Wishlist", "/wishlist"),
                               step("UJ-001-S02", "Customer opens Sign In again", "/login"))
        second = self.go(walk, journey)["steps"][1]
        self.assertTrue(second["reached"], second["notes"])
        self.assertEqual(walk.driver.user, "")

    def test_a_signed_in_person_is_not_signed_out_to_reach_any_other_screen(self):
        pages = {**SHOP, "/wishlist": {"heading": "Wishlist", "elements": [link("Cart", "/cart"), self.SIGN_OUT]}}
        walk = self.walk_with(pages)
        journey = self.journey("Customer", step("UJ-001-S01", "Customer opens My Orders", "/account/orders"))
        walked = self.go(walk, journey, [])
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertNotIn(("click", "Sign out"), walk.driver.calls)
        self.assertEqual(walk.driver.user, "customer@example.com")

    def test_somebody_who_is_not_signed_in_is_not_asked_to_sign_out(self):
        walk = self.walk_with({**SHOP, "/": {"heading": "Home", "elements": [self.SIGN_OUT]}})
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens Sign In", "/login")), [])
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertNotIn(("click", "Sign out"), walk.driver.calls)

    def test_a_screen_with_no_link_to_the_next_one_is_a_step_that_could_not_be_done_and_the_walk_goes_on(self):
        pages = {**SHOP, "/": {"heading": "Home", "elements": [link("Sign in", "/login")]}}
        walk = self.walk_with(pages)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Cart", "/cart"),
                               step("UJ-001-S02", "Visitor opens Home", "/"))
        walked = self.go(walk, journey)
        first, second = walked["steps"]
        self.assertFalse(first["reached"])
        self.assertIn("no link on Home leads towards Cart", first["notes"][0])
        self.assertTrue((self.root / "journeys" / "UJ-001" / first["shots"][-1]).is_file())      # a picture even of that
        self.assertTrue(second["reached"])

    def test_a_step_on_a_screen_the_prototype_does_not_have_says_so(self):
        walked = self.go(self.walk_with(), self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Blog", "/blog")))
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertIn("no screen for the route /blog", walked["steps"][0]["notes"][0])

    def test_when_there_is_no_direct_link_the_way_through_another_screen_is_clicked_a_hop_at_a_time(self):
        pages = {**SHOP, "/": {"heading": "Home", "elements": [link("Phone Catalogue", "/phones")]},
                 "/phones": {"heading": "Phones", "elements": [link("Cart", "/cart")]}}
        (self.root / "app/src/pages/home.tsx").write_text("<Link to='/phones'>p</Link>", encoding="utf-8")
        (self.root / "app/src/pages/phones.tsx").write_text("<Link to='/cart'>c</Link>", encoding="utf-8")
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Cart", "/cart")))
        self.assertTrue(walked["steps"][0]["reached"])
        self.assertEqual(walked["steps"][0]["visited"], ["/", "/phones", "/cart"])

    def test_a_link_in_a_menu_that_is_shut_is_reached_by_opening_the_menu_first_like_a_person_does(self):
        pages = {**SHOP, "/": {"heading": "Home", "elements": [
            {"tag": "button", "text": "Your account", "popup": True, "opens_menu": True, "area": "nav"}],
            "menu": [link("My Orders", "/account/orders")]}}
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens My Orders", "/account/orders")))
        done = walked["steps"][0]
        self.assertTrue(done["reached"], done["notes"])
        self.assertEqual(done["actions"], ['opened "Your account"', 'clicked "My Orders"'])

    def test_a_menu_without_the_link_is_closed_again_and_the_next_menu_is_tried(self):
        pages = {**SHOP, "/": {"heading": "Home", "elements": [
            {"tag": "button", "text": "Language", "popup": True, "opens_menu": True, "area": "nav"}], "menu": [link("English", "/")]}}
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens My Orders", "/account/orders")))
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertIn(("key", "Escape"), walk.driver.calls)

    def test_the_link_in_the_page_itself_is_used_before_one_in_the_navigation(self):
        walk = self.walk_with()
        elements = [{"i": 0, "tag": "a", "text": "Cart", "to": "/cart", "area": "nav"},
                    {"i": 1, "tag": "a", "text": "Cart", "to": "/cart", "area": "main"},
                    {"i": 2, "tag": "a", "text": "Cart", "to": "/cart", "area": "footer"}]
        self.assertEqual(walk._best_link(elements, "/cart", {"step": "opens the cart"})["i"], 1)
        self.assertIsNone(walk._best_link(elements, "/phones", {"step": "x"}))

    def test_a_search_that_left_nothing_to_open_is_cleared_the_way_a_person_would_and_the_screen_tried_again(self):
        pages = {**SHOP, "/phones": {"heading": "Phones", "elements": [
            link("Home", "/"),
            {"tag": "button", "text": "Clear search and filters", "area": "main",
             "reveals": [link("Home", "/"), link("Apple iPhone 15", "/phones/7", "main")]}]}}
        walk = self.walk_with(pages)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue", "/phones"),
                               step("UJ-001-S02", "Visitor reads a Phone Detail page", "/phones/:id"))
        walked = self.go(walk, journey)
        self.assertTrue(walked["steps"][1]["reached"], walked["steps"][1]["notes"])
        self.assertIn('clicked "Clear search and filters"', walked["steps"][1]["actions"])

    def test_when_no_link_leads_there_the_model_that_can_read_the_screen_is_asked_to_get_there(self):
        pages = {**SHOP, "/": {"heading": "Home", "elements": [{"tag": "button", "text": "Shop the range", "goes": "/phones", "area": "main"}]}}
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
        pages = {**SHOP, "/": {"heading": "Home", "elements": [link("Sign in", "/login")]}}
        walked = self.go(self.walk_with(pages), self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Cart", "/cart")), [])
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertIn("no link on Home leads towards Cart", walked["steps"][0]["notes"][0])

    def test_when_a_press_opens_a_menu_the_model_is_asked_again_with_the_menu_open(self):
        pages = {**SHOP, "/phones": {"heading": "Phones", "elements": [
            {"tag": "button", "text": "Sort by", "popup": True, "opens_menu": True, "area": "main"}],
            "menu": [{"tag": "button", "text": "Price: low to high", "area": "dialog"}]}}
        seen = []

        def complete_json(system, user, validator=None, label="", **_):
            seen.append(user)
            if len(seen) == 1:
                return validator({"actions": [{"do": "click", "element": 0}]})
            return validator({"actions": [{"do": "click", "element": 1}]})

        walk = self.walk_with(pages)
        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor sorts the phones by price", "/phones")),
                               self.root / "journeys" / "UJ-001")
        self.assertEqual(len(seen), 2)
        self.assertIn("Price: low to high", seen[1])
        self.assertNotIn("Price: low to high", seen[0])
        self.assertEqual(walked["steps"][0]["actions"][-2:], ['clicked "Sort by"', 'clicked "Price: low to high"'])

    def test_a_dialog_a_press_opened_is_confirmed_on_the_models_next_turn(self):
        pages = {**SHOP, "/cart": {"heading": "Your cart", "elements": [
            {"tag": "button", "text": "Remove", "opens_dialog": True, "popup": True, "area": "main"}],
            "dialog": [{"tag": "button", "text": "Yes, remove it", "closes_dialog": True}]}}
        turns = [[{"do": "click", "element": 0}], [{"do": "click", "element": 1}]]
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor removes a phone from the cart and confirms", "/cart")), *turns)
        self.assertEqual(walked["steps"][0]["actions"][-2:], ['clicked "Remove"', 'clicked "Yes, remove it"'])
        self.assertFalse(walk.driver.dialog)

    def test_a_dialog_left_open_is_closed_with_escape_before_the_next_step_so_it_does_not_cover_that_one(self):
        pages = {**SHOP, "/cart": {"heading": "Your cart", "elements": [
            link("Home", "/"), {"tag": "button", "text": "Remove", "opens_dialog": True, "area": "main"}],
            "dialog": [{"tag": "button", "text": "Yes", "closes_dialog": True}]}}
        walk = self.walk_with(pages)
        journey = self.journey("Visitor", step("UJ-001-S01", "Visitor presses Remove in the Cart", "/cart"),
                               step("UJ-001-S02", "Visitor opens Home", "/"))
        walked = self.go(walk, journey, [{"do": "click", "element": 1}], [])
        self.assertTrue(all(s["reached"] for s in walked["steps"]), [s["notes"] for s in walked["steps"]])
        self.assertIn(("key", "Escape"), walk.driver.calls)

    def test_a_link_that_the_source_says_is_there_but_does_nothing_is_a_failure(self):
        pages = {**SHOP, "/": {"heading": "Home", "elements": [{"tag": "a", "text": "Cart", "to": "/cart", "area": "main", "goes": "/"}]}}
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Cart", "/cart")), [])
        self.assertFalse(walked["steps"][0]["reached"])
        self.assertIn('clicking "Cart" did not open Cart', walked["steps"][0]["notes"][0])

    def test_what_a_step_says_to_do_is_done_with_what_the_model_picked_and_the_screen_it_ends_on_is_kept(self):
        pages = {**SHOP, "/phones": {"heading": "Phones", "elements": [
            link("Home", "/"), {"tag": "input", "type": "search", "placeholder": "Search model", "area": "main"},
            link("Apple iPhone 15", "/phones/7", "main")]}}
        walk = self.walk_with(pages)
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor types a model into search and opens it", "/phones")),
                         [{"do": "fill", "element": 1, "value": "iPhone"}, {"do": "click", "element": 2}])
        done = walked["steps"][0]
        self.assertEqual(done["actions"][-2:], ['filled "Search model" with "iPhone"', 'clicked "Apple iPhone 15"'])
        self.assertEqual(done["page"], "Phone Detail")
        self.assertEqual(len(done["shots"]), 2)                    # on arrival, and after what was done

    def test_a_step_that_only_looks_asks_the_model_nothing_and_has_one_picture(self):
        walk = self.walk_with()
        with mock.patch("server_modules.llm.complete_json", side_effect=AssertionError("asked")):
            walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor reads the Phone Catalogue", "/phones")),
                               self.root / "journeys" / "UJ-001")
        self.assertEqual(len(walked["steps"][0]["shots"]), 1)

    def test_the_plan_is_asked_for_with_the_step_and_what_is_on_the_screen(self):
        asked = []

        def complete_json(system, user, validator=None, label="", **_):
            asked.append(user)
            return validator({"actions": []})

        walk = self.walk_with()
        with mock.patch("server_modules.llm.complete_json", side_effect=complete_json):
            walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor types a model into search", "/phones")),
                      self.root / "journeys" / "UJ-001")
        text = asked[0]
        self.assertIn("Step 1 of 1", text)
        self.assertIn("Visitor types a model into search", text)
        self.assertIn("Phone Catalogue", text)
        self.assertIn('[1] search field "Search model"', text)
        self.assertIn("Prices from Rs 30,000", text)
        self.assertIn("Nobody is signed in.", text)

    def test_a_model_that_cannot_plan_a_step_costs_that_step_its_actions_and_nothing_else(self):
        walk = self.walk_with()
        with mock.patch("server_modules.llm.complete_json", side_effect=ValueError("no valid JSON")):
            walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor types a model into search", "/phones")),
                               self.root / "journeys" / "UJ-001")
        self.assertTrue(walked["steps"][0]["reached"])
        self.assertIn("the model could not say what to do here", walked["steps"][0]["notes"][0])

    def test_the_pages_own_errors_in_the_browser_are_kept_with_the_step(self):
        walk = self.walk_with()
        walk.driver.error_text = ["TypeError: x is undefined"]
        walked = self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens Home", "/")))
        self.assertEqual(walked["steps"][0]["errors"], ["TypeError: x is undefined"])

    def test_a_screen_that_could_not_be_drawn_is_a_high_problem_with_what_it_said(self):
        pages = {**SHOP, "/": {"heading": "", "failed": "Home could not be drawn TypeError: yen is not defined", "elements": []}}
        walked = self.go(self.walk_with(pages), self.journey("Visitor", step("UJ-001-S01", "Visitor opens Home", "/")))
        self.assertIn("yen is not defined", walked["steps"][0]["crashed"])
        found = jw.problems(self.journey("Visitor"), walked, None)
        self.assertTrue(any(p["severity"] == "high" and "could not be drawn" in p["problem"] for p in found), found)

    def test_stop_ends_the_walk_with_the_runs_own_cancellation(self):
        walk = self.walk_with()
        walk.cancelled = lambda: True
        with self.assertRaises(RunCancelled):
            walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor opens Home", "/")), self.root / "journeys" / "UJ-001")

    def test_a_browser_that_has_gone_fails_every_step_with_what_it_said(self):
        walk = self.walk_with()
        walk.driver.reset = mock.Mock(side_effect=DriverError("the browser has stopped"))
        walked = walk.walk(self.journey("Visitor", step("UJ-001-S01", "Visitor opens Home", "/")), self.root / "journeys" / "UJ-001")
        self.assertEqual((walked["steps"][0]["reached"], walked["steps"][0]["notes"]), (False, ["the browser has stopped"]))

    def test_the_live_view_is_told_the_journey_each_step_and_the_end_only_when_it_is_the_one_shown(self):
        walk = self.walk_with()
        walk.streaming = True
        self.go(walk, self.journey("Visitor", step("UJ-001-S01", "Visitor opens the Phone Catalogue", "/phones")))
        states = [m["state"] for m in self.sent if m.get("kind") == "event"]
        self.assertEqual(states[0], "journey_start")
        self.assertIn("step", states)
        self.assertEqual(states[-2:], ["step_done", "journey_done"])
        quiet = self.walk_with()
        before = len(self.sent)
        self.go(quiet, self.journey("Visitor", step("UJ-001-S01", "Visitor opens Home", "/")))
        self.assertEqual(len(self.sent), before)


class JudgingTests(Harness):
    def walked(self, reached=(True, True), notes=((), ()), errors=((), ())):
        folder = self.root / "journeys" / "UJ-001"
        folder.mkdir(parents=True, exist_ok=True)
        steps = []
        for n, (ok, note, err) in enumerate(zip(reached, notes, errors), 1):
            (folder / f"S0{n}.jpg").write_bytes(b"jpg%d" % n)
            steps.append({"id": f"UJ-001-S0{n}", "step": f"step {n}", "route": "/", "expected": "/", "reached": ok,
                          "actions": [] if not ok else ["clicked a"], "notes": list(note), "visited": [], "shots": [f"S0{n}.jpg"],
                          "page": "Home", "errors": list(err), "crashed": ""})
        return {"id": "UJ-001", "name": "Finding", "who": "Visitor", "account": "", "setup": None, "steps": steps}

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
        walked = self.walked(reached=(False, True), notes=(("no link on Home leads towards Cart",), ()),
                             errors=((), ("TypeError: x",)))
        verdict = jw._clean_judgment(judged(["UJ-001-S01", "UJ-001-S02"], ok=False, completes=False,
                                            defects={"UJ-001-S02": [{"severity": "low", "problem": "tiny"},
                                                                    {"severity": "high", "where": "banner", "problem": "cut off"}]}),
                                     ["UJ-001-S01", "UJ-001-S02"])
        found = jw.problems(self.JOURNEY, walked, verdict)
        text = " | ".join(f"{p['step']}:{p['severity']}:{p['problem']}" for p in found)
        self.assertIn("UJ-001-S01:high:no link on Home leads towards Cart", text)
        self.assertIn("UJ-001-S02:medium:the page reported an error in the browser: TypeError: x", text)
        # A prototype has no server: whether a screen shows the step's exact result is said, never sent to be fixed.
        self.assertIn("UJ-001-S02:low:the screenshot does not show the step done", text)
        self.assertIn("UJ-001-S02:high:cut off", text)
        self.assertIn("UJ-001-S02:low:tiny", text)
        self.assertEqual(len(jw._worth_fixing(found)), len(found) - 2)               # the low ones are reported, never fixed

    def test_a_failed_sign_in_is_a_problem_of_its_own(self):
        walked = {**self.walked(), "setup": {"ok": False, "note": "signing in did not take", "shot": ""}}
        self.assertEqual(jw.problems(self.JOURNEY, walked, None)[0]["step"], "sign-in")

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
        return jw.run("p", session or self.session(), ROWS, ACCOUNTS_DOC, **kwargs)

    def test_a_computer_with_no_browser_skips_it_with_a_line_saying_why(self):
        with mock.patch.object(screenshot, "working_browser", return_value=None):
            result = self.run_test()
        self.assertEqual(result["status"], "skipped")
        self.assertEqual([m["title"] for m in self.messages], ["Journey test skipped"])
        self.assertEqual(self.browsers, [])

    def test_a_prototype_that_is_not_bundled_has_nothing_to_click_through(self):
        (self.root / "app" / "bundle.html").unlink()
        result = self.run_test()
        self.assertEqual((result["status"], result["reason"]), ("skipped", "the prototype is not bundled"))

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
        self.pages["/"] = {"heading": "Home", "elements": [link("Sign in", "/login")]}
        with self.models(), mock.patch("server_modules.vision.supports", return_value=False):
            result = self.run_test(fix=False)
        self.assertEqual(result["pictures_looked_at"], False)
        self.assertIn("cannot look at pictures", self.messages[0]["text"])
        self.assertEqual([a for a in self.asked if a[0] == "journey review"], [])
        self.assertTrue(any(p["problem"].startswith("no link on Home") for p in result["remaining"]))
        self.assertEqual(result["completing"], 1)        # the journey that starts from the wishlist still goes through

    def test_a_journey_still_failing_after_round_one_is_asked_about_and_yes_fixes_only_it_again(self):
        self.pages["/"] = {"heading": "Home", "elements": [link("Sign in", "/login")]}
        fixes = []

        def fix(root):
            fixes.append(len(fixes) + 1)
            if len(fixes) == 2:                       # the second round's fix is the one that works
                self.pages["/"] = SHOP["/"]

        self.round_answers = [True]
        session = self.session(fix=fix)
        with self.models():
            result = self.run_test(session)
        self.assertEqual(len(session.requests), 2)
        self.assertNotIn("`UJ-002`", session.requests[1])
        self.assertEqual([(done, where) for done, _left, where in self.rounds_asked], [(1, "1 journey")])
        self.assertEqual([r["round"] for r in result["rounds"]], [1, 2])
        self.assertEqual(result["completing"], 2)

    def test_no_after_round_one_leaves_the_journey_reported_as_it_is(self):
        self.pages["/"] = {"heading": "Home", "elements": [link("Sign in", "/login")]}
        session = self.session(fix=lambda root: None)
        with self.models():
            result = self.run_test(session)
        self.assertEqual(len(session.requests), 1)
        self.assertEqual(len(self.rounds_asked), 1)
        self.assertTrue(result["remaining"])

    def test_the_problems_that_matter_are_given_to_the_agent_the_app_is_bundled_and_the_journeys_walked_again(self):
        self.pages["/"] = {"heading": "Home", "elements": [link("Sign in", "/login")]}
        order = []

        def fix(root):
            order.append("fix")
            self.pages["/"] = SHOP["/"]

        session = self.session(fix=fix)
        walked_before = len(self.browsers)
        with self.models():
            result = self.run_test(session, rebuild=lambda: order.append("bundle"))
        self.assertEqual(len(session.requests), 1)
        self.assertIn("`UJ-001`", session.requests[0])
        self.assertNotIn("`UJ-002`", session.requests[0])
        self.assertEqual(order, ["fix", "bundle"])
        self.assertEqual(result["fixed_journeys"], ["UJ-001"])
        self.assertEqual(result["remaining"], [])
        self.assertIn("1 journey changed to fix them", self.messages[-1]["text"])
        self.assertGreater(len(self.browsers), walked_before + 1)             # a browser again for the second walk

    def test_a_review_only_changes_nothing_and_says_so(self):
        self.pages["/"] = {"heading": "Home", "elements": [link("Sign in", "/login")]}
        session = self.session()
        bundled = []
        with self.models():
            result = self.run_test(session, fix=False, rebuild=lambda: bundled.append(1))
        self.assertEqual(session.requests, [])
        self.assertEqual(bundled, [])
        self.assertIn("nothing was changed, this was a test only", self.messages[-1]["text"])
        self.assertEqual(result["fixed_journeys"], [])

    def test_a_fix_that_stops_partway_does_not_end_the_test(self):
        self.pages["/"] = {"heading": "Home", "elements": [link("Sign in", "/login")]}

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


# --- the real browser, over a small real hash-routed page --------------------------------------------------------------

PAGE = """<!doctype html><title>App</title><div id="root"></div>
<script>
window.__afUser = new URLSearchParams(location.search).get('as') || ''
const root = document.getElementById('root')
const screens = {
  '/': () => `<nav><a href="#/cart">Cart</a><button aria-haspopup="menu" aria-expanded="false" id="account">Account</button></nav>
              <main><h1>Home</h1><a href="#/phones/7">Apple iPhone</a><a href="https://example.org/">Docs</a>
              <div id="card" style="cursor:pointer" onclick="location.hash='#/cart'">A card you can press</div>
              <button onclick="document.title='clicked'">Plain</button></main>`,
  '/cart': () => `<main><h1>Cart</h1><label for="q">Quantity</label><input id="q" placeholder="How many"><select id="s"><option value="a">One</option><option value="b">Two</option></select>
                  <button onclick="window.afSaved = document.getElementById('q').value + document.getElementById('s').value">Save</button></main>`,
  '/phones/7': () => `<main><h1>Phone 7</h1><a href="#/">Home</a></main>`,
  '/broken': () => `<div data-af-error="Oops could not be drawn">Oops could not be drawn</div>`,
}
function draw() {
  const path = '/' + location.hash.replace(/^#/, '').split('/').filter(Boolean).join('/')
  const found = screens[path] || (path.startsWith('/phones/') ? screens['/phones/7'] : screens['/'])
  root.innerHTML = found()
  const account = document.getElementById('account')
  if (account) account.onclick = () => { root.insertAdjacentHTML('beforeend', '<div role="menu"><a role="menuitem" href="#/cart">My cart</a></div>'); account.setAttribute('aria-expanded', 'true') }
}
window.addEventListener('hashchange', draw)
draw()
console.error('a page error')
</script>"""


@unittest.skipUnless(screenshot.working_browser() and shutil.which("node"), "a browser and Node are needed to drive a real page")
class RealBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.bundle = Path(cls.folder.name) / "bundle.html"
        cls.bundle.write_text(PAGE, encoding="utf-8")
        cls.driver = Driver(size=(1000, 700)).start()

    @classmethod
    def tearDownClass(cls):
        cls.driver.close()
        cls.folder.cleanup()

    def setUp(self):
        self.driver.reset()

    def test_the_prototype_is_opened_at_a_screen_signed_in_and_its_state_says_where_it_is_and_who(self):
        state = self.driver.goto(self.bundle, "?as=ada%40example.com#/cart")
        self.assertEqual((state["path"], state["heading"], state["user"]), ("/cart", "Cart", "ada@example.com"))
        self.assertEqual(self.driver.goto(self.bundle, "")["path"], "/")

    def test_what_can_be_pressed_is_listed_with_where_each_link_goes_and_what_opens_a_menu(self):
        self.driver.goto(self.bundle, "#/")
        found = {e["text"]: e for e in self.driver.elements() if e["text"]}
        self.assertEqual(found["Cart"]["to"], "/cart")
        self.assertEqual(found["Apple iPhone"]["to"], "/phones/7")
        self.assertTrue(found["Docs"]["external"])
        self.assertTrue(found["Account"]["popup"])
        self.assertIn("A card you can press", found)                    # drawn to be pressed, with no link or button in it
        self.assertEqual(found["Cart"]["area"], "nav")

    def test_a_press_that_opens_another_screen_changes_the_hash_and_says_it_navigated(self):
        self.driver.goto(self.bundle, "#/")
        link = next(e for e in self.driver.elements() if e["text"] == "Apple iPhone")
        answer = self.driver.click(link["i"])
        self.assertTrue(answer["navigated"])
        self.assertEqual(answer["state"]["path"], "/phones/7")
        again = next(e for e in self.driver.elements() if e["text"] == "Home")
        self.assertEqual(self.driver.click(again["i"])["state"]["path"], "/")

    def test_a_card_with_a_click_handler_is_pressed_like_a_person_would(self):
        self.driver.goto(self.bundle, "#/")
        card = next(e for e in self.driver.elements() if e["text"] == "A card you can press")
        self.assertEqual(self.driver.click(card["i"])["state"]["path"], "/cart")

    def test_a_menu_is_opened_and_what_is_in_it_is_listed_as_in_an_open_layer(self):
        self.driver.goto(self.bundle, "#/")
        self.driver.click(next(e for e in self.driver.elements() if e["text"] == "Account")["i"])
        item = next(e for e in self.driver.elements() if e["text"] == "My cart")
        self.assertEqual((item["area"], item["to"]), ("dialog", "/cart"))

    def test_a_field_is_filled_a_list_is_chosen_and_the_apps_own_handler_sees_both(self):
        self.driver.goto(self.bundle, "#/cart")
        things = {e["label"] or e["text"]: e for e in self.driver.elements()}
        self.driver.fill(things["Quantity"]["i"], "3")
        select = next(e for e in self.driver.elements() if e["tag"] == "select")
        self.assertEqual(select["options"], ["One", "Two"])
        self.driver.fill(select["i"], "Two")
        self.driver.click(next(e for e in self.driver.elements() if e["text"] == "Save")["i"])
        self.assertEqual(self.driver.state()["path"], "/cart")
        shot = Path(self.folder.name) / "cart.jpg"
        self.driver.screenshot(shot)
        self.assertGreater(shot.stat().st_size, 500)

    def test_a_screen_that_could_not_be_drawn_says_so_in_the_state(self):
        state = self.driver.goto(self.bundle, "#/broken")
        self.assertIn("could not be drawn", state["failed"])

    def test_the_pages_own_errors_in_the_browser_are_kept(self):
        self.driver.goto(self.bundle, "#/")
        self.assertIn("a page error", " ".join(self.driver.errors()))

    def test_a_click_on_something_that_is_gone_says_so(self):
        self.driver.goto(self.bundle, "#/")
        elements = self.driver.elements()
        self.driver.goto(self.bundle, "#/cart")
        self.driver.elements()
        with self.assertRaises(DriverError):
            self.driver.click(len(elements) + 50)

    def test_the_hash_moves_to_another_screen_without_loading_the_page_again(self):
        self.driver.goto(self.bundle, "#/")
        self.assertEqual(self.driver.hash("/cart")["path"], "/cart")


class WiringTests(unittest.TestCase):
    def test_the_prompts_resolve_and_tell_the_model_what_it_is_looking_at(self):
        plan = prompts.load("prototype/journey-plan", journey="Buying", who="Customer", number=2, total=3, step="adds to cart",
                            page="Cart", file="/cart", heading="Your cart", signed_in=" Signed in as x.", text="t", elements="[0] button", most=8)
        self.assertIn("Step 2 of 3", plan)
        self.assertIn("(`/cart`)", plan)
        review = prompts.load("prototype/journey-review", who="Customer", journey="Buying", id="UJ-001", steps="1. x", pictures="2 pictures.")
        self.assertIn("working prototype", review)
        self.assertIn("shared", prompts.load("prototype/journey-fix", defects="x") + prompts.load("prototype/visual-fix", defects="x")
                      + "shared")
        for name in ("journey-fix", "visual-fix"):
            text = prompts.load(f"prototype/{name}", defects="DEFECTS")
            self.assertIn("DEFECTS", text)
            self.assertIn(".agentforge/prototype/app/src", text)
            self.assertNotIn("assets/app.css", text)
            self.assertNotIn("flow.js", text)
        self.assertIn("{{", "{{x}}")      # (the placeholders above are all filled)
        for text in (plan, review):
            self.assertNotIn("{{", text)

    def test_the_prototype_is_looked_at_after_it_is_drawn_and_before_it_is_handed_over(self):
        from prototype_agent import prototype as prototyper
        order = []
        session = SimpleNamespace(cancelled=False, record=Path("."))
        with mock.patch.object(prototyper.visual_review, "run", side_effect=lambda *a, **k: order.append("screens")), \
                mock.patch.object(prototyper.journey_walk, "run", side_effect=lambda *a, **k: order.append("journeys")), \
                mock.patch.object(prototyper, "routes", return_value=[{"route": "/"}]), \
                mock.patch.object(prototyper, "_read_record", return_value={}):
            drawn = prototyper._look_at("p", session, [{"route": "/"}])
        self.assertEqual(order, ["screens", "journeys"])
        self.assertEqual(drawn, [{"route": "/"}])

    def test_stop_between_the_two_ends_the_run(self):
        from prototype_agent import prototype as prototyper
        session = SimpleNamespace(cancelled=False, record=Path("."))
        with mock.patch.object(prototyper.visual_review, "run", side_effect=lambda *a, **k: setattr(session, "cancelled", True)), \
                mock.patch.object(prototyper.journey_walk, "run", side_effect=AssertionError("walked")), \
                mock.patch.object(prototyper, "_read_record", return_value={}), self.assertRaises(RunCancelled):
            prototyper._look_at("p", session, [])

    def test_a_test_can_be_asked_for_on_a_project_that_already_has_a_prototype(self):
        from server_modules import runs
        started = []
        with mock.patch.object(runs, "_in_background", lambda name, project, agent, fn, *a, **k: started.append((name, agent, a))), \
                mock.patch.object(runs.store, "require", return_value={}), mock.patch.object(runs, "_remember_model"):
            runs.review_screens({"project": "p", "what": "journeys"})
            runs.review_screens({"project": "p", "what": "prototype", "fix": False})
            runs.review_screens({"project": "p"})
            with self.assertRaisesRegex(ValueError, "what must be"):
                runs.review_screens({"project": "p", "what": "everything"})
        self.assertEqual([(a, args[1]) for _, a, args in started], [(bus.DESIGNER, "journeys"), (bus.DESIGNER, "prototype"),
                                                                    (bus.DEVELOPER, "both")])
        self.assertFalse(started[1][2][2])

    def test_the_journeys_run_walks_the_prototype_and_reloads_the_preview_when_it_changed(self):
        from prototype_agent import prototype as prototyper
        session = SimpleNamespace(cancelled=False, record=Path("."))
        with mock.patch.object(prototyper, "exists", return_value=True), mock.patch.object(prototyper, "session_for", return_value=session), \
                mock.patch.object(prototyper, "routes", return_value=[{"route": "/"}]), mock.patch.object(prototyper, "_read_record", return_value={}), \
                mock.patch.object(prototyper.journey_walk, "run", return_value={"status": "done", "fixed_journeys": ["UJ-001"]}) as walk, \
                mock.patch.object(prototyper.bus, "prototype_changed") as changed:
            result = prototyper.journeys("p")
        self.assertEqual(result["status"], "done")
        self.assertTrue(walk.call_args.kwargs["force"])
        self.assertTrue(callable(walk.call_args.kwargs["rebuild"]))
        changed.assert_called_once_with("p")

    def test_there_must_be_a_prototype_to_look_at(self):
        from prototype_agent import prototype as prototyper
        with mock.patch.object(prototyper, "exists", return_value=False):
            for ask in (prototyper.review, prototyper.journeys):
                with self.assertRaisesRegex(ValueError, "no prototype"):
                    ask("p")

    def test_the_studio_has_the_buttons_and_the_live_view_for_it(self):
        pane = (ROOT / "studio" / "components" / "PrototypePane.jsx").read_text(encoding="utf-8")
        for expected in ("AgentBrowser", "LiveE2EOverlay", "look('journeys')", "look('prototype')", "api.reviewScreens"):
            self.assertIn(expected, pane)


if __name__ == "__main__":
    unittest.main()
