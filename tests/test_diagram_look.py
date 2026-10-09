"""The specification's diagrams are photographed and looked at by a vision model, and what is wrong is fixed - two rounds at most."""
from __future__ import annotations

import inspect
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
from server_modules import bus, config, llm, mermaid, prompts  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402
from srs_agent import diagram_look, document  # noqa: E402

BEFORE = "flowchart LR\n  A[Customer] --> B[A very long label that runs out of its box]"
AFTER = "flowchart TD\n  A[Customer] --> B[Order form]"
EVEN_BETTER = "flowchart TD\n  A[Customer] --> B[Order]"


def entry(kind="system_context", source=BEFORE, svg="<svg><text>one</text></svg>"):
    return {"id": f"DIA-{kind}", "kind": kind, "title": kind.replace("_", " ").title(), "format": "svg+mermaid-source",
            "source": source, "svg": svg, "applicable": True}


def defect(severity="high", problem="The label of the second box runs out of its box."):
    return {"severity": severity, "where": "the Customer box", "problem": problem, "fix": "shorten it"}


def review(*defects):
    return {"page": "x", "looks_ok": not defects, "summary": "How it looks.", "defects": list(defects)}


class FakeSession:
    def __init__(self, folder: Path, model: str = "vision-model"):
        self.workspace = folder
        self.record = folder / ".agentforge"
        self.cancelled = False
        self.model = model

    def agent(self, model: str = ""):
        return SimpleNamespace(model=self.model)

    def record_path(self, *parts):
        if self.cancelled:
            raise RunCancelled("p")
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = FakeSession(Path(self.temp.name))
        self.messages: list[dict] = []
        self.files: list[tuple[str, str, str]] = []
        self.looked: list[tuple[str, int]] = []        # (kind, round) in the order the pictures were taken
        self.counts: dict[str, int] = {}
        self.pages: list[str] = []
        self.drawn: list[str] = []
        self.replies: dict[str, list] = {}            # kind -> the reviews the model gives, one per look
        self.corrections: list = []                   # what the model answers to each "draw it again"
        self.settings = {"diagram_visual_review": True}
        for patch in (
            mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                              self.messages.append({"text": text, "title": title, "kind": kind, "images": images or []})),
            mock.patch.object(bus, "phase", lambda *a, **k: None),
            mock.patch.object(bus, "progress", lambda *a, **k: None),
            mock.patch.object(bus, "log", lambda *a, **k: None),
            mock.patch.object(bus, "file_written", lambda project, name, content, old=None, note="", agent="":
                              self.files.append((name, content, note))),
            mock.patch.object(config, "setting", lambda name, fallback=None: self.settings.get(name, fallback)),
            mock.patch("server_modules.vision.supports", return_value=True),
            mock.patch.object(screenshot, "working_browser", return_value=("b", "chrome")),
            mock.patch.object(screenshot, "shoot", self.shoot),
            mock.patch.object(llm, "complete_json", self.complete_json),
            mock.patch.object(llm, "complete", self.complete),
            mock.patch.object(mermaid, "render_diagram", self.render),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    # --- the stand-ins ---
    def shoot(self, source, out, viewport="desktop", **_):
        page = Path(source).read_text(encoding="utf-8")
        self.pages.append(page)
        out.write_bytes(b"\x89PNG" + page.encode()[:200])
        return out

    def complete_json(self, system, user, validator=None, label="", model="", images=None, project="", role="", **_):
        kind = next(k for k in self.replies if f"a {k.replace('_', ' ')} diagram)" in user)
        number = self.counts[kind] = self.counts.get(kind, 0) + 1
        self.looked.append((kind, number))
        value = self.replies[kind]
        value = value[min(number, len(value)) - 1]
        if isinstance(value, Exception):
            raise value
        return validator(value)

    def complete(self, system="", user="", model="", images=None, **_):
        value = self.corrections.pop(0) if self.corrections else ""
        return value

    def render(self, kind, source, out, timeout=180):
        self.drawn.append(source)
        if "BROKEN" in source:
            return False, "Parse error on line 2"
        out.write_text(f"<svg><text>{source.splitlines()[-1]}</text></svg>", encoding="utf-8")
        return True, ""

    def go(self, rows, **kwargs):
        return diagram_look.run("prj_look", self.session, rows, **kwargs)

    def titles(self):
        return [m["title"] for m in self.messages]


class SkipTests(Harness):
    def test_a_model_that_cannot_look_at_pictures_skips_it_and_says_why(self):
        self.session.model = "plain-model"
        with mock.patch("server_modules.vision.supports", return_value=False):
            result = self.go([entry()])
        self.assertEqual(result["status"], "skipped")
        self.assertIn("cannot look at pictures", result["reason"])
        self.assertEqual(self.titles(), ["Diagram check skipped"])
        self.assertEqual(self.pages, [])

    def test_a_computer_with_no_browser_skips_it_too(self):
        with mock.patch.object(screenshot, "working_browser", return_value=None):
            result = self.go([entry()])
        self.assertEqual(result["status"], "skipped")
        self.assertIn("no browser", result["reason"])

    def test_the_setting_turns_it_off_unless_it_was_asked_for(self):
        self.settings["diagram_visual_review"] = False
        self.assertEqual(self.go([entry()]), {"status": "off"})
        self.replies = {"system_context": [review()]}
        self.assertEqual(self.go([entry()], force=True)["status"], "done")

    def test_a_diagram_that_was_not_drawn_is_not_photographed(self):
        rows = [entry(svg=""), {**entry("erd"), "applicable": False}]
        self.assertEqual(self.go(rows), {"status": "nothing"})
        self.assertEqual(self.pages, [])


class RoundTests(Harness):
    def test_a_diagram_that_looks_right_is_looked_at_once_and_left_alone(self):
        self.replies = {"system_context": [review()]}
        row = entry()
        result = self.go([row])
        self.assertEqual(result["status"], "done")
        self.assertEqual(self.looked, [("system_context", 1)])
        self.assertEqual(row["source"], BEFORE)
        self.assertEqual(self.drawn, [])
        self.assertIn("no problems found", self.messages[-1]["text"])
        picture = next(m for m in self.messages if m["images"])["images"][0]
        self.assertTrue((Path(self.temp.name) / picture["path"]).is_file())              # shown in the chat under its review

    def test_what_is_wrong_is_drawn_again_from_a_corrected_source_and_looked_at_once_more(self):
        self.replies = {"system_context": [review(defect()), review()]}
        self.corrections = [AFTER]
        row = entry()
        result = self.go([row])
        self.assertEqual(self.looked, [("system_context", 1), ("system_context", 2)])
        self.assertEqual(row["source"], AFTER)
        self.assertIn("Order form", row["svg"])
        self.assertEqual(result["redrawn"], ["system_context"])
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(result["remaining"], [])
        saved = Path(self.temp.name) / ".agentforge" / "srs" / "diagrams"
        self.assertEqual((saved / "system_context.mmd").read_text(encoding="utf-8"), AFTER)
        self.assertIn("Order form", (saved / "system_context.svg").read_text(encoding="utf-8"))
        self.assertEqual([note for _n, _c, note in self.files], ["redrawn"])
        self.assertIn("1 diagram drawn again", self.messages[-1]["text"])

    def test_it_is_two_rounds_at_most_even_when_the_second_look_still_finds_problems(self):
        self.replies = {"system_context": [review(defect()), review(defect(problem="A line still crosses a box."))]}
        self.corrections = [AFTER, EVEN_BETTER]
        row = entry()
        result = self.go([row])
        self.assertEqual(self.looked, [("system_context", 1), ("system_context", 2)])      # never a third look
        self.assertEqual(self.corrections, [EVEN_BETTER])                                  # never a second correction
        self.assertEqual(row["source"], AFTER)
        self.assertEqual(len(result["remaining"]), 1)
        self.assertIn("still visible after round 2", self.messages[-1]["text"])

    def test_a_diagram_that_came_out_worse_is_put_back_as_it_was(self):
        self.replies = {"system_context": [review(defect("medium")), review(defect("high"), defect("medium", "More."))]}
        self.corrections = [AFTER]
        row = entry()
        result = self.go([row])
        self.assertEqual(row["source"], BEFORE)
        self.assertIn("one", row["svg"])
        self.assertEqual(result["put_back"], ["system_context"])
        self.assertEqual([note for _n, _c, note in self.files], ["redrawn", "put back"])
        mmd = Path(self.temp.name) / ".agentforge" / "srs" / "diagrams" / "system_context.mmd"
        self.assertEqual(mmd.read_text(encoding="utf-8"), BEFORE)

    def test_a_correction_mermaid_cannot_draw_leaves_the_diagram_as_it_was_and_ends_the_check(self):
        self.replies = {"system_context": [review(defect())]}
        self.corrections = ["flowchart TD\n  BROKEN"]
        row = entry()
        result = self.go([row])
        self.assertEqual(row["source"], BEFORE)
        self.assertEqual(self.looked, [("system_context", 1)])
        self.assertEqual(result["redrawn"], [])
        self.assertTrue(any("stay as they were" in m["text"] for m in self.messages))

    def test_a_reply_that_is_not_a_diagram_or_is_the_same_source_changes_nothing(self):
        self.replies = {"system_context": [review(defect())], "erd": [review(defect())]}
        self.corrections = ["I could not improve this one.", mermaid.clean(BEFORE)]
        rows = [entry(), entry("erd", "erDiagram\n  A ||--o{ B : has")]
        result = self.go(rows)
        self.assertEqual(result["redrawn"], [])
        self.assertEqual([r["source"] for r in rows], [BEFORE, "erDiagram\n  A ||--o{ B : has"])

    def test_a_problem_that_is_only_polish_is_reported_but_not_fixed(self):
        self.replies = {"system_context": [review(defect("low", "The spacing is uneven."))]}
        result = self.go([entry()])
        self.assertEqual(self.corrections, [])
        self.assertEqual(result["redrawn"], [])
        self.assertEqual(result["problems_found"], 1)

    def test_a_review_only_run_changes_nothing(self):
        self.replies = {"system_context": [review(defect())]}
        self.corrections = [AFTER]
        row = entry()
        result = self.go([row], fix=False)
        self.assertEqual(row["source"], BEFORE)
        self.assertEqual(self.corrections, [AFTER])
        self.assertEqual(self.looked, [("system_context", 1)])
        self.assertIn("this was a review only", self.messages[-1]["text"])
        self.assertEqual(result["status"], "done")

    def test_only_the_diagrams_that_were_drawn_again_are_looked_at_in_round_two(self):
        self.replies = {"system_context": [review(defect()), review()], "erd": [review()], "sequence": [review()]}
        self.corrections = [AFTER]
        rows = [entry(), entry("erd", "erDiagram\n  A ||--o{ B : has"), entry("sequence", "sequenceDiagram\n  A->>B: hi")]
        self.go(rows)
        self.assertEqual(sorted(self.looked[:3]), [("erd", 1), ("sequence", 1), ("system_context", 1)])      # round 1 looks at all of them
        self.assertEqual(self.looked[3:], [("system_context", 2)])                                          # round 2 at the one drawn again


class SafetyTests(Harness):
    def test_one_diagram_the_model_fails_on_is_reported_and_the_others_are_still_reviewed(self):
        self.replies = {"system_context": [RuntimeError("the model service stopped")], "erd": [review()]}
        rows = [entry(), entry("erd", "erDiagram\n  A ||--o{ B : has")]
        result = self.go(rows)
        self.assertEqual(result["status"], "done")
        self.assertEqual(result["not_reviewed"], ["System Context"])
        self.assertIn("Could not be reviewed: System Context", self.messages[-1]["text"])

    def test_a_check_that_breaks_never_fails_the_specification(self):
        with mock.patch.object(diagram_look, "_review", side_effect=RuntimeError("boom")):
            result = self.go([entry()])
        self.assertEqual(result["status"], "failed")

    def test_stop_ends_the_check(self):
        self.replies = {"system_context": [review()]}
        self.session.cancelled = True
        with self.assertRaises(RunCancelled):
            self.go([entry()])

    def test_the_picture_is_the_diagram_on_a_white_page_that_measures_its_own_height(self):
        self.replies = {"system_context": [review()]}
        self.go([entry(svg="<svg id='mine'></svg>", source=BEFORE)])
        page = self.pages[0]
        self.assertIn("<svg id='mine'></svg>", page)
        self.assertIn(screenshot.HEIGHT_MARK, page)
        self.assertIn("background:#fff", page)


class WiringTests(unittest.TestCase):
    def test_the_prompts_are_filled_in_completely(self):
        look = prompts.load("srs/diagram-look", title="Erd", kind="erd", source="erDiagram")
        fix = prompts.load("srs/diagram-look-fix", kind="erd", source="erDiagram", defects="1. [high] x: y",
                           declaration="erDiagram")
        for text in (look, fix):
            self.assertNotIn("{{", text)
        self.assertIn("(a erd diagram)", look)
        self.assertIn("1. [high] x: y", fix)

    def test_drawing_the_diagrams_ends_with_the_check_and_the_deep_redraw_does_it_too(self):
        self.assertIn('diagram_look.run(project, session, doc["diagrams"])', inspect.getsource(document.generate))
        self.assertIn("diagram_look.run(project, session, doc[\"diagrams\"])", inspect.getsource(document.redraw_diagrams))

    def test_the_setting_is_on_by_default_and_the_rounds_are_capped_at_two(self):
        self.assertTrue(config.DEFAULTS["diagram_visual_review"])
        self.assertEqual(diagram_look.MAX_ROUNDS, 2)


if __name__ == "__main__":
    unittest.main()
