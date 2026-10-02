"""A diagram is always a diagram, and it is drawn legibly.

Found live in a hotel project's SRS: the sequence diagram was the model's own narration ("Let me read the Booking module
requirements…") saved as its source - `llm.complete` hands back the model's reasoning when its answer is empty - the
component diagram's `<<component>>` stereotypes drew as a bare "<>" (flowchart labels are HTML), the state and ER
diagrams had their last letters cut off (a model-written font made the labels be measured in one font and painted in
another), and edge labels were stacked on top of each other.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent", "tests"):
    sys.path.insert(0, str(ROOT / folder))

import support  # noqa: E402
from server_modules import llm, mermaid  # noqa: E402
from srs_agent import diagram_fallback, document  # noqa: E402

NARRATION = ("Let me read the Booking module requirements — lines 2270-2470 (FR-042 to FR-058). "
             "Also the Room Catalogue and Availability module. Let me read 2270-2470.")
GOOD_SEQUENCE = "sequenceDiagram\n  actor G as Guest\n  participant S as Hotel\n  G->>S: book a room\n  S-->>G: reference\n"
PARSE_FAILURE = "Error: Parse error on line 2: Expecting 'SEMI', 'NEWLINE', got 'EOF'"
DOC = {
    "app_summary": {"app_name": "Hotel Booking"},
    "business_workflows": [{"workflow_name": "Booking a room", "who": "Guest",
                            "steps": ["Guest picks dates", "Guest picks a room", "Guest confirms the booking"]}],
    "database_design": {
        "tables": [{"table_name": "guests", "fields": [{"name": "id", "type": "uuid", "primary_key": True},
                                                      {"name": "email", "type": "text"}]},
                   {"table_name": "bookings", "fields": [{"name": "id", "type": "uuid", "primary_key": True},
                                                        {"name": "guest_id", "type": "uuid",
                                                         "references": "guests.id"}]}],
        "relationships": [{"from": "bookings.guest_id", "to": "guests.id", "type": "many_to_one",
                           "description": "a guest makes bookings"}],
    },
}


def setUpModule():
    support.isolate_workspaces()


class ThinkingIsNotAnAnswerTests(unittest.TestCase):
    def reply(self, content, thinking, **kwargs):
        message = SimpleNamespace(content=content, thinking=thinking)
        with mock.patch.object(llm, "client"), mock.patch.object(llm, "_model", return_value="m"), \
             mock.patch.object(llm, "_context_for", return_value=0), \
             mock.patch.object(llm, "_tools_for", return_value=None), \
             mock.patch.object(llm, "_focused_usage", return_value=None), \
             mock.patch("server_modules.llm_tools.run_chat", return_value=message), \
             mock.patch("server_modules.llm_tools.tag_effort"):
            return llm.complete("system", "user", **kwargs)

    def test_a_reasoning_model_with_no_content_still_answers_in_its_thinking_by_default(self):
        self.assertEqual(self.reply("", " the answer "), "the answer")

    def test_an_answer_that_must_be_the_thing_asked_for_never_takes_the_reasoning(self):
        self.assertEqual(self.reply("", NARRATION, thinking_fallback=False), "")

    def test_content_is_the_answer_either_way(self):
        self.assertEqual(self.reply("flowchart LR", NARRATION, thinking_fallback=False), "flowchart LR")
        self.assertEqual(self.reply("flowchart LR", NARRATION), "flowchart LR")


class DeclarationTests(unittest.TestCase):
    def test_the_models_narration_is_not_a_diagram(self):
        for kind in mermaid.OPENERS:
            self.assertFalse(mermaid.has_diagram(kind, NARRATION), kind)
        self.assertEqual(mermaid.clean(NARRATION), NARRATION)
        self.assertFalse(mermaid.has_diagram("sequence", ""))

    def test_prose_before_or_around_a_diagram_is_cut_away(self):
        reply = "Here is the diagram:\n```mermaid\nsequenceDiagram\n  A->>B: hi\n```\nHope it helps"
        self.assertEqual(mermaid.clean(reply), "sequenceDiagram\n  A->>B: hi")
        self.assertTrue(mermaid.has_diagram("sequence", reply))
        self.assertEqual(mermaid.clean("Sure, here you go.\nflowchart LR\n  a --> b"), "flowchart LR\n  a --> b")

    def test_a_theme_line_before_the_declaration_is_kept_when_the_prose_is_cut(self):
        theme = '%%{init: {"themeVariables": {"primaryColor": "#F8B666"}}}%%'
        diagram = theme + "\nerDiagram\n  A ||--o{ B : has"
        self.assertEqual(mermaid.clean(diagram), diagram)
        self.assertEqual(mermaid.clean("Sure, here it is:\n" + diagram), diagram)

    def test_a_sentence_that_starts_like_a_declaration_is_still_prose(self):
        self.assertFalse(mermaid.has_diagram("activity", "graph of the booking flow is below"))
        self.assertFalse(mermaid.has_diagram("activity", "flowchart shows the steps\nin order"))

    def test_the_declaration_has_to_belong_to_the_kind(self):
        self.assertTrue(mermaid.has_diagram("component", "flowchart LR\n a --> b"))
        self.assertTrue(mermaid.has_diagram("state_machine", "stateDiagram-v2\n [*] --> A"))
        self.assertFalse(mermaid.has_diagram("sequence", "flowchart TD\n a --> b"))
        self.assertTrue(mermaid.has_diagram("state_machine", '%%{init: {"theme": "base"}}%%\nstateDiagram-v2\n [*] --> A'))

    def test_not_applicable_still_comes_through_clean(self):
        self.assertEqual(mermaid.clean("NOT_APPLICABLE: no lifecycle field"), "NOT_APPLICABLE: no lifecycle field")
        self.assertFalse(mermaid.has_diagram("state_machine", "NOT_APPLICABLE: no lifecycle field"))

    def test_a_retry_names_the_declaration_the_kind_needs(self):
        self.assertEqual(mermaid.declaration_for("sequence"), "sequenceDiagram")
        self.assertIn("flowchart", mermaid.declaration_for("component"))


class PrepareTests(unittest.TestCase):
    def test_a_flowchart_stereotype_survives_html_labels(self):
        source = 'flowchart LR\n  a["<<component>>\\nGuest"] -.->|"<<deploy>>"| b\n'
        prepared = mermaid.prepare(source)
        self.assertIn("«component»", prepared)
        self.assertIn("«deploy»", prepared)
        self.assertNotIn("<<", prepared)

    def test_class_and_state_stereotypes_keep_their_own_syntax(self):
        for source in ("classDiagram\n  class S {\n    <<enumeration>>\n    A\n  }",
                       "stateDiagram-v2\n  state choose <<choice>>\n  [*] --> choose"):
            self.assertEqual(mermaid.prepare(source), source)

    def test_the_models_font_is_dropped_but_its_colours_stay(self):
        source = ('%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#F8B666", '
                  '"fontFamily": "Helvetica, Arial, sans-serif", "fontSize": "20px"}}}%%\nerDiagram\n  A ||--o{ B : has')
        prepared = mermaid.prepare(source)
        self.assertIn("#F8B666", prepared)
        self.assertNotIn("fontFamily", prepared)
        self.assertNotIn("Helvetica", prepared)
        self.assertNotIn("fontSize", prepared)
        self.assertTrue(prepared.rstrip().endswith("A ||--o{ B : has"))

    def test_single_quoted_json_is_read_like_mermaid_reads_it(self):
        prepared = mermaid.prepare("%%{init: {'themeVariables': {'primaryColor': '#75C5E8', 'fontFamily': 'X'}}}%%\nflowchart LR\n a-->b")
        self.assertIn("#75C5E8", prepared)
        self.assertNotIn("fontFamily", prepared)

    def test_a_theme_line_with_nothing_but_a_font_disappears_and_broken_json_does_too(self):
        self.assertEqual(mermaid.prepare('%%{init: {"themeVariables": {"fontFamily": "X"}}}%%\nflowchart LR\n a-->b'),
                         "flowchart LR\n a-->b")
        self.assertEqual(mermaid.prepare("%%{init: {broken}}%%\nflowchart LR\n a-->b"), "flowchart LR\n a-->b")

    def test_a_config_front_matter_is_dropped_and_a_plain_title_is_kept(self):
        self.assertEqual(mermaid.prepare("---\nconfig:\n  theme: dark\n---\nflowchart LR\n a-->b"), "flowchart LR\n a-->b")
        self.assertTrue(mermaid.prepare("---\ntitle: Booking\n---\nflowchart LR\n a-->b").startswith("---\ntitle"))

    def test_a_plain_source_is_untouched(self):
        self.assertEqual(mermaid.prepare(GOOD_SEQUENCE), GOOD_SEQUENCE)

    def test_the_shared_font_is_named_where_text_is_measured_and_where_it_is_painted(self):
        config = mermaid._VISUAL_CONFIG  # noqa: SLF001
        self.assertEqual(config["fontFamily"], config["themeVariables"]["fontFamily"])


class RenderChoiceTests(unittest.TestCase):
    def render(self, kind, results, source="flowchart LR\n a-->b"):
        calls = []

        def once(cli, text, out, visual, timeout):
            calls.append((text, visual))
            return results[len(calls) - 1]

        with tempfile.TemporaryDirectory() as folder, \
             mock.patch.object(mermaid, "_find_cli", return_value=["cli"]), \
             mock.patch.object(mermaid, "_render_once", side_effect=once):
            done = mermaid.render(source, Path(folder) / "out.svg", kind=kind)
        return done, calls

    def test_a_graph_kind_is_laid_out_with_elk_first(self):
        done, calls = self.render("component", [(True, "")])
        self.assertEqual(done, (True, ""))
        self.assertEqual([visual.get("layout") for _, visual in calls], ["elk"])

    def test_if_elk_fails_the_diagram_is_drawn_again_with_the_default_layout(self):
        done, calls = self.render("component", [(False, "the renderer could not run: elk"), (True, "")])
        self.assertEqual(done, (True, ""))
        self.assertEqual([visual.get("layout") for _, visual in calls], ["elk", None])

    def test_a_source_mermaid_rejects_is_not_tried_twice(self):
        done, calls = self.render("component", [(False, PARSE_FAILURE)])
        self.assertEqual(done, (False, PARSE_FAILURE))
        self.assertEqual(len(calls), 1)

    def test_a_sequence_diagram_has_no_graph_layout_to_choose(self):
        _, calls = self.render("sequence", [(True, "")], GOOD_SEQUENCE)
        self.assertEqual([visual.get("layout") for _, visual in calls], [None])

    def test_every_graph_kind_but_not_the_sequence_uses_elk(self):
        graph_kinds = {kind for kind in mermaid.OPENERS if kind != "sequence"}
        self.assertEqual(set(mermaid._ELK_KINDS), graph_kinds)  # noqa: SLF001

    def test_the_renderer_is_given_the_prepared_source(self):
        _, calls = self.render("component", [(True, "")], 'flowchart LR\n a["<<component>>\\nX"]\n')
        self.assertIn("«component»", calls[0][0])


@unittest.skipUnless(mermaid.available(), "no Mermaid renderer on this machine")
class RealRenderTests(unittest.TestCase):
    def draw(self, kind, source):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out.svg"
            done, why = mermaid.render_diagram(kind, source, out)
            self.assertTrue(done, why)
            return out.read_text(encoding="utf-8")

    def test_a_component_stereotype_is_drawn_not_swallowed(self):
        svg = self.draw("component", 'flowchart LR\n  a["<<component>>\\nGuest Storefront"] --> b["<<component>>\\nCore"]\n')
        self.assertIn("«component»", svg)
        self.assertNotIn("&lt;&lt;component", svg)

    def test_a_model_written_font_no_longer_decides_the_font(self):
        source = ('%%{init: {"theme": "base", "themeVariables": {"primaryColor": "#F8B666", '
                  '"fontFamily": "Helvetica, Arial, sans-serif"}}}%%\nstateDiagram-v2\n  [*] --> Confirmed\n'
                  '  Confirmed --> CheckedOut : guest checked out\n  CheckedOut --> [*]\n')
        svg = self.draw("state_machine", source)
        self.assertIn("Arial,Helvetica,sans-serif", svg)
        self.assertNotIn('"Helvetica, Arial, sans-serif"', svg)
        self.assertIn("#f8b666", svg.lower())                      # the model's colours are still its own


class FallbackTests(unittest.TestCase):
    def test_a_sequence_is_the_workflows_own_steps(self):
        source = diagram_fallback.build("sequence", DOC)
        self.assertTrue(source.startswith("sequenceDiagram"))
        self.assertIn("actor U as Guest", source)
        self.assertIn("participant S as Hotel Booking", source)
        self.assertEqual(source.count("U->>S:"), 3)
        self.assertIn("Guest picks a room", source)

    def test_an_activity_flows_through_the_same_steps(self):
        source = diagram_fallback.build("activity", DOC)
        self.assertTrue(source.startswith("flowchart TD"))
        self.assertIn('a2("Guest picks a room") --> a3', source)
        self.assertTrue(source.rstrip().endswith("a3 --> finish((◉))"))

    def test_states_are_a_status_fields_own_values_in_order(self):
        context = {"lifecycle_candidates": [{"table": "bookings", "field": "status",
                                             "states": "enum(Confirmed, 'Checked In', CheckedOut)"}]}
        source = diagram_fallback.build("state_machine", context)
        self.assertTrue(source.startswith("stateDiagram-v2"))
        self.assertIn('state "Checked In" as s1_Checked_In', source)
        self.assertIn("[*] --> s0_Confirmed", source)
        self.assertIn("s2_CheckedOut --> [*]", source)

    def test_an_erd_is_the_tables_and_their_relationships(self):
        source = diagram_fallback.build("erd", {"database_design": DOC["database_design"]})
        self.assertTrue(source.startswith("erDiagram"))
        self.assertIn("GUESTS {", source)
        self.assertIn("uuid id PK", source)
        self.assertIn("uuid guest_id FK", source)
        self.assertIn('BOOKINGS }o--|| GUESTS : "a guest makes bookings"', source)

    def test_nothing_is_invented_when_the_specification_has_no_such_facts(self):
        for kind in ("sequence", "activity", "state_machine", "erd"):
            self.assertEqual(diagram_fallback.build(kind, {}), "", kind)
        self.assertEqual(diagram_fallback.build("sequence", {"business_workflows": [
            {"workflow_name": "One step only", "steps": ["just this"]}]}), "")
        self.assertEqual(diagram_fallback.build("state_machine", {"lifecycle_candidates": [
            {"states": "text"}]}), "")
        for kind in ("component", "deployment", "dfd", "bpmn", "system_context", "use_case", "class_object", "nope"):
            self.assertEqual(diagram_fallback.build(kind, DOC), "", kind)

    def test_characters_that_end_a_mermaid_label_early_are_left_out(self):
        context = {"business_workflows": [{"workflow_name": "W", "who": 'The "Guest"', "steps": [
            'Pick (a) room; then "book" #1', "Pay [now] and finish"]}]}
        source = diagram_fallback.build("sequence", context)
        for character in '"();#[]':
            self.assertNotIn(character, source.split("\n", 1)[1].replace("->>", ""), character)

    @unittest.skipUnless(mermaid.available(), "no Mermaid renderer on this machine")
    def test_every_fallback_really_renders(self):
        context = {**DOC, "lifecycle_candidates": [{"states": "enum(Booked, CheckedIn, CheckedOut)"}]}
        for kind in ("sequence", "activity", "state_machine", "erd"):
            source = diagram_fallback.build(kind, context)
            with tempfile.TemporaryDirectory() as folder:
                done, why = mermaid.render_diagram(kind, source, Path(folder) / "out.svg")
            self.assertTrue(done, f"{kind}: {why}\n{source}")


class DrawFixture(unittest.TestCase):
    def draw(self, kind, replies, doc=None, render=None):
        """Run `_draw_diagram` with the model's replies in order (the last repeats); returns the entry, the model calls
        and the text saved to the `.mmd` file (None when nothing was saved)."""
        calls: list[dict] = []

        def complete(**kwargs):
            calls.append(kwargs)
            return replies[min(len(calls), len(replies)) - 1]

        def drawn(_kind, source, out, timeout=180):
            out.write_text("<svg/>", encoding="utf-8")
            return True, ""

        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            session = mock.Mock(workspace=workspace)
            session.record_path.side_effect = lambda *parts: workspace / ".agentforge" / Path(*parts)
            (workspace / ".agentforge" / "srs" / "diagrams").mkdir(parents=True)
            with mock.patch.object(document.llm, "complete", side_effect=complete), \
                 mock.patch.object(document, "_diagram_reference", return_value=""), \
                 mock.patch.object(document.mermaid, "available", return_value=True), \
                 mock.patch.object(document.mermaid, "render_diagram", side_effect=render or drawn) as renderer:
                entry = document._draw_diagram(session, "prj_draw", doc or DOC, kind)  # noqa: SLF001
            mmd = workspace / ".agentforge" / "srs" / "diagrams" / f"{kind}.mmd"
            saved = mmd.read_text(encoding="utf-8") if mmd.is_file() else None
        self.renderer = renderer
        return entry, calls, saved


class NarrationIsNeverSavedTests(DrawFixture):
    def test_a_model_that_only_narrates_gets_its_diagram_drawn_from_the_specification(self):
        entry, calls, saved = self.draw("sequence", [NARRATION])
        self.assertEqual(len(calls), 3)
        self.assertTrue(entry["fallback"])
        self.assertTrue(saved.startswith("sequenceDiagram"))
        self.assertNotIn("Let me read", saved)
        self.assertEqual(entry["source"], saved)
        self.assertEqual(entry["svg"], "<svg/>")

    def test_the_first_ask_reads_the_specification_and_the_rest_cannot_narrate(self):
        _, calls, _ = self.draw("sequence", [NARRATION])
        first, second, third = calls
        self.assertIsNotNone(first["workspace"])
        self.assertIs(first["thinking_fallback"], False)
        for later in (second, third):
            self.assertIsNone(later["workspace"])                  # no read tool: nothing to narrate
            self.assertIs(later["think"], False)
            self.assertIs(later["thinking_fallback"], False)
            self.assertIn("Your last reply was not a usable diagram", later["user"])
            self.assertIn("Booking a room", later["user"])           # the specification slice is in the prompt
            self.assertIn("beginning “Let me read", later["user"])

    def test_a_good_diagram_on_the_second_ask_is_what_is_saved(self):
        entry, calls, saved = self.draw("sequence", [NARRATION, GOOD_SEQUENCE])
        self.assertEqual(len(calls), 2)
        self.assertEqual(saved.strip(), GOOD_SEQUENCE.strip())
        self.assertNotIn("fallback", entry)
        self.assertEqual(entry["format"], "svg+mermaid-source")

    def test_an_empty_reply_is_not_a_diagram_either(self):
        entry, calls, saved = self.draw("sequence", ["", GOOD_SEQUENCE])
        self.assertEqual(len(calls), 2)
        self.assertEqual(saved.strip(), GOOD_SEQUENCE.strip())

    def test_a_good_first_reply_is_asked_for_once_with_the_read_tool(self):
        entry, calls, saved = self.draw("sequence", [GOOD_SEQUENCE])
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(calls[0]["workspace"])
        self.assertEqual(entry["source"].strip(), GOOD_SEQUENCE.strip())

    def test_a_kind_with_nothing_to_draw_from_is_reported_not_faked_and_nothing_is_saved(self):
        entry, calls, saved = self.draw("component", [NARRATION])
        self.assertEqual(len(calls), 3)
        self.assertIsNone(saved)
        self.assertEqual(entry["source"], "")
        self.assertTrue(entry["applicable"])
        self.assertTrue(entry["drawing_failed"])
        self.assertIn("did not return a diagram", entry["render_error"])
        self.assertNotIn("svg", entry)

    def test_not_applicable_is_honoured_when_it_comes_on_a_retry(self):
        entry, calls, saved = self.draw("state_machine", [NARRATION, "NOT_APPLICABLE: no lifecycle field"])
        self.assertEqual(len(calls), 2)
        self.assertFalse(entry["applicable"])
        self.assertEqual(entry["applicability_note"], "no lifecycle field")
        self.assertIsNone(saved)

    def test_a_source_mermaid_keeps_rejecting_is_drawn_from_the_specification_when_it_can_be(self):
        outcomes = [(False, PARSE_FAILURE)] * 3 + [(True, "")]

        def render(_kind, source, out, timeout=180):
            done, why = outcomes.pop(0)
            if done:
                out.write_text("<svg/>", encoding="utf-8")
            return done, why

        entry, calls, saved = self.draw("sequence", ["sequenceDiagram\n  A->>"], render=render)
        self.assertEqual(len(calls), 3)
        self.assertEqual(self.renderer.call_count, 4)
        self.assertTrue(entry["fallback"])
        self.assertIn("U->>S: Guest picks dates", saved)

    def test_a_source_mermaid_keeps_rejecting_stays_the_models_when_there_is_nothing_to_draw_from(self):
        entry, calls, saved = self.draw("component", ["flowchart LR\n  a -->"],
                                        render=lambda *args, **kwargs: (False, PARSE_FAILURE))
        self.assertEqual(len(calls), 3)
        self.assertEqual(saved.strip(), "flowchart LR\n  a -->")
        self.assertNotIn("fallback", entry)
        self.assertNotIn("drawing_failed", entry)
        self.assertEqual(entry["render_error"], PARSE_FAILURE[:240])


class HealingTests(unittest.TestCase):
    def test_recovery_never_spends_a_render_on_words_that_are_not_a_diagram(self):
        envelope = {"srs_document": {"diagrams": [{"kind": "sequence", "source": NARRATION, "applicable": True}]}}
        with mock.patch.object(document.mermaid, "available", return_value=True), \
             mock.patch.object(document, "session_for"), \
             mock.patch.object(document.mermaid, "render_diagram") as render:
            self.assertFalse(document._recover_rendered_diagrams("prj_heal", envelope))  # noqa: SLF001
        render.assert_not_called()

    def redraw(self, entry, drawn_entry, deep=False):
        envelope = {"srs_document": {"diagrams": [entry]}}
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            session = mock.Mock(workspace=workspace)
            session.record_path.side_effect = lambda *parts: workspace / ".agentforge" / Path(*parts)
            with mock.patch.object(document.store, "require"), \
                 mock.patch.object(document, "document", return_value=envelope), \
                 mock.patch.object(document, "session_for", return_value=session), \
                 mock.patch.object(document, "_write_record_visible"), \
                 mock.patch.object(document.bus, "sync_state"), \
                 mock.patch.object(document, "_draw_diagram", return_value=drawn_entry) as drawn:
                result = document.redraw_diagrams("prj_heal", kinds=["sequence"], deep=deep)
        return result, drawn

    def test_a_saved_source_that_is_narration_is_drawn_afresh_not_rerendered(self):
        fresh = {"id": "DIA-sequence", "kind": "sequence", "source": GOOD_SEQUENCE, "applicable": True, "svg": "<svg/>"}
        result, drawn = self.redraw({"id": "DIA-sequence", "kind": "sequence", "source": NARRATION, "applicable": True},
                                    fresh)
        drawn.assert_called_once()
        self.assertEqual(result["diagrams"][0]["source"], GOOD_SEQUENCE)

    def test_a_diagram_that_was_never_drawn_is_drawn_afresh(self):
        fresh = {"id": "DIA-sequence", "kind": "sequence", "source": GOOD_SEQUENCE, "applicable": True, "svg": "<svg/>"}
        result, drawn = self.redraw({"id": "DIA-sequence", "kind": "sequence", "source": "", "applicable": True,
                                     "drawing_failed": True}, fresh)
        drawn.assert_called_once()
        self.assertEqual(result["diagrams"][0]["source"], GOOD_SEQUENCE)

    def test_refreshing_a_good_diagram_keeps_the_models_colours(self):
        source = ('%%{init: {"themeVariables": {"primaryColor": "#F8B666"}}}%%\n'
                  'erDiagram\n  A ||--o{ B : has\n')
        envelope = {"srs_document": {"diagrams": [{"id": "DIA-erd", "kind": "erd", "source": source,
                                                    "applicable": True}]}}
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder)
            session = mock.Mock(workspace=workspace)
            session.record_path.side_effect = lambda *parts: workspace / ".agentforge" / Path(*parts)
            diagrams = workspace / ".agentforge" / "srs" / "diagrams"
            diagrams.mkdir(parents=True)
            (diagrams / "erd.mmd").write_text(source, encoding="utf-8")

            def drawn(_kind, text, out, timeout=180):
                out.write_text("<svg/>", encoding="utf-8")
                return True, ""

            with mock.patch.object(document.store, "require"), \
                 mock.patch.object(document, "document", return_value=envelope), \
                 mock.patch.object(document, "session_for", return_value=session), \
                 mock.patch.object(document, "_write_record_visible"), \
                 mock.patch.object(document.bus, "sync_state"), \
                 mock.patch.object(document, "_draw_diagram") as redrawn, \
                 mock.patch.object(document.mermaid, "render_diagram", side_effect=drawn):
                result = document.redraw_diagrams("prj_heal", kinds=["erd"])
        redrawn.assert_not_called()                              # a good diagram is only re-rendered, no model call
        self.assertTrue(result["diagrams"][0]["source"].startswith("%%{init"))
        self.assertIn("#F8B666", result["diagrams"][0]["source"])

    def test_a_redraw_that_produced_nothing_never_replaces_a_diagram_that_was_drawn(self):
        old = {"id": "DIA-sequence", "kind": "sequence", "source": GOOD_SEQUENCE, "applicable": True, "svg": "<svg/>"}
        failed = {"id": "DIA-sequence", "kind": "sequence", "source": "", "applicable": True, "drawing_failed": True}
        result, _ = self.redraw(old, failed, deep=True)
        self.assertEqual(result["diagrams"][0]["source"], GOOD_SEQUENCE)
        self.assertEqual(result["diagrams"][0]["svg"], "<svg/>")


if __name__ == "__main__":
    unittest.main()
