"""Wireframe generation and compatibility with saved previews."""
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
        self.unplanned: list[str] = []
        self.saved: dict[tuple, object] = {}
        self.events: list[str] = []
        self.notes: list[str] = []

    def run_task(self, request, **kwargs):
        self.tasks.append(request)
        self.kwargs = kwargs
        if self.agent:
            self.agent(self)
        return {"status": "complete", "text": "done", "plan": "PLAN"}

    def run_unplanned(self, request, **_kwargs):
        self.unplanned.append(request)
        return {"status": "complete", "text": "done"}

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
            mock.patch.object(web_app, "kit_dir", lambda legacy=False: self.kit),
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
            mock.patch.object(wireframe, "Review"),
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
    def test_default_generation_publishes_html_without_the_react_kit(self):
        wireframe.generate(PROJECT)
        web_app.prepare_kit.assert_not_called()
        web_app.build_for.assert_not_called()
        wireframe.bus.wireframe_changed.assert_called_once_with(PROJECT)
        self.assertEqual(self.session.saved[("wireframe", "state.json")], {"error": ""})


class ProgressiveDrawingTests(Scratch):
    def test_first_page_is_visible_and_checked_before_the_next_is_written(self):
        folder = wireframe.html_path(PROJECT)
        self.session.agent = lambda session: (folder / "home.html").write_text("<h1>Home</h1>", encoding="utf-8")
        sequence = []

        def next_page(request, **_kwargs):
            name = "orders-id.html" if "`orders-id.html`" in request.split("### Assigned screen")[1] else "orders.html"
            sequence.append(("write", name))
            (folder / name).write_text("<h1>Orders</h1>", encoding="utf-8")
            return {"status": "complete"}

        def check(row):
            pages = document.wireframes(PROJECT)["pages"]
            self.assertTrue(next(page for page in pages if page["route"] == row["route"])["has_html"])
            sequence.append(("check", row["file"]))

        self.session.run_unplanned = next_page
        wireframe.Review.return_value.__enter__.return_value.page.side_effect = check
        result = wireframe.generate(PROJECT)

        self.assertEqual(sequence, [
            ("check", "home.html"), ("write", "orders-id.html"), ("check", "orders-id.html"),
            ("write", "orders.html"), ("check", "orders.html"),
        ])
        self.assertTrue(result["ok"])
        self.assertIn("only the first screen", self.session.tasks[0])


class RunningTests(Scratch):
    def test_a_whole_run_reports_how_many_pages_are_ready(self):
        def draw(session):
            for name in ("home", "orders-id", "orders"):
                (wireframe.html_path(PROJECT) / f"{name}.html").write_text(f"<h1>{name}</h1>", encoding="utf-8")

        self.session.agent = draw
        result = wireframe.run(PROJECT)

        self.assertEqual(result["ready"], 3)
        self.assertEqual(result["total"], 3)
        self.assertEqual(self.session.events[0], "begin wireframes")
        self.assertTrue(self.session.events[-1].startswith("finish"))
        self.assertEqual(wireframe.bus.sync_state.call_args_list[-1].args[1], "clean")

    def test_a_failure_is_kept_for_the_studio_to_show(self):
        with mock.patch.object(wireframe, "generate", side_effect=web_app.BuildFailed("Could not resolve ./missing")):
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
        web_app.create_app(self.app, PAGES)
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
        web_app.create_app(self.app, PAGES)
        (self.app / "index.html").write_text("<div id='root'></div>", encoding="utf-8")
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
        web_app.create_app(self.app, PAGES)
        with self.assertRaisesRegex(ValueError, "describe"):
            wireframe.edit(PROJECT, "   ")
        with self.assertRaisesRegex(ValueError, "under 4,000"):
            wireframe.edit(PROJECT, "x" * 4001)

    def test_a_change_waits_for_a_run_that_is_still_drawing(self):
        web_app.create_app(self.app, PAGES)
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
