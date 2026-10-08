"""The wireframe stage: one agent run that builds a low-fidelity React app, and the screen list the studio reads."""
from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent", ".deps"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import bus, config, prompts, web_app  # noqa: E402
from server_modules.session import RunCancelled  # noqa: E402
from srs_agent import document, wireframe  # noqa: E402
from support import forget_project, isolate_workspaces  # noqa: E402

PROJECT = "prj_wire"
DOC = {
    "app_summary": {"app_name": "Bakery"},
    "public_pages": [{"page_name": "Home", "route": "/", "sections": ["hero", "cake list"], "functions": ["browse cakes"]}],
    "protected_pages": [{"page_name": "Orders", "route": "/orders", "login_required": True, "allowed_roles": ["Owner"],
                         "sections": ["order table"], "functions": ["mark an order ready"]}],
    "business_workflows": [{"workflow_name": "Ordering a cake", "who": "Visitor",
                            "steps": ["open Home", "see the orders"]}],
}


def setUpModule():
    isolate_workspaces()


class FakeSession:
    cancelled = False

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.stage = "idle"
        self.saved: dict = {}
        self.tasks: list[str] = []
        self.direct: list[str] = []
        self.on_task = lambda: None
        self.failed = ""

    def begin(self, stage, role=""):
        self.stage = stage

    def finish(self, text=""):
        self.stage = "idle"

    def fail(self, text):
        self.stage, self.failed = "idle", text

    def save_context(self):
        pass

    def read_record(self, *parts, fallback=None):
        return self.saved.get(parts, fallback)

    def write_record(self, *parts, data):
        self.saved[parts] = data
        return self.record.joinpath(*parts)

    def run_task(self, request, **_kwargs):
        self.tasks.append(request)
        self.on_task()
        return {"status": "complete", "text": ""}

    def run_direct(self, request, model=""):
        self.direct.append(request)
        return {"status": "complete", "text": ""}


class WireframeTests(unittest.TestCase):
    def setUp(self):
        forget_project(PROJECT)
        self.workspace = config.workspace_for(PROJECT)
        (self.workspace / ".agentforge" / "srs" / "handoff").mkdir(parents=True, exist_ok=True)
        (self.workspace / ".agentforge" / "srs" / "handoff" / "app.md").write_text("# Bakery", encoding="utf-8")
        self.session = FakeSession(self.workspace)
        self.app = web_app.app_dir(PROJECT, "wireframe")
        web_app.remove_app(self.app)
        shutil.rmtree(self.workspace / ".agentforge" / "skills", ignore_errors=True)
        self.built: list[str] = []

        def build(session, project, kind, agent=""):
            self.built.append(kind)
            self.app.mkdir(parents=True, exist_ok=True)
            (self.app / "bundle.html").write_text("<html>built</html>", encoding="utf-8")

        patches = [
            patch.object(wireframe, "session_for", return_value=self.session),
            patch.object(document, "session_for", return_value=self.session),
            patch.object(document, "document", return_value={"srs_document": DOC}),
            patch.object(document.plan_stage, "approved_plan", return_value={}),
            patch.object(web_app, "runtime_ready", return_value=True),
            patch.object(web_app, "prepare_runtime", return_value=(True, "ready")),
            patch.object(web_app, "ensure_built", side_effect=build),
        ]
        for name in ("phase", "agent_msg", "log", "sync_state", "wireframe_changed", "user_msg"):
            patches.append(patch.object(bus, name))
        self.bus = {}
        for item in patches:
            started = item.start()
            self.addCleanup(item.stop)
            if getattr(item, "attribute", "") in ("sync_state", "agent_msg", "wireframe_changed"):
                self.bus[item.attribute] = started

    def draw_app(self):
        """What the agent leaves behind when it has made the app."""
        (self.app / "src").mkdir(parents=True, exist_ok=True)
        (self.app / "index.html").write_text("<div id=root></div>", encoding="utf-8")
        (self.app / "src" / "App.tsx").write_text("export default () => null", encoding="utf-8")

    # --- what the agent is asked ----------------------------------------------------------------

    def test_the_agent_gets_the_short_request_the_skill_the_screens_and_the_journeys(self):
        wireframe.generate(PROJECT)

        request = self.session.tasks[0]
        self.assertTrue(request.startswith("Generate a low-fidelity prototype."))
        self.assertIn(".agentforge/skills/web-artifacts-builder/SKILL.md", request)
        self.assertIn("node .agentforge/skills/web-artifacts-builder/scripts/init-artifact.mjs .agentforge/wireframe/app", request)
        self.assertIn(".agentforge/srs/handoff/app.md", request)
        self.assertIn(".agentforge/srs/handoff/sitemap.md", request)
        self.assertIn("- `/` — Home — sections: hero, cake list; functions: browse cakes", request)
        self.assertIn("- `/orders` — Orders", request)
        self.assertIn("Ordering a cake", request)
        self.assertIn("open Home", request)
        self.assertIn("see the orders", request)
        self.assertIn("No database, seed data, accounts or sign-in logic", request)
        self.assertNotIn("{{", request, "every placeholder was filled")
        self.assertEqual(self.built, ["wireframe"])
        self.assertTrue((self.workspace / ".agentforge" / "skills" / "web-artifacts-builder" / "SKILL.md").is_file())

    def test_the_prompt_holds_no_style_rules_of_its_own(self):
        raw = (config.PROMPTS / "wireframe" / "generate.md").read_text(encoding="utf-8")
        self.assertEqual(raw.splitlines()[0], "{{request}}")
        for rule in ("black-and-white", "HTML", "grid", "popup", "pixel", "monochrome"):
            self.assertNotIn(rule, raw, f"the prompt must not dictate: {rule}")
        self.assertLess(len(raw.splitlines()), 25, "the wireframe prompt stays short")
        self.assertEqual(document.WIREFRAME_APPROVAL_PROMPT, "Generate a low-fidelity prototype.")

    def test_a_customers_own_words_replace_the_default_request(self):
        wireframe.generate(PROJECT, "Generate a low-fidelity prototype. Keep the menu on the left.")
        self.assertTrue(self.session.tasks[0].startswith("Generate a low-fidelity prototype. Keep the menu on the left."))

    def test_a_fresh_run_starts_the_app_over_and_a_stopped_one_is_carried_on(self):
        self.draw_app()
        (self.app / "src" / "Old.tsx").write_text("old", encoding="utf-8")

        wireframe.generate(PROJECT)                      # fresh: whatever was there goes
        self.assertFalse((self.app / "src" / "Old.tsx").exists())
        self.assertNotIn("carry on with it", self.session.tasks[0])

        self.draw_app()
        (self.app / "src" / "Kept.tsx").write_text("kept", encoding="utf-8")
        wireframe.generate(PROJECT, fresh=False)         # a run that stopped half way
        self.assertTrue((self.app / "src" / "Kept.tsx").exists())
        self.assertIn("carry on with it", self.session.tasks[1])

    def test_nothing_is_asked_without_screens_or_the_handoff(self):
        with patch.object(document, "screens", return_value=[]):
            with self.assertRaises(ValueError):
                wireframe.generate(PROJECT)
        (self.workspace / ".agentforge" / "srs" / "handoff" / "app.md").unlink()
        with self.assertRaises(ValueError):
            wireframe.generate(PROJECT)
        self.assertEqual(self.session.tasks, [])

    def test_the_toolkit_is_prepared_once_and_a_failure_to_install_it_is_said(self):
        with patch.object(web_app, "runtime_ready", return_value=False), \
             patch.object(web_app, "prepare_runtime", return_value=(False, "npm could not be reached")):
            with self.assertRaises(RuntimeError) as raised:
                wireframe.generate(PROJECT)
        self.assertIn("npm could not be reached", str(raised.exception))
        self.assertEqual(self.session.tasks, [])
        self.assertTrue(any(call.kwargs.get("title") == "Wireframe toolkit"
                            for call in self.bus["agent_msg"].call_args_list))

    # --- the run, and what the studio reads --------------------------------------------------------

    def test_a_whole_run_reports_how_many_pages_are_ready_and_tells_the_preview_to_reload(self):
        self.session.on_task = self.draw_app

        done = wireframe.run(PROJECT)

        self.assertEqual(done, {"ok": True, "project": PROJECT, "ready": 2, "total": 2})
        self.assertEqual(self.session.stage, "idle")
        self.bus["wireframe_changed"].assert_called_with(PROJECT)
        states = [call.args[1] for call in self.bus["sync_state"].call_args_list]
        self.assertEqual(states, ["running", "clean"])

    def test_the_cards_follow_the_one_app_and_carry_the_last_error_until_it_is_built(self):
        grid = document.wireframes(PROJECT)
        self.assertEqual([p["route"] for p in grid["pages"]], ["/", "/orders"])
        self.assertEqual([p["has_html"] for p in grid["pages"]], [False, False])
        self.assertFalse(grid["app"]["built"])
        self.assertEqual(grid["journeys"][0]["workflow_name"], "Ordering a cake")

        self.session.saved[("wireframe", "state.json")] = {"error": "the bundle did not build"}
        self.assertEqual(document.wireframes(PROJECT)["pages"][0]["error"], "the bundle did not build")

        self.draw_app()
        (self.app / "bundle.html").write_text("<html>built</html>", encoding="utf-8")
        built = document.wireframes(PROJECT)
        self.assertEqual([p["has_html"] for p in built["pages"]], [True, True])
        self.assertEqual({p["error"] for p in built["pages"]}, {""}, "a built app shows no old error")
        self.assertTrue(built["app"]["built"])
        self.assertTrue(all(p["drawing"] is False for p in built["pages"]))

    def test_a_failed_build_is_remembered_for_the_cards_and_the_run_fails_loudly(self):
        self.session.on_task = self.draw_app
        with patch.object(web_app, "ensure_built", side_effect=web_app.BuildFailed("Failed to resolve './Nope'")):
            with self.assertRaises(web_app.BuildFailed):
                wireframe.run(PROJECT)
        self.assertEqual(self.session.saved[("wireframe", "state.json")], {"error": "Failed to resolve './Nope'"})
        self.assertIn("Failed to resolve", self.session.failed)
        self.assertEqual(self.bus["sync_state"].call_args.args[1], "failed")

    def test_stopping_a_run_leaves_the_app_for_the_next_one_to_carry_on_with(self):
        self.session.on_task = lambda: (self.draw_app(), setattr(self.session, "cancelled", True))
        with self.assertRaises(RunCancelled):
            wireframe.run(PROJECT)
        self.assertTrue((self.app / "index.html").is_file())
        self.assertEqual(self.bus["sync_state"].call_args.args[1], "paused")

    def test_approving_the_specification_builds_the_app_and_moves_on_to_design(self):
        self.session.on_task = self.draw_app
        with patch.object(document, "has_document", return_value=True), \
             patch.object(document.store, "update") as update, \
             patch.object(document.store, "advance") as advance:
            done = document.approve(PROJECT, "")

        self.assertTrue(done["ok"])
        update.assert_called_with(PROJECT, status="approved")
        advance.assert_called_with(PROJECT, "design")
        self.assertTrue(self.session.tasks[0].startswith("Generate a low-fidelity prototype."))

    def test_a_second_approval_cannot_start_while_the_wireframe_is_being_built(self):
        self.session.stage = "wireframes"
        with patch.object(document, "has_document", return_value=True):
            with self.assertRaises(ValueError):
                document.approve(PROJECT, "")
        self.assertEqual(self.session.tasks, [])

    # --- changing it ------------------------------------------------------------------------------

    def test_a_change_is_one_direct_turn_about_the_page_and_the_picked_element_then_a_rebuild(self):
        self.draw_app()

        done = wireframe.edit(PROJECT, "  make the   header sticky ", route="/orders",
                              element='<header class="top">Menu</header>')

        self.assertEqual(done, {"ok": True, "route": "/orders"})
        request = self.session.direct[0]
        self.assertTrue(request.startswith("make the header sticky"))
        self.assertIn("The change is on the page for `/orders`.", request)
        self.assertIn('<header class="top">Menu</header>', request)
        self.assertIn("replace_text", request)
        self.assertEqual(self.built, ["wireframe"])
        self.bus["wireframe_changed"].assert_called_with(PROJECT)

    def test_a_change_needs_words_a_wireframe_and_a_quiet_moment(self):
        with self.assertRaises(ValueError):
            wireframe.edit(PROJECT, "   ")
        with self.assertRaises(ValueError):
            wireframe.edit(PROJECT, "x" * 4001)
        with self.assertRaises(FileNotFoundError):
            wireframe.edit(PROJECT, "make it blue")
        self.draw_app()
        self.session.stage = "wireframes"
        with self.assertRaises(ValueError):
            wireframe.edit(PROJECT, "make it blue")
        self.assertEqual(self.session.direct, [])


class BuildFixPromptTests(unittest.TestCase):
    def test_the_fix_prompt_carries_the_build_output_and_forbids_installing(self):
        text = prompts.load("shared/build-fix", app=".agentforge/wireframe/app", log="Failed to resolve './Nope'")
        self.assertIn(".agentforge/wireframe/app", text)
        self.assertIn("Failed to resolve './Nope'", text)
        self.assertIn("Do not install packages", text)


if __name__ == "__main__":
    unittest.main()
