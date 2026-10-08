"""The agent's screenshot tool: a page photographed on request, shown to a model that can look at pictures, and kept in the chat."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import agent as agent_module  # noqa: E402
from ollama_terminal import screenshot  # noqa: E402
from ollama_terminal.tools import TOOL_SCHEMAS, WorkspaceTools, describe_call  # noqa: E402
from server_modules import bus, config, session as session_module  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"x" * 700


def fake_shoot(source, out, viewport="desktop", browser=None, seconds=0):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(PNG)
    fake_shoot.calls.append((str(source), viewport))
    return out


fake_shoot.calls = []


class ToolCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fake_shoot.calls.clear()
        patch = mock.patch.object(screenshot, "shoot", fake_shoot)
        patch.start()
        self.addCleanup(patch.stop)
        self.tools = WorkspaceTools(self.root, None, lambda _q: True)


class ToolTests(ToolCase):
    def test_the_tool_is_offered_with_its_arguments_and_described_when_called(self):
        schema = next(s for s in TOOL_SCHEMAS if s["function"]["name"] == "screenshot")
        self.assertEqual(set(schema["function"]["parameters"]["properties"]), {"target", "viewport"})
        self.assertEqual(schema["function"]["parameters"]["required"], [])
        self.assertEqual(describe_call("screenshot", {"target": "dashboard.html", "viewport": "mobile"}), "screenshot(dashboard.html, mobile)")

    def test_a_page_in_the_workspace_is_photographed_and_saved_under_the_qa_shots(self):
        (self.root / "page.html").write_text("<h1>x</h1>", encoding="utf-8")
        answer = json.loads(self.tools.execute("screenshot", {"target": "page.html", "viewport": "mobile"}))
        self.assertTrue(answer["saved"].startswith(".agentforge/qa/shots/screenshot-mobile-"))
        self.assertTrue((self.root / answer["saved"]).is_file())
        self.assertEqual(fake_shoot.calls, [(str((self.root / "page.html").resolve()), "mobile")])

    def test_a_local_preview_url_is_photographed_and_a_remote_one_is_refused(self):
        answer = json.loads(self.tools.execute("screenshot", {"target": "http://localhost:3000/rooms"}))
        self.assertEqual(fake_shoot.calls, [("http://localhost:3000/rooms", "desktop")])
        self.assertEqual(answer["viewport"], "desktop")
        with mock.patch.object(screenshot, "shoot", wraps=screenshot.shoot):
            result = self.tools.execute("screenshot", {"target": "https://example.com"})
        self.assertTrue(result.startswith("Tool error"))

    def test_with_no_target_the_managed_preview_is_used_and_with_none_running_it_says_so(self):
        self.assertIn("Say which page", self.tools.execute("screenshot", {}))
        self.tools.browser_url = lambda: "http://127.0.0.1:5173/"
        json.loads(self.tools.execute("screenshot", {}))
        self.assertEqual(fake_shoot.calls[-1][0], "http://127.0.0.1:5173/")

    def test_a_file_that_is_not_a_page_or_leaves_the_workspace_is_an_error_and_so_is_a_bad_viewport(self):
        (self.root / "notes.txt").write_text("x", encoding="utf-8")
        for args in ({"target": "notes.txt"}, {"target": "missing.html"}, {"target": "../outside.html"},
                     {"target": "http://localhost:3000", "viewport": "tablet"}):
            with self.subTest(args=args):
                self.assertTrue(self.tools.execute("screenshot", args).startswith("Tool error"))

    def test_a_model_that_cannot_look_at_pictures_gets_the_file_saved_and_is_told_so(self):
        (self.root / "page.html").write_text("<h1>x</h1>", encoding="utf-8")
        answer = json.loads(self.tools.execute("screenshot", {"target": "page.html"}))
        self.assertFalse(answer["shown_to_you"])
        self.assertIn("cannot look at pictures", answer["note"])
        self.assertEqual(self.tools.take_images(), [])

    def test_a_model_that_can_gets_the_picture_once_to_be_shown_with_its_label(self):
        (self.root / "page.html").write_text("<h1>x</h1>", encoding="utf-8")
        self.tools.sees_pictures = lambda: True
        answer = json.loads(self.tools.execute("screenshot", {"target": "page.html", "viewport": "mobile"}))
        self.assertTrue(answer["shown_to_you"])
        self.assertIn("attached to the next message", answer["note"])
        self.assertEqual(self.tools.take_images(), [("page.html (mobile)", PNG)])
        self.assertEqual(self.tools.take_images(), [])                  # handed out once


class ShownToTheModelTests(unittest.TestCase):
    """What the agent does with the pictures after a batch of tool calls."""

    def make(self):
        tools = SimpleNamespace(take_images=mock.Mock(return_value=[("dashboard.html (desktop)", PNG), ("dashboard.html (mobile)", PNG + b"y")]))
        agent = agent_module.Agent.__new__(agent_module.Agent)
        agent.tools = tools
        agent.messages = [{"role": "system", "content": "s"}, {"role": "user", "content": "do it"},
                          {"role": "tool", "tool_name": "screenshot", "content": "{}"}]
        return agent, tools

    def test_the_pictures_follow_the_tool_results_as_one_user_message_with_base64_images(self):
        agent, tools = self.make()
        agent._show_pictures()
        message = agent.messages[-1]
        self.assertEqual(message["role"], "user")
        self.assertEqual(message["images"], [base64.b64encode(PNG).decode(), base64.b64encode(PNG + b"y").decode()])
        self.assertIn("the 2 screenshots", message["content"])
        self.assertIn("dashboard.html (mobile)", message["content"])
        self.assertEqual(agent.messages[-2]["role"], "tool")                # right after the tool results

    def test_no_pictures_means_no_message(self):
        agent, tools = self.make()
        tools.take_images.return_value = []
        agent._show_pictures()
        self.assertEqual(len(agent.messages), 3)
        agent.tools = SimpleNamespace()                                      # a toolset with no screenshots at all
        agent._show_pictures()
        self.assertEqual(len(agent.messages), 3)

    def test_only_the_newest_pictures_stay_in_the_history(self):
        agent, tools = self.make()
        agent._show_pictures()
        tools.take_images.return_value = [("home.html (desktop)", PNG)]
        agent._show_pictures()
        pictured = [m for m in agent.messages if m.get("images")]
        self.assertEqual(len(pictured), 1)
        self.assertIn("home.html (desktop)", pictured[0]["content"])
        older = next(m for m in agent.messages if "dashboard.html (desktop)" in str(m.get("content")))
        self.assertNotIn("images", older)
        self.assertIn("no longer attached", older["content"])

    def test_a_conversation_too_long_to_carry_a_picture_is_not_sent_one_and_the_model_is_told(self):
        # The service answered "500" to every try of a 2.6 MB conversation with a 0.75 MB picture, and to nothing smaller.
        agent, tools = self.make()
        agent.messages.append({"role": "user", "content": "x" * agent_module.MAX_REQUEST_BYTES})
        agent._show_pictures()
        self.assertFalse([m for m in agent.messages if m.get("images")])
        note = agent.messages[-1]
        self.assertEqual(note["role"], "user")
        self.assertIn("could not be shown to you", note["content"])
        self.assertIn("dashboard.html (desktop)", note["content"])

    def test_the_pictures_that_fit_are_sent_and_the_ones_that_do_not_are_named_as_left_out(self):
        agent, tools = self.make()
        small, big = b"s" * 1000, b"B" * 900_000
        tools.take_images.return_value = [("small.html (desktop)", small), ("big.html (desktop)", big)]
        agent.messages.append({"role": "user", "content": "x" * (agent_module.MAX_REQUEST_BYTES - 1_000_000)})
        agent._show_pictures()
        pictured = [m for m in agent.messages if m.get("images")]
        self.assertEqual(len(pictured), 1)
        self.assertEqual(len(pictured[0]["images"]), 1)
        self.assertIn("small.html (desktop)", pictured[0]["content"])
        self.assertIn("big.html (desktop)", next(m for m in agent.messages if "could not be shown" in str(m.get("content")))["content"])

    def test_a_short_conversation_gets_its_pictures_as_before(self):
        agent, tools = self.make()
        agent._show_pictures()
        self.assertEqual(len(agent.messages[-1]["images"]), 2)
        self.assertFalse([m for m in agent.messages if "could not be shown" in str(m.get("content"))])

    def test_a_picture_is_a_fixed_cost_in_the_context_not_its_bytes(self):
        big = {"role": "user", "content": "look", "images": [base64.b64encode(b"x" * 2_000_000).decode()]}
        plain = {"role": "user", "content": "look"}
        self.assertEqual(agent_module._approx_tokens([big]) - agent_module._approx_tokens([plain]), agent_module.PICTURE_TOKENS)


class InTheStudioTests(unittest.TestCase):
    """The studio's own tools: the prototype's pages by name, and the chat."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        proto = self.root / ".agentforge" / "prototype"
        proto.mkdir(parents=True)
        self.rows = [{"route": "/", "file": "app/src/App.tsx", "name": "Home"},
                     {"route": "/dashboard", "file": "app/src/App.tsx", "name": "Dashboard"}]
        (proto / "routes.json").write_text(json.dumps({"routes": self.rows}), encoding="utf-8")
        self.messages: list[dict] = []
        patch = mock.patch.object(bus, "agent_msg", lambda project, text, agent="", title="", kind="", design=None, images=None:
                                  self.messages.append({"text": text, "title": title, "kind": kind, "images": images}))
        patch.start()
        self.addCleanup(patch.stop)
        self.tools = session_module.StudioTools(self.root, None, lambda _q: True, project="prj_shots", role_of=lambda: "designer")
        self.shot_page = mock.Mock(side_effect=lambda root, page, out, viewport, cancelled=None: fake_shoot(None, out, viewport))
        patch = mock.patch("prototype_agent.screens.shoot_page", self.shot_page)
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_prototype_page_is_found_by_its_route_and_photographed_in_the_built_app(self):
        answer = json.loads(self.tools.execute("screenshot", {"target": "/dashboard", "viewport": "mobile"}))
        root, page, viewport = (self.shot_page.call_args.args[0], self.shot_page.call_args.args[1],
                                self.shot_page.call_args.args[3])
        self.assertEqual((page["route"], viewport), ("/dashboard", "mobile"))
        self.assertEqual(root, self.root / ".agentforge" / "prototype")
        self.assertTrue((self.root / answer["saved"]).is_file())

    def test_a_page_is_found_by_its_name_or_without_the_slash_and_an_unknown_one_goes_the_generic_way(self):
        for wanted in ("Dashboard", "dashboard", "#/dashboard"):
            with self.subTest(wanted=wanted):
                self.tools.execute("screenshot", {"target": wanted})
                self.assertEqual(self.shot_page.call_args.args[1]["route"], "/dashboard")
        self.shot_page.reset_mock()
        self.tools.execute("screenshot", {"target": "/nowhere"})        # not a page of the prototype: the generic tool refuses it
        self.shot_page.assert_not_called()

    def test_a_local_preview_url_does_not_go_through_the_prototype(self):
        with mock.patch.object(screenshot, "shoot", fake_shoot):
            self.tools.execute("screenshot", {"target": "http://localhost:3000/x"})
        self.shot_page.assert_not_called()

    def test_the_chat_gets_a_message_with_the_screenshot_under_it(self):
        self.tools.sees_pictures = lambda: True
        self.tools.execute("screenshot", {"target": "/dashboard"})
        message = self.messages[-1]
        self.assertEqual((message["title"], message["kind"]), ("Screenshot", "screenshot"))
        self.assertIn("the model is looking at it", message["text"])
        self.assertTrue(message["images"][0]["path"].startswith(".agentforge/qa/shots/screenshot-desktop-"))
        self.assertEqual(message["images"][0]["label"], "/dashboard · desktop")

    def test_for_a_model_that_cannot_see_the_chat_says_it_was_only_saved(self):
        self.tools.execute("screenshot", {"target": "/dashboard"})
        self.assertIn("cannot look at pictures", self.messages[-1]["text"])

    def test_a_failed_screenshot_puts_nothing_in_the_chat(self):
        self.tools.execute("screenshot", {"target": "https://example.com"})
        self.assertEqual(self.messages, [])


class ChatEventTests(unittest.TestCase):
    def test_a_message_carries_its_pictures_and_drops_a_blank_one(self):
        events = []
        with mock.patch.object(bus, "emit", events.append):
            bus.agent_msg("p", "hi", images=[{"path": "a.png", "label": "A"}, {"path": "", "label": "none"}])
            bus.agent_msg("p", "no pictures")
        self.assertEqual(events[0]["images"], [{"path": "a.png", "label": "A"}])
        self.assertNotIn("images", events[1])

    def test_a_saved_conversation_never_carries_picture_bytes(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(config, "workspace_for", lambda project: Path(folder)):
            session = session_module.ProjectSession("prj_ctx")
            session._agent = SimpleNamespace(memory_summary="", tool_call_count=0, messages=[
                {"role": "system", "content": "s"},
                {"role": "user", "content": "here is the screenshot", "images": ["AAAA" * 1000]}])
            session.save_context()
            saved = json.loads(session._context_file().read_text(encoding="utf-8"))
        self.assertEqual(saved["messages"][1], {"role": "user", "content": "here is the screenshot"})


if __name__ == "__main__":
    unittest.main()
