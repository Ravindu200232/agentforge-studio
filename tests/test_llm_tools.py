"""The read-only tool loop `llm.py`'s focused calls opt into, and its
fallback when the selected model cannot take tools at all."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, llm_tools  # noqa: E402


class FakeMessage:
    def __init__(self, content="", calls=None):
        self.content = content
        self.tool_calls = calls or []

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [{"function": {"name": c.function.name,
                                                  "arguments": c.function.arguments}} for c in self.tool_calls]
        return data


class ResponseError(Exception):
    """Shaped like `ollama.ResponseError` (matched by name, not import) without
    depending on the real package."""
    def __init__(self, error, status_code):
        super().__init__(error)
        self.error = error
        self.status_code = status_code


class RunChatTests(unittest.TestCase):
    def setUp(self):
        llm_tools._UNSUPPORTED_MODELS.clear()

    def test_no_tools_is_a_plain_passthrough(self):
        calls = []

        def chat(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            return SimpleNamespace(message=FakeMessage("hi"))

        message = llm_tools.run_chat(chat, {"model": "m", "messages": []}, None)
        self.assertEqual(message.content, "hi")
        self.assertNotIn("tools", calls[0])

    def test_a_tool_call_is_dispatched_and_the_result_fed_back(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "hello.txt").write_text("hello", encoding="utf-8")
            tools = llm_tools.ReadOnlyTools(Path(folder), project="prj", role=bus.DEVELOPER)
            calls = []

            def chat(**kwargs):
                calls.append(copy.deepcopy(kwargs))
                if len(calls) == 1:
                    call = SimpleNamespace(function=SimpleNamespace(name="read_file", arguments={"path": "hello.txt"}))
                    return SimpleNamespace(message=FakeMessage(calls=[call]))
                return SimpleNamespace(message=FakeMessage("Found it."))

            message = llm_tools.run_chat(chat, {"model": "m", "messages": []}, tools)
            self.assertEqual(message.content, "Found it.")
            self.assertEqual(calls[0]["tools"], llm_tools.READ_ONLY_SCHEMAS)
            self.assertIn("hello", calls[1]["messages"][-1]["content"])
            self.assertEqual(tools.rounds, 1)

    def test_a_model_that_cannot_take_tools_falls_back_and_is_remembered(self):
        events = []
        self.addCleanup(bus.subscribe(events.append))
        tools = llm_tools.ReadOnlyTools(Path("/tmp"), project="prj", role=bus.DEVELOPER)
        calls = []

        def chat(**kwargs):
            calls.append(copy.deepcopy(kwargs))
            if "tools" in kwargs:
                raise ResponseError('model "m" does not support tools', 400)
            return SimpleNamespace(message=FakeMessage("plain answer"))

        message = llm_tools.run_chat(chat, {"model": "m", "messages": []}, tools)
        self.assertEqual(message.content, "plain answer")
        self.assertEqual(len(calls), 2)          # the failed tools= attempt, then the fallback
        self.assertIn("m", llm_tools._UNSUPPORTED_MODELS)
        self.assertTrue(any(e.get("type") == "log" and "does not support tool calling" in e.get("text", "")
                            for e in events))

        # A second call for the same model skips the failing attempt entirely.
        calls.clear()
        message = llm_tools.run_chat(chat, {"model": "m", "messages": []}, tools)
        self.assertEqual(message.content, "plain answer")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("tools", calls[0])

    def test_an_unrelated_chat_error_is_not_mistaken_for_missing_tool_support(self):
        tools = llm_tools.ReadOnlyTools(Path("/tmp"), project="prj", role=bus.DEVELOPER)

        def chat(**kwargs):
            raise ResponseError("internal server error", 500)

        with self.assertRaises(ResponseError):
            llm_tools.run_chat(chat, {"model": "m", "messages": []}, tools)
        self.assertNotIn("m", llm_tools._UNSUPPORTED_MODELS)


class WebToolsTests(unittest.TestCase):
    """Focused calls can reach for web_search/web_fetch themselves now, not
    only through a Python-side pre-fetch — still never a write or a command."""

    def test_web_search_and_web_fetch_are_offered_read_only(self):
        names = {s["function"]["name"] for s in llm_tools.READ_ONLY_SCHEMAS}
        self.assertIn("web_search", names)
        self.assertIn("web_fetch", names)
        self.assertNotIn("write_file", names)
        self.assertNotIn("run_command", names)

    def test_a_web_search_call_reaches_the_injected_client(self):
        class FakeClient:
            def web_search(self, query, max_results):
                return SimpleNamespace(model_dump=lambda: {"results": [{"title": query}]})

        with tempfile.TemporaryDirectory() as folder:
            tools = llm_tools.ReadOnlyTools(Path(folder), project="prj", role=bus.DEVELOPER,
                                            client=FakeClient(), use_local_web=False)
            result = tools.call("web_search", {"query": "test query"})
            self.assertIn("test query", result)
            self.assertEqual(tools.rounds, 1)


class EffortLevelTests(unittest.TestCase):
    def test_the_four_levels_follow_thinking_and_tool_round_count(self):
        self.assertEqual(llm_tools.effort_level(False, 0), "low")
        self.assertEqual(llm_tools.effort_level(False, 1), "medium")
        self.assertEqual(llm_tools.effort_level(True, 0), "high")
        self.assertEqual(llm_tools.effort_level(True, 1), "high")
        self.assertEqual(llm_tools.effort_level(True, 2), "ultra")


if __name__ == "__main__":
    unittest.main()
