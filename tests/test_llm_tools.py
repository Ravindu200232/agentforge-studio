"""The read-only tool loop `llm.py`'s focused calls opt into, and its
fallback when the selected model cannot take tools at all."""
from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import ollama

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, llm, llm_tools  # noqa: E402
from support import forget_project, isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


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

    def test_a_failed_call_names_itself_in_the_warn_log(self):
        # Found live: a focused SRS/diagram call listing a path that turned
        # out to be a file got a WARN log reading just "Tool error: Not a
        # directory" - no clue which call, even though the model recovers on
        # its own right after. The log line now names the call.
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "dfd.json").write_text("{}", encoding="utf-8")
            tools = llm_tools.ReadOnlyTools(Path(folder), project="prj", role=bus.DEVELOPER)
            events = []
            self.addCleanup(bus.subscribe(events.append))
            result = tools.call("list_files", {"path": "dfd.json"})

        self.assertIn("is a file, not a directory", result)
        # Every event is mirrored across both agent roles (bus.emit's
        # MIRROR_ROLES) so both chat tabs stay in sync - not a duplicate log.
        warnings = [e for e in events if e.get("level") == "WARN"]
        self.assertTrue(warnings)
        self.assertTrue(all("list_files(dfd.json)" in w["text"] and "is a file, not a directory" in w["text"]
                            for w in warnings))

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


class FakeChunk:
    def __init__(self, content="", thinking="", calls=None):
        self.message = SimpleNamespace(content=content, thinking=thinking, tool_calls=calls)


class StreamingTests(unittest.TestCase):
    """Phase 6: `on_stream_token` turns a blocking chat() into a live one,
    without changing what `run_chat()` ultimately returns."""

    def setUp(self):
        llm_tools._UNSUPPORTED_MODELS.clear()

    def test_stream_chat_forwards_each_delta_and_assembles_the_full_message(self):
        def chat(**kwargs):
            self.assertTrue(kwargs["stream"])
            return iter([FakeChunk("hello"), FakeChunk(" world"), FakeChunk("")])

        tokens = []
        message = llm_tools._stream_chat(chat, {"model": "m", "messages": []}, tokens.append)
        self.assertEqual(tokens, ["hello", " world"])
        self.assertEqual(message.content, "hello world")
        self.assertIsNone(message.tool_calls)

    def test_stream_chat_collects_tool_calls_wherever_they_land(self):
        call = ollama.Message.ToolCall(
            function=ollama.Message.ToolCall.Function(name="read_file", arguments={"path": "a"}))

        def chat(**kwargs):
            return iter([FakeChunk("I'll check that."), FakeChunk("", calls=[call]), FakeChunk("")])

        tokens = []
        message = llm_tools._stream_chat(chat, {"model": "m", "messages": []}, tokens.append)
        self.assertEqual(tokens, ["I'll check that."])
        self.assertEqual(message.content, "I'll check that.")
        self.assertEqual(message.tool_calls, [call])

    def test_stream_chat_reports_the_terminal_provider_usage(self):
        final = FakeChunk("done")
        final.prompt_eval_count = 23
        final.eval_count = 5

        def chat(**_kwargs):
            return iter([FakeChunk("part "), final])

        usage = []
        message = llm_tools._stream_chat(chat, {"model": "m", "messages": []},
                                         lambda _token: None, usage.append)
        self.assertEqual(message.content, "part done")
        self.assertEqual(usage, [final])


class FocusedUsageTests(unittest.TestCase):
    def setUp(self):
        llm_tools._UNSUPPORTED_MODELS.clear()

    def test_focused_call_usage_reaches_the_same_memory_meter(self):
        project = "prj_focused_usage"
        seen = []
        cancel = bus.subscribe(seen.append)
        try:
            bus.run_state(project, "running")
            report = llm._focused_usage(project, "test:cloud", 8192, bus.DEVELOPER)
            assert report is not None
            report(SimpleNamespace(prompt_eval_count=123, eval_count=17))
        finally:
            cancel()
            forget_project(project)
        event = next(row for row in seen if row.get("type") == "memory" and row.get("agent") == bus.DEVELOPER)
        self.assertEqual(event["used"], 123)
        self.assertEqual(event["limit"], 8192)
        self.assertEqual(event["sent"], 123)
        self.assertEqual(event["received"], 17)
        self.assertEqual(event["context_scope"], "focused")

    def test_run_chat_streams_the_no_tools_path(self):
        def chat(**kwargs):
            return iter([FakeChunk("hi")])

        tokens, starts = [], []
        message = llm_tools.run_chat(chat, {"model": "m", "messages": []}, None,
                                     on_stream_start=lambda: starts.append(1),
                                     on_stream_token=tokens.append)
        self.assertEqual(message.content, "hi")
        self.assertEqual(tokens, ["hi"])
        self.assertEqual(len(starts), 1)

    def test_run_chat_streams_every_round_and_resets_after_a_tool_round(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, "hello.txt").write_text("hello", encoding="utf-8")
            tools = llm_tools.ReadOnlyTools(Path(folder), project="prj", role=bus.DEVELOPER)
            call = ollama.Message.ToolCall(
                function=ollama.Message.ToolCall.Function(name="read_file", arguments={"path": "hello.txt"}))
            rounds = []

            def chat(**kwargs):
                self.assertTrue(kwargs["stream"])
                if not rounds:
                    rounds.append(1)
                    return iter([FakeChunk("checking the file..."), FakeChunk("", calls=[call])])
                return iter([FakeChunk("Found it.")])

            starts, tokens = [], []
            message = llm_tools.run_chat(chat, {"model": "m", "messages": []}, tools,
                                         on_stream_start=lambda: starts.append(len(tokens)),
                                         on_stream_token=tokens.append)
            self.assertEqual(message.content, "Found it.")
            # A start fired for both rounds — the second start is what the
            # caller uses to reset a buffer the first (tool) round wrote into.
            self.assertEqual(len(starts), 2)
            self.assertEqual(tokens, ["checking the file...", "Found it."])

    def test_a_model_that_cannot_stream_with_tools_still_falls_back_streaming(self):
        tools = llm_tools.ReadOnlyTools(Path("/tmp"), project="prj", role=bus.DEVELOPER)
        calls = []

        def chat(**kwargs):
            calls.append(kwargs)
            if "tools" in kwargs:
                raise ResponseError('model "m" does not support tools', 400)
            return iter([FakeChunk("plain answer")])

        tokens = []
        message = llm_tools.run_chat(chat, {"model": "m", "messages": []}, tools,
                                     on_stream_token=tokens.append)
        self.assertEqual(message.content, "plain answer")
        self.assertEqual(tokens, ["plain answer"])
        self.assertIn("m", llm_tools._UNSUPPORTED_MODELS)


class WebToolsTests(unittest.TestCase):
    """Focused calls can reach for web_search/web_fetch themselves now, not
    only through a Python-side pre-fetch — still never a write or a command."""

    def test_web_search_and_web_fetch_are_offered_read_only(self):
        names = {s["function"]["name"] for s in llm_tools.READ_ONLY_SCHEMAS}
        self.assertIn("web_search", names)
        self.assertIn("web_fetch", names)
        self.assertIn("browser_inspect", names)
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

    def test_browser_tool_uses_its_project_managed_preview(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = llm_tools.ReadOnlyTools(Path(folder), project="prj", role=bus.DEVELOPER)
            with mock.patch("server_modules.preview_runtime.status", return_value={
                    "status": "running", "url": "http://127.0.0.1:3001/"}), \
                 mock.patch("ollama_terminal.tools.inspect_local_page", return_value={"title": "Preview"}) as inspect:
                result = tools.call("browser_inspect", {"viewport": "mobile"})
        self.assertIn("Preview", result)
        inspect.assert_called_once_with(Path(folder), "http://127.0.0.1:3001/", "mobile")


class EffortLevelTests(unittest.TestCase):
    def test_the_four_levels_follow_thinking_and_tool_round_count(self):
        self.assertEqual(llm_tools.effort_level(False, 0), "low")
        self.assertEqual(llm_tools.effort_level(False, 1), "medium")
        self.assertEqual(llm_tools.effort_level(True, 0), "high")
        self.assertEqual(llm_tools.effort_level(True, 1), "high")
        self.assertEqual(llm_tools.effort_level(True, 2), "ultra")


if __name__ == "__main__":
    unittest.main()
