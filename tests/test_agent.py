import tempfile
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ollama_terminal.agent import Agent, model_context_length
from ollama_terminal.guard import SourceGuard
from ollama_terminal.tools import WorkspaceTools


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


class FakeClient:
    def __init__(self):
        self.calls = []

    def show(self, model):
        return SimpleNamespace(modelinfo={"llama.context_length": 8192})

    def chat(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        if len(self.calls) == 1:
            call = SimpleNamespace(function=SimpleNamespace(name="read_file", arguments={"path": "hello.txt"}))
            return SimpleNamespace(message=FakeMessage(calls=[call]))
        return SimpleNamespace(message=FakeMessage("Found the file."))


class ResponseError(Exception):
    """Shaped like `ollama.ResponseError` (matched by name, not import) without
    depending on the real package."""
    def __init__(self, error, status_code):
        super().__init__(error)
        self.error = error
        self.status_code = status_code


class AgentTests(unittest.TestCase):
    def test_a_model_that_cannot_take_tools_fails_with_a_clear_actionable_error(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()

            def refuses_tools(**kwargs):
                client.calls.append(copy.deepcopy(kwargs))
                raise ResponseError("model \"test\" does not support tools", 400)

            client.chat = refuses_tools
            agent = Agent(client, "test", Path(directory), lambda _: False, announce=lambda _: None)
            with self.assertRaisesRegex(RuntimeError, "does not support tool calling"):
                agent.ask("Read hello.txt")
            self.assertEqual(len(client.calls), 1)   # never retried, never reached a tool round trip

    def test_an_unrelated_chat_error_is_not_mistaken_for_missing_tool_support(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()

            def other_error(**kwargs):
                raise ResponseError("internal server error", 500)

            client.chat = other_error
            agent = Agent(client, "test", Path(directory), lambda _: False, announce=lambda _: None)
            with self.assertRaises(ResponseError):
                agent.ask("Read hello.txt")

    def test_sdk_tool_round_trip_and_model_context(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "hello.txt").write_text("hello", encoding="utf-8")
            client = FakeClient()
            agent = Agent(client, "test", Path(directory), lambda _: False, announce=lambda _: None)
            self.assertEqual(model_context_length(client, "test"), 8192)
            self.assertEqual(agent.ask("Read hello.txt"), "Found the file.")
            self.assertEqual(client.calls[0]["options"], {"num_ctx": 8192})
            self.assertEqual(client.calls[1]["messages"][-1]["role"], "tool")
            self.assertIn("hello", client.calls[1]["messages"][-1]["content"])

    def test_provider_usage_is_counted_and_announced_without_estimating(self):
        """The UI meter must receive the model's counts, never a text-length guess."""
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()

            def respond(**kwargs):
                client.calls.append(copy.deepcopy(kwargs))
                return SimpleNamespace(message=FakeMessage("Done."),
                                       prompt_eval_count=41, eval_count=9)

            client.chat = respond
            announced = []
            agent = Agent(client, "test", Path(directory), lambda _: False,
                          announce=announced.append)
            self.assertEqual(agent.ask("Do it"), "Done.")
            self.assertEqual(agent.prompt_tokens, 41)
            self.assertEqual(agent.completion_tokens, 9)
            self.assertIn("[usage] provider response completed", announced)
            self.assertIn("[thinking] model is considering the request", announced)

    def test_cloud_stream_keeps_the_final_provider_usage(self):
        """Hosted models can expose usage only on a stream's terminal chunk."""
        with tempfile.TemporaryDirectory() as directory:
            class CloudClient(FakeClient):
                def chat(self, **kwargs):
                    self.calls.append(copy.deepcopy(kwargs))
                    self.assertTrue(kwargs["stream"])
                    return iter((
                        SimpleNamespace(message=FakeMessage("All ")),
                        SimpleNamespace(message=FakeMessage("done."),
                                        prompt_eval_count=31, eval_count=7),
                    ))

                def assertTrue(self, value):
                    if not value:
                        raise AssertionError("cloud call did not stream")

            client = CloudClient()
            agent = Agent(client, "test:cloud", Path(directory), lambda _: False,
                          cloud=True, announce=lambda _: None)
            self.assertEqual(agent.ask("Do it"), "All done.")
            self.assertEqual(agent.prompt_tokens, 31)
            self.assertEqual(agent.completion_tokens, 7)

    def test_path_escape_and_mutation_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = WorkspaceTools(Path(directory), FakeClient(), lambda _: False)
            self.assertIn("Path escapes", tools.execute("read_file", {"path": "../secret"}))
            self.assertEqual(tools.execute("write_file", {"path": "x.txt", "content": "x"}), "Denied by user")
            self.assertFalse(Path(directory, "x.txt").exists())

    def test_studio_tools_do_not_start_a_foreground_preview_server(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = WorkspaceTools(Path(directory), FakeClient(), lambda _: True)
            tools.managed_preview = True
            result = tools.execute("run_command", {"command": "npm run start"})
            self.assertIn("Studio starts the managed preview", result)

    def test_plan_mode_removes_mutating_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            def write_request(**kwargs):
                client.calls.append(copy.deepcopy(kwargs))
                call = SimpleNamespace(function=SimpleNamespace(
                    name="write_file", arguments={"path": "x.txt", "content": "x"}))
                return SimpleNamespace(message=FakeMessage(calls=[call]) if len(client.calls) == 1
                                       else FakeMessage("Plan only."))
            client.chat = write_request
            agent = Agent(client, "test", Path(directory), lambda _: True, announce=lambda _: None)
            agent.set_mode("plan")
            agent.ask("Plan the work")
            names = {tool["function"]["name"] for tool in client.calls[0]["tools"]}
            self.assertNotIn("run_command", names)
            self.assertNotIn("write_file", names)
            self.assertIn("web_search", names)
            self.assertFalse(Path(directory, "x.txt").exists())
            self.assertEqual(client.calls[1]["messages"][-1]["content"], "Tool unavailable in plan mode")

    def test_model_switch_preserves_context_override(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            agent = Agent(client, "test", Path(directory), lambda _: False,
                          context=16384, announce=lambda _: None)
            agent.messages.extend([
                {"role": "user", "content": "Keep the approved checkout flow."},
                {"role": "assistant", "content": "Noted."},
            ])
            agent.memory_summary = "Checkout needs guest and member paths."
            agent.set_model(client, "other", cloud=True)
            self.assertEqual(agent.context, 16384)
            self.assertIsNone(agent.options)
            self.assertIn("approved checkout", agent.messages[1]["content"])
            self.assertIn("guest and member", agent.memory_summary)

    def test_extra_high_effort_keeps_context_and_adds_a_final_check_rule(self):
        with tempfile.TemporaryDirectory() as directory:
            agent = Agent(FakeClient(), "test", Path(directory), lambda _: False,
                          announce=lambda _: None)
            agent.messages.append({"role": "user", "content": "Keep this turn."})
            agent.set_reasoning_level("xhigh")
            system = agent._system_message()
            self.assertIn("EXTRA-HIGH EFFORT", system)
            self.assertEqual(agent.messages[-1]["content"], "Keep this turn.")

    def test_local_web_search_needs_no_sdk_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            tools = WorkspaceTools(Path(directory), FakeClient(), lambda _: False,
                                   web_host="http://localhost:11434", use_local_web=True)
            with patch("ollama_terminal.tools.httpx.post") as post:
                post.return_value.json.return_value = {"results": [{"title": "Ollama"}]}
                result = tools.execute("web_search", {"query": "Ollama", "max_results": 1})
            self.assertIn("Ollama", result)
            post.assert_called_once_with(
                "http://localhost:11434/api/experimental/web_search",
                json={"query": "Ollama", "max_results": 1}, timeout=30)

    def test_approved_plan_continues_past_tool_batch_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            def respond(**kwargs):
                client.calls.append(copy.deepcopy(kwargs))
                if len(client.calls) == 1:
                    call = SimpleNamespace(function=SimpleNamespace(
                        name="write_file", arguments={"path": "done.txt", "content": "done"}))
                    return SimpleNamespace(message=FakeMessage(calls=[call]))
                if len(client.calls) == 2:
                    return SimpleNamespace(message=FakeMessage("Finished. <TASK_COMPLETE>"))
                if len(client.calls) == 3:
                    call = SimpleNamespace(function=SimpleNamespace(
                        name="read_file", arguments={"path": "done.txt"}))
                    return SimpleNamespace(message=FakeMessage(calls=[call]))
                return SimpleNamespace(message=FakeMessage("Checked. <PLAN_VERIFIED>"))
            client.chat = respond
            agent = Agent(client, "test", Path(directory), lambda _: True,
                          max_steps=1, announce=lambda _: None)
            result = agent.execute_plan("Create done.txt", "1. Create done.txt")
            self.assertEqual(result.status, "complete")
            self.assertEqual(result.rounds, 4)
            self.assertEqual(Path(directory, "done.txt").read_text(), "done")

    def test_source_guard_restores_cli_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "ollama_terminal").mkdir(parents=True)
            source = root / "src" / "ollama_terminal" / "cli.py"
            source.write_text("original", encoding="utf-8")
            guard = SourceGuard(root)
            before = guard.snapshot()
            source.write_text("changed", encoding="utf-8")
            (root / "src" / "ollama_terminal" / "extra.py").write_text("extra", encoding="utf-8")
            changed = guard.restore(before)
            self.assertEqual(source.read_text(encoding="utf-8"), "original")
            self.assertFalse((source.parent / "extra.py").exists())
            self.assertEqual(set(changed), {"src/ollama_terminal/cli.py", "src/ollama_terminal/extra.py"})

    def test_command_restores_protected_cli_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspaces"
            workspace.mkdir()
            readme = root / "README.md"
            readme.write_text("original", encoding="utf-8")
            tools = WorkspaceTools(workspace, FakeClient(), lambda _: True,
                                   protected_app_root=root)
            if os.name == "nt":
                command = f"Set-Content -LiteralPath '{readme}' -Value changed"
            else:
                command = f"printf changed > '{readme}'"
            result = tools.execute("run_command", {"command": command})
            self.assertIn("Protected CLI source changes were reverted", result)
            self.assertEqual(readme.read_text(encoding="utf-8"), "original")

    def test_a_pull_landing_while_a_command_runs_is_not_undone(self):
        """Found live: a deployment command was running when the app's own repository was pulled, and the
        guard put every pulled file back the way it was before the pull."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspaces"
            workspace.mkdir()
            (root / ".git" / "refs" / "heads").mkdir(parents=True)
            (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            branch = root / ".git" / "refs" / "heads" / "main"
            branch.write_text("aaaa\n", encoding="utf-8")
            readme = root / "README.md"
            readme.write_text("original", encoding="utf-8")
            guard = SourceGuard(root)
            before = guard.snapshot()
            self.assertEqual(before.head, "aaaa")
            # What a pull does to the working tree and the branch, while the command is still running.
            readme.write_text("pulled", encoding="utf-8")
            (root / "server.py").write_text("new file from the pull", encoding="utf-8")
            branch.write_text("bbbb\n", encoding="utf-8")
            self.assertEqual(guard.restore(before), [])
            self.assertEqual(readme.read_text(encoding="utf-8"), "pulled")
            self.assertTrue((root / "server.py").exists())
            self.assertEqual(set(guard.left_alone), {"README.md", "server.py"})

    def test_a_project_outside_the_app_is_not_guarded(self):
        with tempfile.TemporaryDirectory() as app, tempfile.TemporaryDirectory() as elsewhere:
            tools = WorkspaceTools(Path(elsewhere), FakeClient(), lambda _: True, protected_app_root=Path(app))
            self.assertIsNone(tools.source_guard)
            inside = Path(app) / "workspaces" / "shop"
            inside.mkdir(parents=True)
            self.assertIsNotNone(WorkspaceTools(inside, FakeClient(), lambda _: True,
                                                protected_app_root=Path(app)).source_guard)

    def test_read_utf16_file_from_windows_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "utf16.txt").write_text("hello", encoding="utf-16")
            tools = WorkspaceTools(Path(directory), FakeClient(), lambda _: False)
            self.assertEqual(tools.execute("read_file", {"path": "utf16.txt"}), "1: hello")

    def test_context_summarizes_old_turns_into_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            summary_calls = []
            def respond(**kwargs):
                if "tools" not in kwargs:
                    summary_calls.append(kwargs)
                    return SimpleNamespace(message=FakeMessage("Keep the old decision."))
                return SimpleNamespace(message=FakeMessage("New answer."))
            client.chat = respond
            agent = Agent(client, "test", Path(directory), lambda _: False,
                          context=4096, announce=lambda _: None)
            agent.messages.extend([
                {"role": "user", "content": "old request"},
                {"role": "assistant", "content": "old output " * 2200},
            ])
            self.assertEqual(agent.ask("new request"), "New answer.")
            self.assertTrue(summary_calls)
            self.assertIn("Keep the old decision.", agent.messages[0]["content"])
            self.assertNotIn("old output", str(agent.messages))
            self.assertIn("new request", str(agent.messages))

    def test_context_summarization_hands_the_deleted_turns_to_on_summarize_before_deleting_them(self):
        """Compression keeps the live conversation inside the model's window, but the project's
        own history — interview answers, SRS wording, an earlier decision — must not become
        unrecoverable the moment this runs. A caller that wants to keep it gets the exact turns,
        verbatim, before they are gone."""
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()

            def respond(**kwargs):
                if "tools" not in kwargs:
                    return SimpleNamespace(message=FakeMessage("Keep the old decision."))
                return SimpleNamespace(message=FakeMessage("New answer."))

            client.chat = respond
            archived: list[list[dict]] = []
            agent = Agent(client, "test", Path(directory), lambda _: False,
                          context=4096, announce=lambda _: None,
                          on_summarize=lambda old: archived.append(old))
            agent.messages.extend([
                {"role": "user", "content": "old request"},
                {"role": "assistant", "content": "old output " * 2200},
            ])
            self.assertEqual(agent.ask("new request"), "New answer.")
            self.assertTrue(archived)
            kept = archived[0]
            self.assertEqual(kept[0], {"role": "user", "content": "old request"})
            self.assertTrue(any("old output" in str(m.get("content", "")) for m in kept))
            # The archive is the one copy left — it is deleted from the live window by this point.
            self.assertNotIn("old output", str(agent.messages))

    def test_a_failing_on_summarize_does_not_break_the_turn_it_was_archiving(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()

            def respond(**kwargs):
                if "tools" not in kwargs:
                    return SimpleNamespace(message=FakeMessage("Keep the old decision."))
                return SimpleNamespace(message=FakeMessage("New answer."))

            client.chat = respond

            def broken(_old):
                raise OSError("disk full")

            agent = Agent(client, "test", Path(directory), lambda _: False,
                          context=4096, announce=lambda _: None, on_summarize=broken)
            agent.messages.extend([
                {"role": "user", "content": "old request"},
                {"role": "assistant", "content": "old output " * 2200},
            ])
            self.assertEqual(agent.ask("new request"), "New answer.")
            self.assertNotIn("old output", str(agent.messages))

    def test_context_summary_falls_back_to_thinking_field(self):
        """A reasoning model can leave `content` empty and answer in `thinking`."""
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()

            def respond(**kwargs):
                if "tools" not in kwargs:
                    message = FakeMessage("")
                    message.thinking = "Deposit stays at 20%."
                    return SimpleNamespace(message=message)
                return SimpleNamespace(message=FakeMessage("New answer."))

            client.chat = respond
            agent = Agent(client, "test", Path(directory), lambda _: False,
                          context=4096, announce=lambda _: None)
            agent.messages.extend([
                {"role": "user", "content": "old request"},
                {"role": "assistant", "content": "old output " * 2200},
            ])
            self.assertEqual(agent.ask("new request"), "New answer.")
            self.assertIn("Deposit stays at 20%.", agent.messages[0]["content"])
            self.assertNotIn("old output", str(agent.messages))

    def test_context_summary_survives_a_model_that_returns_nothing(self):
        """An empty summary must cost detail, never the whole session."""
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()

            def respond(**kwargs):
                if "tools" not in kwargs:
                    return SimpleNamespace(message=FakeMessage(""))
                return SimpleNamespace(message=FakeMessage("New answer."))

            client.chat = respond
            agent = Agent(client, "test", Path(directory), lambda _: False,
                          context=4096, announce=lambda _: None)
            agent.messages.extend([
                {"role": "user", "content": "keep the pickup date rule"},
                {"role": "assistant", "content": "wrote app/order/page.tsx " * 1500},
            ])
            self.assertEqual(agent.ask("new request"), "New answer.")
            # The stretch is gone from the window but its facts are not gone.
            self.assertNotIn("wrote app/order/page.tsx", str(agent.messages))
            self.assertIn("app/order/page.tsx", agent.memory_summary)
            self.assertIn("keep the pickup date rule", agent.memory_summary)

    def test_compaction_summarizes_parts_at_the_same_time_says_how_far_it_is_and_merges_in_order(self):
        """A long project's history used to be summarized one stretch after another, silently, for
        minutes. The stretches now go out together, each one finished is announced, and the merge
        keeps them oldest first."""
        import threading
        import time as clock

        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            lock = threading.Lock()
            live = {"now": 0, "most": 0}
            merges = []

            def respond(**kwargs):
                if "tools" in kwargs:
                    return SimpleNamespace(message=FakeMessage("New answer."))
                text = kwargs["messages"][1]["content"]
                if kwargs["messages"][0]["content"].startswith("Merge"):
                    merges.append(text)
                    return SimpleNamespace(message=FakeMessage("MERGED: " + " | ".join(
                        line for line in text.splitlines() if line.startswith("memory of part"))))
                with lock:
                    live["now"] += 1
                    live["most"] = max(live["most"], live["now"])
                clock.sleep(0.05)
                with lock:
                    live["now"] -= 1
                number = text.split(" of ", 1)[0].removeprefix("History part ")
                return SimpleNamespace(message=FakeMessage(f"memory of part {number}"))

            client.chat = respond
            said: list[str] = []
            agent = Agent(client, "test", Path(directory), lambda _: False, context=4096, announce=said.append)
            agent.messages.extend([
                {"role": "user", "content": "old request"},
                {"role": "assistant", "content": "old output " * 6000},
            ])
            self.assertEqual(agent.ask("new request"), "New answer.")

            progress = [line for line in said if line.startswith("[compacting] ") and "/" in line]
            total = int(progress[0].split("/")[1])
            self.assertGreater(total, 4)
            self.assertEqual(progress, [f"[compacting] {done}/{total}" for done in range(total + 1)])
            self.assertTrue(any(line.startswith("[compacting] merging") for line in said))
            self.assertTrue(any(line.startswith("[context] Compacting") for line in said))
            self.assertGreater(live["most"], 1)                        # parts really went out together
            self.assertLessEqual(live["most"], 4)
            self.assertTrue(merges)
            # Oldest first, whatever order the parts finished in.
            order = [int(piece.rsplit(" ", 1)[1]) for piece in agent.memory_summary.removeprefix("MERGED: ").split(" | ")]
            self.assertEqual(order, sorted(order))
            self.assertNotIn("old output", str(agent.messages))


if __name__ == "__main__":
    unittest.main()
