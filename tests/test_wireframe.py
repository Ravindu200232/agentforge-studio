"""The wireframes: a React app the project's agent builds with the web-artifacts-builder skill, from app.md."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent"):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import prompts, web_app  # noqa: E402
from srs_agent import document, wireframe  # noqa: E402

PROJECT = "prj_bakery"
PAGES = [
    {"route": "/", "page_name": "Home", "sections": ["hero"], "functions": ["browse cakes"]},
    {"route": "/orders/[id]", "page_name": "Order", "login_required": True, "allowed_roles": ["Owner"]},
    {"route": "/orders", "page_name": "Orders", "login_required": True, "allowed_roles": ["Owner"]},
]


class FakeSession:
    cancelled = False
    stage = "idle"

    def __init__(self, workspace: Path, agent=None):
        self.workspace = workspace
        self.record = workspace / ".agentforge"
        self.agent = agent
        self.tasks: list[str] = []
        self.directs: list[str] = []
        self.saved: dict[tuple, object] = {}
        self.events: list[str] = []
        self.notes: list[str] = []

    def run_task(self, request, **kwargs):
        self.tasks.append(request)
        self.kwargs = kwargs
        if self.agent:
            self.agent(self)
        return {"status": "complete", "text": "done", "plan": "PLAN"}

    def run_direct(self, request, **_kwargs):
        self.directs.append(request)
        return {"status": "complete", "text": "done"}

    def write_record(self, *parts, data):
        self.saved[parts] = data
        path = self.record.joinpath(*parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def read_record(self, *parts, fallback=None):
        path = self.record.joinpath(*parts)
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return fallback

    def begin(self, stage, role=""):
        self.stage = stage
        self.events.append(f"begin {stage}")

    def finish(self, text=""):
        self.stage = "idle"
        self.events.append(f"finish {text}")

    def fail(self, text):
        self.stage = "idle"
        self.events.append(f"fail {text}")

    def save_context(self):
        pass

    def note(self, text, role=""):
        self.notes.append(text)


class Scratch(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.workspace = Path(self.folder.name)
        (self.workspace / ".agentforge" / "srs" / "handoff").mkdir(parents=True)
        (self.workspace / ".agentforge" / "srs" / "handoff" / "app.md").write_text("# Bakery", encoding="utf-8")
        self.session = FakeSession(self.workspace)
        self.kit = self.workspace / "kit"
        for patcher in (
            mock.patch.object(wireframe, "session_for", lambda project: self.session),
            mock.patch.object(document, "session_for", lambda project: self.session),
            mock.patch.object(web_app, "kit_dir", lambda: self.kit),
            mock.patch.object(web_app, "kit_ready", return_value=True),
            mock.patch.object(web_app, "prepare_kit", return_value=(True, "")),
            mock.patch.object(web_app, "build_for"),
            mock.patch.object(wireframe.document, "screens", return_value=PAGES),
            mock.patch.object(wireframe.document, "document", return_value={"srs_document": {"app_summary": {"app_name": "Sweet Crumbs"}}}),
            mock.patch.object(wireframe.bus, "agent_msg"),
            mock.patch.object(wireframe.bus, "phase"),
            mock.patch.object(wireframe.bus, "log"),
            mock.patch.object(wireframe.bus, "sync_state"),
            mock.patch.object(wireframe.bus, "wireframe_changed"),
            mock.patch.object(wireframe.bus, "user_msg"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = web_app.app_dir(self.workspace, "wireframe")


def writes_pages(session: FakeSession) -> None:
    """What the agent does: one page file for every route."""
    pages = web_app.app_dir(session.workspace, "wireframe") / "src" / "pages"
    pages.mkdir(parents=True, exist_ok=True)
    for name in ("home", "orders-id", "orders"):
        (pages / f"{name}.tsx").write_text(f"export default function P() {{ return <p>{name}</p> }}", encoding="utf-8")


class GeneratingTests(Scratch):
    def test_the_agent_gets_the_short_request_the_skill_app_md_and_the_pages_it_writes(self):
        wireframe.generate(PROJECT)

        request = self.session.tasks[0]
        self.assertTrue(request.startswith("Generate low-fidelity wireframes."))
        self.assertIn(".agentforge/skills/web-artifacts-builder/SKILL.md", request)
        self.assertIn(".agentforge/wireframe/app", request)
        self.assertIn(".agentforge/srs/handoff/app.md", request)
        self.assertNotIn("sitemap.md", request)
        self.assertIn("- `/` — Home — `src/pages/home.tsx`", request)
        self.assertIn("- `/orders/[id]` — Order (signed in: Owner) — `src/pages/orders-id.tsx`", request)
        self.assertIn("`/orders` — Orders (signed in: Owner) — `src/pages/orders.tsx`", request)
        self.assertIn("low fidelity", request.lower())
        # a planned run, then written; the pages are the agent's, and are not audited
        self.assertFalse(self.session.kwargs["audit"])

    def test_the_prompt_is_short_and_general(self):
        text = prompts.load("wireframe/generate")
        self.assertLess(len(text), 2400)
        self.assertNotIn("HTML", text)
        for words in ("web-artifacts-builder", "app.md", "{{routes}}", "@/lib/router"):
            self.assertIn(words, text)

    def test_the_skill_is_staged_and_the_app_is_created_with_the_pages_the_specification_names(self):
        wireframe.generate(PROJECT)

        self.assertTrue((self.workspace / ".agentforge/skills/web-artifacts-builder/SKILL.md").is_file())
        self.assertTrue((self.app / "src/components/ui/button.tsx").is_file())
        routes = (self.app / "src/routes.ts").read_text(encoding="utf-8")
        self.assertIn('"route": "/orders/[id]"', routes)
        self.assertIn('"file": "orders-id"', routes)
        self.assertIn("<title>Sweet Crumbs</title>", (self.app / "index.html").read_text(encoding="utf-8"))

    def test_when_the_agent_is_done_the_app_is_bundled_and_the_studio_told(self):
        wireframe.generate(PROJECT)

        web_app.build_for.assert_called_once()
        self.assertEqual(web_app.build_for.call_args.args[1:3], (PROJECT, "wireframe"))
        wireframe.bus.wireframe_changed.assert_called_once_with(PROJECT)
        self.assertEqual(self.session.saved[("wireframe", "state.json")], {"error": ""})

    def test_a_fresh_run_starts_the_app_again_and_a_carried_on_run_keeps_the_pages(self):
        wireframe.generate(PROJECT)
        writes_pages(self.session)
        wireframe.generate(PROJECT, fresh=False)
        self.assertTrue((self.app / "src/pages/home.tsx").is_file())
        self.assertIn("pages from a run that stopped", self.session.tasks[1])

        wireframe.generate(PROJECT, fresh=True)
        self.assertFalse((self.app / "src/pages/home.tsx").exists())
        self.assertNotIn("run that stopped", self.session.tasks[2])

    def test_a_run_needs_screens_and_the_handoff(self):
        with mock.patch.object(wireframe.document, "screens", return_value=[]):
            with self.assertRaisesRegex(ValueError, "no screens"):
                wireframe.generate(PROJECT)
        (self.workspace / ".agentforge/srs/handoff/app.md").unlink()
        with self.assertRaisesRegex(ValueError, "app.md"):
            wireframe.generate(PROJECT)

    def test_a_toolkit_that_cannot_be_installed_is_said_plainly(self):
        with mock.patch.object(web_app, "kit_ready", return_value=False), \
                mock.patch.object(web_app, "prepare_kit", return_value=(False, "npm: network unreachable")):
            with self.assertRaisesRegex(RuntimeError, "could not be installed: npm: network unreachable"):
                wireframe.generate(PROJECT)
        self.assertEqual(self.session.tasks, [])

    def test_the_first_run_says_the_toolkit_is_being_made_ready(self):
        with mock.patch.object(web_app, "kit_ready", return_value=False):
            wireframe.generate(PROJECT)
        self.assertEqual(wireframe.bus.agent_msg.call_args_list[0].kwargs["title"], "Wireframe toolkit")


class RunningTests(Scratch):
    def test_a_whole_run_reports_how_many_pages_are_ready(self):
        self.session.agent = writes_pages
        with mock.patch.object(web_app, "build_for", side_effect=lambda *a, **k: (self.app / "bundle.html").write_text("<html>", encoding="utf-8")):
            result = wireframe.run(PROJECT)

        self.assertEqual(result["ready"], 3)
        self.assertEqual(result["total"], 3)
        self.assertEqual(self.session.events[0], "begin wireframes")
        self.assertTrue(self.session.events[-1].startswith("finish"))
        self.assertEqual(wireframe.bus.sync_state.call_args_list[-1].args[1], "clean")

    def test_a_failure_is_kept_for_the_studio_to_show(self):
        with mock.patch.object(web_app, "build_for", side_effect=web_app.BuildFailed("Could not resolve ./missing")):
            with self.assertRaises(web_app.BuildFailed):
                wireframe.run(PROJECT)
        self.assertEqual(self.session.saved[("wireframe", "state.json")]["error"], "Could not resolve ./missing")
        self.assertEqual(wireframe.bus.sync_state.call_args_list[-1].args[1], "failed")


class ReadingTests(Scratch):
    def read(self):
        with mock.patch.object(document, "screens", return_value=PAGES), \
                mock.patch.object(document, "document", return_value={"srs_document": {"version": "1.0.0"}}), \
                mock.patch.object(document.journeys, "user_journeys_for", return_value=[]):
            return document.wireframes(PROJECT)

    def test_nothing_is_drawn_before_the_agent_has_written_and_the_app_is_bundled(self):
        answer = self.read()
        self.assertEqual([p["route"] for p in answer["pages"]], ["/", "/orders/[id]", "/orders"])
        self.assertFalse(any(p["has_html"] for p in answer["pages"]))
        self.assertFalse(answer["built"])

    def test_a_page_is_there_when_its_file_is_written_and_the_app_is_bundled(self):
        web_app.create_app(self.app, "App", PAGES)
        writes_pages(self.session)
        (self.app / "src/pages/orders.tsx").unlink()
        self.assertFalse(any(p["has_html"] for p in self.read()["pages"]), "not bundled yet")

        (self.app / "bundle.html").write_text("<html>", encoding="utf-8")
        answer = self.read()
        self.assertEqual([p["has_html"] for p in answer["pages"]], [True, True, False])
        self.assertTrue(answer["built"])
        self.assertGreater(answer["version"], 0)
        self.assertEqual(answer["pages"][1]["slug"], "orders-id")

    def test_the_last_error_is_shown_on_every_page(self):
        self.session.write_record("wireframe", "state.json", data={"error": "the toolkit could not be installed"})
        self.assertEqual({p["error"] for p in self.read()["pages"]}, {"the toolkit could not be installed"})


class EditingTests(Scratch):
    def test_one_change_is_a_direct_run_on_the_app_and_it_is_bundled_again(self):
        web_app.create_app(self.app, "App", PAGES)
        wireframe.edit(PROJECT, "Make the order table wider", "/orders")

        request = self.session.directs[0]
        self.assertIn("Make the order table wider", request)
        self.assertIn(".agentforge/wireframe/app", request)
        self.assertIn("`/orders`", request)
        web_app.build_for.assert_called_once()
        wireframe.bus.wireframe_changed.assert_called_once_with(PROJECT)
        self.assertEqual(self.session.events, ["begin wireframe-edit", "finish Wireframes updated."])

    def test_a_change_needs_words_and_wireframes(self):
        with self.assertRaisesRegex(FileNotFoundError, "no wireframes"):
            wireframe.edit(PROJECT, "Make it wider")
        web_app.create_app(self.app, "App", PAGES)
        with self.assertRaisesRegex(ValueError, "describe"):
            wireframe.edit(PROJECT, "   ")
        with self.assertRaisesRegex(ValueError, "under 4,000"):
            wireframe.edit(PROJECT, "x" * 4001)

    def test_a_change_waits_for_a_run_that_is_still_drawing(self):
        web_app.create_app(self.app, "App", PAGES)
        self.session.stage = "wireframes"
        with self.assertRaisesRegex(ValueError, "wait"):
            wireframe.edit(PROJECT, "Make it wider")


class ApprovingTests(unittest.TestCase):
    def test_approving_the_specification_draws_the_wireframes_from_it(self):
        session = SimpleNamespace(stage="idle")
        with mock.patch.object(document, "has_document", return_value=True), \
                mock.patch.object(document, "session_for", return_value=session), \
                mock.patch.object(document.store, "update") as update, \
                mock.patch.object(document.store, "advance") as advance, \
                mock.patch.object(document.bus, "log"), \
                mock.patch.object(wireframe, "run", return_value={"ok": True, "project": PROJECT, "ready": 2, "total": 3}) as run:
            answer = document.approve(PROJECT, "Keep it simple.")

        run.assert_called_once_with(PROJECT, "Keep it simple.")
        update.assert_called_once_with(PROJECT, status="approved")
        advance.assert_called_once_with(PROJECT, "design")
        self.assertEqual(answer["drawn"], 2)

    def test_a_run_that_is_still_going_is_not_started_again(self):
        with mock.patch.object(document, "has_document", return_value=True), \
                mock.patch.object(document, "session_for", return_value=SimpleNamespace(stage="wireframes")):
            with self.assertRaisesRegex(ValueError, "wait"):
                document.approve(PROJECT)


if __name__ == "__main__":
    unittest.main()
