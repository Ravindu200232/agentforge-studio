"""The prototype's journeys, clicked through in a real browser, with a picture at every step.

The specification lists the journeys (`.agentforge/srs/user-journeys.json`): who does what, step by step, on which screen. Here
each one is walked the way a person would walk it, in a browser that is already on the computer (`journey_driver.py`): it starts
on the prototype's home page, then for every step finds the way to the screen the step happens on by clicking the links the app
really has, does what the step says there (a model reads what can be pressed or filled and says what to press and fill), and
takes a picture. The prototype is one React app, so a screen is a route of it (`bundle.html#/orders`). Nothing about the app is
checked by reading its code: a link that is not there, or a button that does nothing, shows up as a step that could not be done.

A model that can look at pictures then looks at the pictures of each journey and says, step by step, whether the step is shown done
and what is visibly wrong on the screen, and whether the journey can be completed at all. What is found is fixed in the prototype
app's source (which is then built again), the journeys that had problems are walked once more, and what is still wrong is reported
as it is. The walk is shown live in the Studio, the way a build's end-to-end tests are, and everything is in the chat with the
pictures.

A model that cannot look at pictures still gets the walk (each step reached or not, the pages' own errors); it just does not get the
pictures looked at, and the chat says so. A computer with no browser skips all of it, with one line saying why. Neither is an error,
and nothing here ever fails the prototype: it is a test, not a gate.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ollama_terminal import screenshot
from server_modules import bus, config, journeys as journey_model, live, llm, prompts, screen_review, web_app
from server_modules.session import RunCancelled

from . import screens
from .journey_driver import Driver, DriverError

PHASE = "prototype:journeys"
JOURNEY_DIR = "journeys"
REPORT = "report.json"
MAX_JOURNEYS = 24
MAX_STEPS = 10                 # a step past this is neither walked nor judged
MAX_ACTIONS = 8
TURNS = 3                      # times the model is asked what to do on one step (a menu or a dialog it opened is then in front of it)
MAX_PICTURES = 10              # what one journey's review is shown
LANES = 3
HOPS = 4                       # the most screens a step goes through to get to the one it happens on
PACE_MS = 350                  # slow enough to follow while it is shown live
SYSTEM = ("You are a meticulous tester of a clickable prototype. You are shown screenshots taken while a person's journey was clicked "
          "through in a browser, and you report only what you can see, as the JSON object you are asked for. You never invent "
          "something you cannot see.")
SYSTEM_PLAN = ("You are a person using a clickable prototype in a browser, deciding what to press and fill on the screen in front of "
               "you to carry out one step. You answer with the JSON object you are asked for.")

# Words that say a step is about doing something on its screen, not about getting to it or looking at it.
_DOING = re.compile(r"\b(types?|typing|enters?|fills?|gives?|taps?|clicks?|presses?|chooses?|selects?|saves?|submits?|adds?|sets?|"
                    r"changes?|cancels?|confirms?|uploads?|pays?|writes?|hides?|removes?|deletes?|filters?|narrows?|puts?|creates?|"
                    r"refunds?|marks?|searches?|sends?|edits?|continues?|books?|buys?|signs?|logs?|compares?|checks? out)\b", re.I)
_CLEAR = re.compile(r"\b(clear|reset)\b", re.I)


PLAN_SECONDS = 150             # the longest the model has to say what to press on one screen
JUDGE_SECONDS = 420            # the longest it has to look at the pictures of one journey


def enabled() -> bool:
    return bool(config.setting("prototype_journey_test", True))


def _within(seconds: float, function: Any, *args: Any, **kwargs: Any) -> Any:
    """`function(*args)`, but not for longer than `seconds`: a model call that has stopped answering must not stop a whole walk
    with it (`llm.within`)."""
    return llm.within(seconds, function, *args, **kwargs)


# --- what there is to walk -------------------------------------------------------------------------------------------

def load_journeys(record: Path) -> list[dict[str, Any]]:
    """The journeys of the specification, each with a few steps that name the route they happen on."""
    try:
        data = json.loads((record / "srs" / "user-journeys.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    found = []
    for row in (data.get("journeys") if isinstance(data, dict) else None) or []:
        if not isinstance(row, dict):
            continue
        steps = [s for s in (row.get("steps") or []) if isinstance(s, dict) and str(s.get("step") or "").strip()]
        if row.get("id") and steps:
            found.append({"id": str(row["id"]), "name": str(row.get("workflow_name") or row["id"]), "who": str(row.get("who") or ""),
                          "steps": [{"id": str(s.get("id") or f"{row['id']}-S{n:02d}"), "step": str(s["step"]).strip(),
                                     "route": str(s.get("route") or "")} for n, s in enumerate(steps[:MAX_STEPS], 1)]})
    return found[:MAX_JOURNEYS]


def page_for(route: str, rows: list[dict[str, Any]]) -> str:
    """The route of the prototype page a journey step's route is (`/phones/:id` and `/phones/[id]` are one page), or ""."""
    wanted = journey_model._route_key(route)  # noqa: SLF001
    for row in rows:
        if journey_model._route_key(row.get("route")) == wanted:  # noqa: SLF001
            return str(row.get("route") or "")
    for row in rows:                                          # the same page with its parameter spelled another way
        if web_app.route_matches(str(row.get("route") or ""), wanted):
            return str(row.get("route") or "")
    return ""


def at_page(current: str, target: str) -> bool:
    """Is the app on the page `target` names? A page with a parameter in its route is on a concrete value of it."""
    return bool(target) and web_app.route_matches(target, current)


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", str(text).lower()) if len(w) > 2}


# --- what the planner is shown ---------------------------------------------------------------------------------------

def describe(elements: list[dict[str, Any]], allow_sign_out: bool = False, include_menus: bool = False) -> list[dict[str, Any]]:
    """What can be used on the screen as the planner sees it: sign-out and other websites left out, and what is inside a menu that
    is shut (it can be used once the menu is open, which is what `include_menus` is for)."""
    return [e for e in elements if not e.get("external") and not (e.get("signOut") and not allow_sign_out)
            and (include_menus or e.get("menu", -1) < 0)
            and not (e.get("tag") == "input" and e.get("type") in {"submit", "reset", "image"} and not e.get("text"))]


def _line(e: dict[str, Any]) -> str:
    name = e.get("label") or e.get("text") or e.get("placeholder") or e.get("name") or ""
    if e.get("tag") == "a":
        return f'[{e["i"]}] link "{name}"' + (f' to {e["route"]}' if e.get("route") else "") + f' ({e.get("area")})'
    if e.get("tag") == "select":
        return f'[{e["i"]}] list "{name}" with the choices: {" | ".join(e.get("options") or [])}'
    if e.get("tag") in {"input", "textarea"}:
        kind = e.get("type") or "text"
        if kind in {"checkbox", "radio"}:
            return f'[{e["i"]}] {kind} "{name}" ({"ticked" if e.get("checked") else "not ticked"})'
        if kind in {"submit", "button"}:
            return f'[{e["i"]}] button "{name}"'
        return (f'[{e["i"]}] {kind} field "{name}"' + (f' (now "{e["value"]}")' if e.get("value") else "")
                + (" (disabled)" if e.get("disabled") else ""))
    return f'[{e["i"]}] button "{name}"' + (" (disabled)" if e.get("disabled") else "") + f' ({e.get("area")})'


def check_plan(data: Any, elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the model said to do, as clean actions on things that are really on the screen. What is wrong is the repair prompt."""
    if not isinstance(data, dict) or not isinstance(data.get("actions"), list):
        raise ValueError('answer with one JSON object that has an "actions" list (empty when nothing needs doing)')
    by_index = {e["i"]: e for e in elements}
    actions = []
    for row in data["actions"][:MAX_ACTIONS]:
        if not isinstance(row, dict):
            continue
        do = str(row.get("do") or "").strip().lower()
        try:
            element = by_index[int(row.get("element"))]
        except (TypeError, ValueError, KeyError):
            raise ValueError(f'"element" must be one of the numbers on the screen, not {row.get("element")!r}') from None
        if do == "fill" and element["tag"] in {"input", "textarea", "select"}:
            actions.append({"do": "fill", "element": element["i"], "value": str(row.get("value") if row.get("value") is not None else "")})
        elif do == "click" and not element.get("disabled"):
            actions.append({"do": "click", "element": element["i"]})
        else:
            raise ValueError(f'`{do}` cannot be done to [{element["i"]}] ({element["tag"]})')
    return actions


# --- walking one journey ---------------------------------------------------------------------------------------------

class Walk:
    """One journey, clicked through in one browser."""

    def __init__(self, project: str, model: str, root: Path, rows: list[dict[str, Any]], driver: Driver, streaming: bool,
                 cancelled):
        self.project, self.model, self.root, self.rows = project, model, root, rows
        self.bundle = screens.bundle_of(root)
        self.driver, self.streaming, self.cancelled = driver, streaming, cancelled
        self.at: tuple[dict[str, Any], int] = ({"name": "", "who": "", "steps": []}, 0)      # the journey and step being walked
        self.model_tried = False

    # what the Studio shows live: only the journey that is on the screen
    def event(self, state: str, **fields: Any) -> None:
        if self.streaming:
            live.handle(self.project, {"kind": "event", "state": state, **fields})

    def walk(self, journey: dict[str, Any], out: Path) -> dict[str, Any]:
        out.mkdir(parents=True, exist_ok=True)
        steps = journey["steps"]
        title = f"[{journey['id']}] {journey['name']}"
        try:
            self.driver.reset()
        except DriverError as exc:      # the browser is gone: every step of this journey says so
            return {"id": journey["id"], "name": journey["name"], "who": journey["who"], "setup": None,
                    "steps": [{"id": s["id"], "step": s["step"], "route": s["route"], "expected": page_for(s["route"], self.rows),
                               "reached": False, "actions": [], "notes": [str(exc)], "visited": [], "shots": [], "page": "",
                               "errors": []} for s in steps]}
        self.event("journey_start", title=title, role=journey["who"], total=len(steps), index=0)
        setup = self._start(journey, out)
        walked = []
        for number, step in enumerate(steps, 1):
            if self.cancelled():
                raise RunCancelled(self.project)
            self.event("step", title=title, label=step["step"], verb="GOTO", route=step["route"], index=number - 1, total=len(steps))
            walked.append(self._step(journey, number, step, out))
            self.event("step_done", title=title, label=step["step"], index=number, total=len(steps), ok=walked[-1]["reached"])
        done = all(s["reached"] for s in walked) and (setup is None or setup["ok"])
        self.event("journey_done", title=title, ok=done, index=len(steps), total=len(steps),
                   message="" if done else "a step could not be done")
        return {"id": journey["id"], "name": journey["name"], "who": journey["who"], "setup": setup, "steps": walked}

    def _start(self, journey: dict[str, Any], out: Path) -> dict[str, Any] | None:
        """A journey starts where a visitor does: at the prototype's home page, not on a blank tab."""
        home = page_for("/", self.rows) or (str(self.rows[0].get("route")) if self.rows else "")
        try:
            if home:
                self.driver.goto(self.bundle, home)
            return None
        except DriverError as exc:
            return {"ok": False, "note": f"the browser could not open {home}: {exc}", "shot": ""}

    def _step(self, journey: dict[str, Any], number: int, step: dict[str, Any], out: Path) -> dict[str, Any]:
        target = page_for(step["route"], self.rows)
        self.at = (journey, number)
        self.model_tried = False
        notes: list[str] = []
        actions: list[str] = []
        visited: list[str] = []
        shots: list[str] = []
        sid = step["id"].rsplit("-", 1)[-1] or f"S{number:02d}"
        try:
            self._close_dialog()
            state = self.driver.state()
            visited.append(state.get("route", ""))
            if not target:
                notes.append(f"the prototype has no page for the route {step['route']}")
            elif not at_page(state.get("route", ""), target):
                self._reach(target, step, state, actions, visited, notes)
            reached = bool(target) and any(at_page(v, target) for v in visited)
            arrival = self.driver.screenshot(out / f"{sid}-a.jpg").name
            changed = False
            if reached and _DOING.search(step["step"]):
                changed = self._do(journey, number, step, actions, visited, notes)
            final = self.driver.screenshot(out / f"{sid}.jpg").name
            shots = [arrival, final] if changed else [final]
            if not changed:
                try:
                    (out / f"{sid}-a.jpg").unlink()
                except OSError:
                    pass
            now = self.driver.state()
            errors = self.driver.errors()
        except DriverError as exc:
            reached, errors, now = False, [], {"route": "", "title": ""}
            notes.append(str(exc))
        if target and not reached and not notes:
            notes.append(f"the browser never got to {target}")
        return {"id": step["id"], "step": step["step"], "route": step["route"], "expected": target, "reached": reached,
                "actions": actions, "notes": notes, "visited": [v for v in dict.fromkeys(visited) if v], "shots": shots,
                "page": now.get("title", ""), "errors": errors}

    def _reach(self, target: str, step: dict[str, Any], state: dict[str, Any], actions: list[str], visited: list[str],
               notes: list[str]) -> None:
        """Click the way to `target`: its link on this page, else the model reads the screen and finds the way, a few hops at most."""
        cleared = False
        for _hop in range(HOPS):
            current = state.get("route", "")
            if at_page(current, target):
                return
            elements = describe(self.driver.elements(), include_menus=True)
            link = self._best_link(elements, target, step)
            if link is None and not cleared:
                # A search or a filter that left nothing on the page: a person clears it and looks again.
                cleared = True
                if self._clear_filters(elements, actions):
                    state = self.driver.state()
                    continue
            if link is None:
                if self._model_gets_there(target, step, actions, visited, notes):
                    return
                notes.append(f"no link on {current or 'this page'} leads towards {target}")
                return
            if link.get("menu", -1) >= 0:
                # It is in a menu that is shut ("Your account"): a person opens the menu first, and then finds it.
                opener = next((e for e in elements if e["i"] == link["menu"]), {})
                self.event("step", title=step["step"], label=opener.get("text") or "menu", verb="CLICK", route=step["route"])
                self.driver.click(link["menu"])
                actions.append(f'opened "{opener.get("text") or "the menu"}"')
                wanted = link["route"]
                link = self._best_link(describe(self.driver.elements(), include_menus=True), wanted, step)
                if link is None or link.get("menu", -1) >= 0:
                    notes.append(f'the menu "{opener.get("text") or "menu"}" did not show a link to {wanted}')
                    return
            self.event("step", title=step["step"], label=link["text"] or link["route"], verb="CLICK", route=step["route"])
            answer = self.driver.click(link["i"])
            state = answer["state"]
            actions.append(f'clicked "{link["text"] or link["route"]}"')
            visited.append(state.get("route", ""))
            if not answer.get("navigated") and state.get("route", "") == current:
                if self._model_gets_there(target, step, actions, visited, notes):
                    return
                notes.append(f'clicking "{link["text"] or link["route"]}" did not open {link["route"]}')
                return
        if not at_page(state.get("route", ""), target):
            notes.append(f"{target} was not reached in {HOPS} clicks")

    @staticmethod
    def _best_link(elements: list[dict[str, Any]], target: str, step: dict[str, Any]) -> dict[str, Any] | None:
        """The link to `target` a person would use: one that is showing before one in a shut menu, the page's own content before
        the menus around it, and the one whose words are the step's."""
        order = {"main": 0, "nav": 1, "footer": 2, "dialog": 3}
        wanted = _words(step["step"])
        candidates = [e for e in elements if e.get("tag") == "a" and e.get("route") and at_page(e["route"], target)
                      and not e.get("disabled")]
        if not candidates:
            return None
        return min(candidates, key=lambda e: (e.get("menu", -1) >= 0, order.get(e.get("area"), 4),
                                               -len(wanted & _words(e.get("text", ""))), e["i"]))

    def _clear_filters(self, elements: list[dict[str, Any]], actions: list[str]) -> bool:
        """Press the page's own "clear" or "reset" control, when it has one showing."""
        for e in elements:
            if e.get("tag") in {"a", "button"} and not e.get("disabled") and e.get("menu", -1) < 0 \
                    and _CLEAR.search(f'{e.get("text", "")} {e.get("label", "")}'):
                self.driver.click(e["i"])
                actions.append(f'clicked "{e.get("text") or "clear"}"')
                return True
        return False

    def _do(self, journey: dict[str, Any], number: int, step: dict[str, Any], actions: list[str], visited: list[str],
            notes: list[str]) -> bool:
        """Do what the step says on its screen: the model reads what can be used and says what to fill and press. When what it
        pressed opened a menu or a dialog, it is asked again, with that open, because what it wanted next (a choice in the
        menu, the button that confirms the dialog) is in it."""
        changed = False
        for turn in range(TURNS):
            state = self.driver.state()
            elements = describe(self.driver.elements(), allow_sign_out=bool(re.search(r"\b(log|sign)\s?out\b", step["step"], re.I)))
            if not elements:
                return changed
            request = prompts.load(
                "prototype/journey-plan", journey=journey["name"], who=journey["who"] or "a visitor", number=number,
                total=len(journey["steps"]), step=step["step"], page=state.get("title") or state.get("route"),
                route=state.get("route"), heading=state.get("heading"),
                text=self.driver.text() or "(nothing)", elements="\n".join(_line(e) for e in elements), most=MAX_ACTIONS)
            try:
                plan = _within(PLAN_SECONDS, llm.complete_json, SYSTEM_PLAN, request, lambda data: check_plan(data, elements),
                               label="journey step", model=self.model, project=self.project, role=bus.DESIGNER)
            except RunCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - a step the model could not plan is shown as it is, never fails the walk
                notes.append(f"the model could not say what to do here: {str(exc)[:160]}")
                return changed
            by_index = {e["i"]: e for e in elements}
            opened_menu, left_page = False, False
            for action in plan:
                element = by_index[action["element"]]
                name = element.get("label") or element.get("text") or element.get("placeholder") or element.get("name") or element["tag"]
                try:
                    if action["do"] == "fill":
                        self.event("step", title=step["step"], label=name, verb="FILL", value=action["value"], route=step["route"])
                        self.driver.fill(element["i"], action["value"])
                        actions.append(f'filled "{name}" with "{action["value"]}"')
                        changed = True
                    else:
                        self.event("step", title=step["step"], label=name, verb="CLICK", route=step["route"])
                        answer = self.driver.click(element["i"])
                        actions.append(f'clicked "{name}"')
                        changed = True
                        visited.append(answer["state"].get("route", ""))
                        opened_menu = opened_menu or element["tag"] == "summary"
                        if answer.get("navigated"):
                            left_page = True
                            break          # the page changed: the numbers of the rest were of the page that is gone
                except DriverError as exc:
                    notes.append(f'could not use "{name}": {exc}')
                    return changed
            if left_page or not (opened_menu or self._dialog_open()):
                break
        return changed

    def _dialog_open(self) -> bool:
        return any(e.get("area") == "dialog" for e in self.driver.elements())

    def _close_dialog(self) -> None:
        """A dialog the step before left open lies over the page; a person closes it (Escape) before going on."""
        try:
            if self._dialog_open():
                self.driver.key("Escape")
        except DriverError:
            pass

    def _model_gets_there(self, target: str, step: dict[str, Any], actions: list[str], visited: list[str],
                          notes: list[str]) -> bool:
        """The way to `target` was not found by its links: the model, which can read what is on the screen, is asked to get there."""
        if self.model_tried:                    # once for a step: a model that cannot find the way twice will not the third time
            return False
        self.model_tried = True
        journey, number = self.at
        row = next((r for r in self.rows if str(r.get("route")) == target), {})
        goal = {"id": step["id"], "route": step["route"],
                "step": f'Get to the "{row.get("name") or target}" screen ({row.get("route") or target}) from this one, '
                        "the way a person would find it"}
        before = len(actions)
        self._do(journey, number, goal, actions, visited, notes)
        return any(at_page(v, target) for v in visited) and len(actions) > before


# --- looking at the pictures -----------------------------------------------------------------------------------------

def _clean_judgment(data: Any, ids: list[str]) -> dict[str, Any]:
    if not isinstance(data, dict) or not isinstance(data.get("steps"), list):
        raise ValueError('answer with one JSON object that has a "journey" and a "steps" list')
    journey = data.get("journey") if isinstance(data.get("journey"), dict) else {}
    found: dict[str, dict[str, Any]] = {}
    for row in data["steps"]:
        if isinstance(row, dict) and str(row.get("id") or "") in ids:
            cleaned = screen_review.clean({"defects": row.get("defects") or [], "looks_ok": True, "summary": row.get("summary")})
            found[str(row["id"])] = {"ok": bool(row.get("ok")), "summary": cleaned["summary"],
                                     "defects": [{**d, "viewport": "desktop"} for d in cleaned["defects"]][:5]}
    missing = [i for i in ids if i not in found]
    if missing:
        raise ValueError("every step needs an entry in \"steps\"; missing: " + ", ".join(missing))
    return {"completes": bool(journey.get("completes")), "summary": str(journey.get("summary") or "").strip()[:300], "steps": found}


def judge(project: str, model: str, root: Path, journey: dict[str, Any], walked: dict[str, Any]) -> dict[str, Any]:
    """A vision model looks at the pictures of one walked journey and says what each shows."""
    folder = root / JOURNEY_DIR / journey["id"]
    steps = walked["steps"]
    pictures: list[bytes] = []
    lines = []
    for number, step in enumerate(steps, 1):
        shots = [s for s in step["shots"] if (folder / s).is_file()]
        # Both pictures of a step (on arrival, and after what was done) while that is not too many for one review.
        keep = shots if len(steps) * 2 <= MAX_PICTURES else shots[-1:]
        first = len(pictures) + 1
        pictures += [(folder / s).read_bytes() for s in keep]
        shown = (f"picture {first}" if len(keep) == 1 else f"pictures {first} to {first + len(keep) - 1}") if keep else "no picture"
        did = "; ".join(step["actions"]) or "nothing needed doing"
        extra = " ".join(f"({n})" for n in step["notes"])
        lines.append(f"{number}. `{step['id']}` on {step['route']}: \"{step['step']}\" — {shown}. The browser: {did}. "
                     f"It ended on \"{step['page'] or 'a page'}\".{' Notes: ' + extra if extra else ''}"
                     + (f" Page errors: {'; '.join(step['errors'])}." if step["errors"] else ""))
    request = prompts.load("prototype/journey-review", who=journey["who"] or "A visitor", journey=journey["name"], id=journey["id"],
                           steps="\n".join(lines), pictures=f"{len(pictures)} picture{'s' if len(pictures) != 1 else ''} in all.")
    ids = [s["id"] for s in steps]
    return _within(JUDGE_SECONDS, llm.complete_json, SYSTEM, request, lambda data: _clean_judgment(data, ids),
                   label="journey review", model=model, images=pictures, project=project, role=bus.DESIGNER)


# --- what is wrong, and what is said about it ------------------------------------------------------------------------

def problems(journey: dict[str, Any], walked: dict[str, Any], judged: dict[str, Any] | None) -> list[dict[str, str]]:
    """Everything worth fixing in one walked journey: what could not be done, and what the pictures showed."""
    found: list[dict[str, str]] = []
    setup = walked.get("setup")
    if setup and not setup["ok"]:
        found.append({"step": "start", "severity": "high", "where": "the prototype's home page", "problem": setup["note"], "fix": ""})
    seen = (judged or {}).get("steps") or {}
    for step in walked["steps"]:
        if not step["reached"]:
            found.append({"step": step["id"], "severity": "high", "where": f"{step['route']} (step: {step['step']})",
                          "problem": "; ".join(step["notes"]) or "the step could not be done", "fix": ""})
        elif step["notes"] and step["actions"] == []:
            found.append({"step": step["id"], "severity": "medium", "where": step["route"], "problem": "; ".join(step["notes"]), "fix": ""})
        for error in step["errors"]:
            found.append({"step": step["id"], "severity": "medium", "where": step["page"] or step["route"],
                          "problem": f"the page reported an error in the browser: {error}", "fix": ""})
        verdict = seen.get(step["id"])
        if verdict:
            if not verdict["ok"] and step["reached"]:
                # The screen was reached; whether it shows the step's exact result is the model's opinion of a prototype that has no
                # server, so it is said (low) and never sent to be fixed. What is really wrong shows as a defect or a step not done.
                found.append({"step": step["id"], "severity": "low", "where": f"{step['route']} (step: {step['step']})",
                              "problem": f"the screenshot does not show the step done: {verdict['summary']}", "fix": ""})
            found += [{"step": step["id"], "severity": d["severity"], "where": d["where"], "problem": d["problem"], "fix": d["fix"]}
                      for d in verdict["defects"]]
    if judged and not judged["completes"] and not any(not s["reached"] for s in walked["steps"]):
        found.append({"step": "journey", "severity": "medium", "where": journey["name"],
                      "problem": f"the journey cannot be completed: {judged['summary']}", "fix": ""})
    return found


def _worth_fixing(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return [p for p in items if p["severity"] in screen_review.FIX_SEVERITIES]


def _tell(project: str, journey: dict[str, Any], walked: dict[str, Any], judged: dict[str, Any] | None,
          found: list[dict[str, str]]) -> None:
    """One journey's result, in the chat, under the pictures of its steps."""
    seen = (judged or {}).get("steps") or {}
    lines, thumbs = [], []
    for step in walked["steps"]:
        verdict = seen.get(step["id"])
        good = step["reached"] and (verdict["ok"] if verdict else True)
        name = step["id"].rsplit("-", 1)[-1]
        lines.append(f"- **{name} {'✓' if good else '✗'}** {step['step']}"
                     + (f" — {verdict['summary']}" if verdict and verdict["summary"] else "")
                     + (f" ({'; '.join(step['notes'])})" if step["notes"] else ""))
        for d in (verdict or {}).get("defects", []):
            lines.append(f"    - **{d['severity']}** · {d['where'] or 'screen'}: {d['problem']}")
        if step["shots"]:
            thumbs.append({"path": f"{config.RECORD_DIR}/prototype/{JOURNEY_DIR}/{journey['id']}/{step['shots'][-1]}",
                           "label": f"{name} · {step['page'] or step['expected'] or step['route']}"})
    worth = len(_worth_fixing(found))
    completes = all(s["reached"] for s in walked["steps"]) and (judged["completes"] if judged else True)
    head = (judged or {}).get("summary") or ("Every step could be done." if completes else "Not every step could be done.")
    state = "completes" if completes and not worth else f"{worth} to fix" if worth else "completes"
    bus.agent_msg(project, head + "\n\n" + "\n".join(lines), title=f"[{journey['id']}] {journey['name']} · {state}",
                  kind="visual_review", agent=bus.DESIGNER, images=thumbs)


def _fix_request(items: list[tuple[dict[str, Any], list[dict[str, str]]]]) -> tuple[str, int]:
    blocks, count = [], 0
    for journey, found in items:
        worth = _worth_fixing(found)
        if not worth:
            continue
        lines = [f"### `{journey['id']}` — {journey['name']} ({journey['who'] or 'visitor'})"]
        for n, p in enumerate(sorted(worth, key=lambda p: screen_review.ORDER[p["severity"]]), 1):
            lines.append(f"{n}. [{p['severity']} · {p['step']}] {p['where'] or 'the page'}: {p['problem']}"
                         + (f" Suggested: {p['fix']}" if p["fix"] else ""))
        count += len(worth)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)[:24000], count


# --- the whole test --------------------------------------------------------------------------------------------------

def can_walk(cancelled=None) -> tuple[bool, str]:
    """Whether there is a browser to click through the journeys in: (ok, why not)."""
    try:
        browser = screenshot.working_browser(cancelled=cancelled)
    except InterruptedError as exc:
        raise RunCancelled("prototype") from exc
    if not browser:
        return False, "no browser (Edge, Chrome or Chromium) could be used to click through the journeys"
    return True, ""


def run(project: str, session: Any, rows: list[dict[str, Any]], fix: bool = True, model: str = "",
        force: bool = False) -> dict[str, Any]:
    """Click through the prototype's journeys, look at the pictures, fix what is found (`fix`: false only looks and reports).
    `model` is the one this run chose, else the project's; `force` runs it even when the setting turns it off, because it was
    asked for. Always returns a result, never raises."""
    if not enabled() and not force:
        return {"status": "off"}
    try:
        ok, why = can_walk(cancelled=lambda: bool(session.cancelled))
        if not ok:
            bus.agent_msg(project, f"The journeys were not clicked through: {why}.", title="Journey test skipped",
                          kind="narration", agent=bus.DESIGNER)
            return {"status": "skipped", "reason": why}
        return _run(project, session, str(session.agent(model).model), rows, fix)
    except RunCancelled:
        live.finish(project)
        raise
    except Exception as exc:  # noqa: BLE001 - a test is never a reason to fail the prototype
        live.finish(project)
        bus.phase(project, PHASE, "Clicking through the journeys", status="failed", detail=str(exc)[:300], agent=bus.DESIGNER)
        bus.log(project, "WARN", f"The journey test stopped: {str(exc)[:300]}", agent=bus.DESIGNER)
        return {"status": "failed", "reason": str(exc)[:300]}


def _walk_all(project: str, session: Any, model: str, sees: bool, root: Path, rows: list[dict[str, Any]],
              todo: list[dict[str, Any]], label: str) -> list[dict[str, Any]]:
    """Walk `todo`, `lanes` browsers at a time (one when someone is watching, so every journey is seen), and have each walked
    journey looked at while the next is walked. Returns, per journey: the journey, what was walked, what was judged, the problems."""
    watching = bus.viewers() > 0
    lanes = 1 if watching else min(LANES, max(1, len(todo)))
    uploads = root / "app" / "src" / "assets" / "uploads"
    sample = next((str(p) for p in sorted(uploads.glob("*")) if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}), "") \
        if uploads.is_dir() else ""
    jobs: queue.Queue = queue.Queue()
    for journey in todo:
        jobs.put(journey)
    results: list[dict[str, Any]] = []
    lock = threading.Lock()
    failures: list[BaseException] = []
    stop = llm._stop_event()  # noqa: SLF001 - Stop of this run: the lanes and the looking at pictures must end with it
    judges = ThreadPoolExecutor(max_workers=2, initializer=llm.bind_stop, initargs=(stop,))

    def finished(journey: dict[str, Any], walked: dict[str, Any]) -> None:
        judged = None
        if sees and not session.cancelled:
            try:
                judged = judge(project, model, root, journey, walked)
            except RunCancelled:
                raise
            except Exception as exc:  # noqa: BLE001 - a journey the model failed on is still reported as walked
                walked["judge_error"] = str(exc)[:200]
        found = problems(journey, walked, judged)
        _tell(project, journey, walked, judged, found)
        with lock:
            results.append({"journey": journey, "walked": walked, "judged": judged, "problems": found})
            bus.progress(project, label, len(results) * 100 / len(todo), agent=bus.DESIGNER)

    pending = []

    def lane(number: int) -> None:
        llm.bind_stop(stop)
        driver = Driver(relay=(lambda body: live.handle(project, body)) if (watching and number == 0) else None,
                        live=watching and number == 0, pace=PACE_MS if (watching and number == 0) else 0, sample=sample,
                        cancelled=lambda: bool(session.cancelled))
        try:
            driver.start()
            walk = Walk(project, model, root, rows, driver, streaming=watching and number == 0,
                        cancelled=lambda: bool(session.cancelled))
            while True:
                try:
                    journey = jobs.get_nowait()
                except queue.Empty:
                    return
                walked = walk.walk(journey, root / JOURNEY_DIR / journey["id"])
                with lock:
                    pending.append(judges.submit(finished, journey, walked))
        except BaseException as exc:  # noqa: BLE001 - handed to the thread that waits, so one lane's trouble is not lost
            failures.append(exc)
        finally:
            driver.close()

    threads = [threading.Thread(target=lane, args=(n,), daemon=True, name=f"journey-lane-{n}") for n in range(lanes)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    for future in list(pending):
        try:
            future.result()
        except RunCancelled:
            failures.append(RunCancelled(project))
        except Exception as exc:  # noqa: BLE001
            failures.append(exc)
    judges.shutdown(wait=True)
    live.finish(project)
    cancelled = next((f for f in failures if isinstance(f, RunCancelled)), None)
    if cancelled or session.cancelled:
        raise RunCancelled(project)
    if failures and not results:
        raise failures[0]
    results.sort(key=lambda r: [j["id"] for j in todo].index(r["journey"]["id"]))
    return results


def _run(project: str, session: Any, model: str, rows: list[dict[str, Any]], fix: bool) -> dict[str, Any]:
    root = session.record / "prototype"
    journeys = load_journeys(session.record)
    if not journeys:
        bus.agent_msg(project, "There are no journeys in the specification to click through.", title="Journey test",
                      kind="narration", agent=bus.DESIGNER)
        return {"status": "skipped", "reason": "no journeys"}
    sees, why = screen_review.can_review(model)
    bus.phase(project, PHASE, "Clicking through the journeys",
              detail=f"{len(journeys)} journey{'s' if len(journeys) != 1 else ''}, a picture at every step.", agent=bus.DESIGNER)
    bus.agent_msg(project, f"Clicking through {len(journeys)} journey{'s' if len(journeys) != 1 else ''} of the prototype in a real browser, "
                           + (f"taking a screenshot at every step for {model} to look at." if sees else
                              f"taking a screenshot at every step. {model} cannot look at pictures, so only whether each step could be "
                              f"done is checked ({why})."),
                  title="Journey test", kind="narration", agent=bus.DESIGNER)
    first = _walk_all(project, session, model, sees, root, rows, journeys, "Clicking through the journeys")

    final = {r["journey"]["id"]: r for r in first}
    fixed: list[str] = []
    stopped = ""
    request, count = _fix_request([(r["journey"], r["problems"]) for r in first])
    if count and fix:
        if session.cancelled:
            raise RunCancelled(project)
        bus.agent_msg(project, f"{count} problem{'s' if count != 1 else ''} worth fixing found in "
                               f"{sum(1 for r in first if _worth_fixing(r['problems']))} journey(s). Fixing them in the prototype app.",
                      title="Journey test", kind="narration", agent=bus.DESIGNER)
        app = root / "app"
        before = web_app.fingerprint(app)
        stopped = screen_review.run_fix(
            project, session, prompts.load("prototype/journey-fix", defects=request, skill=web_app.stage_skill(project),
                                           app=app.relative_to(session.workspace).as_posix()),
            model, bus.DESIGNER, "Journey test")
        changed = web_app.fingerprint(app) != before
        if changed:
            web_app.ensure_built(session, project, "prototype", agent=bus.DESIGNER)
            bus.prototype_changed(project)
        again = [r["journey"] for r in first if _worth_fixing(r["problems"])] if changed else []
        fixed = [j["id"] for j in again]
        if again:
            bus.agent_msg(project, f"Clicking through the {len(again)} journey{'s' if len(again) != 1 else ''} that had problems again.",
                          title="Journey test", kind="narration", agent=bus.DESIGNER)
            for r in _walk_all(project, session, model, sees, root, rows, again, "Clicking through them again"):
                final[r["journey"]["id"]] = r
    bus.progress(project, "Clicking through the journeys", 100, agent=bus.DESIGNER)

    remaining = [{"journey": jid, **p} for jid, r in final.items() for p in _worth_fixing(r["problems"])]
    completing = [jid for jid, r in final.items()
                  if all(s["reached"] for s in r["walked"]["steps"]) and (r["judged"]["completes"] if r["judged"] else True)]
    found = sum(len(r["problems"]) for r in first)
    report = {"model": model, "pictures_looked_at": bool(sees), "journeys": len(journeys), "completing": len(completing),
              "problems_found": found, "fixed_journeys": fixed, "fix_stopped": stopped, "remaining": remaining,
              "results": [{"id": jid, "name": r["journey"]["name"], "who": r["journey"]["who"],
                           "completes": jid in completing, "summary": (r["judged"] or {}).get("summary", ""),
                           "setup": r["walked"].get("setup"), "judge_error": r["walked"].get("judge_error", ""),
                           "steps": [{**s, "verdict": ((r["judged"] or {}).get("steps") or {}).get(s["id"])} for s in r["walked"]["steps"]]}
                          for jid, r in final.items()]}
    try:
        (root / JOURNEY_DIR).mkdir(parents=True, exist_ok=True)
        (root / JOURNEY_DIR / REPORT).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    summary = (f"Clicked through {len(journeys)} journey{'s' if len(journeys) != 1 else ''}: {len(completing)} can be completed. "
               + ("No problems found." if not found else
                  f"{found} problem{'s' if found != 1 else ''} found; nothing was changed, this was a test only." if not fix else
                  f"{found} problem{'s' if found != 1 else ''} found"
                  + (f", {len(fixed)} journey{'s' if len(fixed) != 1 else ''} changed to fix them" if fixed else "")
                  + (f"; {len(remaining)} still there after the fix." if remaining else "; none left that matters.")))
    if stopped:
        summary += f" The fix stopped before it was finished ({stopped})."
    bus.agent_msg(project, summary, title="Journey test", kind="narration", agent=bus.DESIGNER)
    bus.phase(project, PHASE, "Clicking through the journeys", status="complete", agent=bus.DESIGNER)
    return {"status": "done", **{k: v for k, v in report.items() if k != "results"}}
