"""The MCP (Model Context Protocol) stdio client, against a real fake server
subprocess (tests/fixtures/fake_mcp_server.py) rather than a mocked one — the
whole point of this module is getting the JSON-RPC framing and lifecycle
right, which a mock would just assume away."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import mcp_client  # noqa: E402


def _config(server_id: str = "fake") -> dict:
    return {"id": server_id, "command": sys.executable,
           "args": [str(Path(__file__).resolve().parent / "fixtures" / "fake_mcp_server.py")]}


class ProbeTests(unittest.TestCase):
    def test_probe_lists_every_tool_across_pages(self):
        tools = mcp_client.probe(_config())
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"echo", "boom", "second_page_tool"})

    def test_a_command_that_does_not_exist_raises_mcperror(self):
        with self.assertRaises(mcp_client.MCPError):
            mcp_client.probe({"id": "missing", "command": "this-binary-does-not-exist-anywhere"})


class MCPManagerTests(unittest.TestCase):
    def test_tool_schemas_are_prefixed_and_ollama_shaped(self):
        manager = mcp_client.MCPManager([_config()])
        try:
            schemas = manager.tool_schemas()
            names = {s["function"]["name"] for s in schemas}
            self.assertIn("mcp__fake__echo", names)
            self.assertIn("mcp__fake__boom", names)
            echo = next(s for s in schemas if s["function"]["name"] == "mcp__fake__echo")
            self.assertEqual(echo["function"]["parameters"]["required"], ["text"])
        finally:
            manager.close()

    def test_is_mcp_tool_distinguishes_mcp_names_from_builtins(self):
        manager = mcp_client.MCPManager([_config()])
        try:
            manager.tool_schemas()
            self.assertTrue(manager.is_mcp_tool("mcp__fake__echo"))
            self.assertFalse(manager.is_mcp_tool("read_file"))
            self.assertFalse(manager.is_mcp_tool("mcp__fake__not_a_real_tool"))
        finally:
            manager.close()

    def test_a_successful_call_round_trips_through_the_real_subprocess(self):
        manager = mcp_client.MCPManager([_config()])
        try:
            result = manager.call("mcp__fake__echo", {"text": "hello"})
            self.assertEqual(result, "echo: hello")
        finally:
            manager.close()

    def test_an_iserror_result_is_reported_as_a_tool_error(self):
        manager = mcp_client.MCPManager([_config()])
        try:
            result = manager.call("mcp__fake__boom", {})
            self.assertTrue(result.startswith("Tool error"))
        finally:
            manager.close()

    def test_a_server_that_cannot_start_is_skipped_not_fatal(self):
        logged = []
        manager = mcp_client.MCPManager(
            [{"id": "broken", "command": "this-binary-does-not-exist-anywhere"}, _config("fake")],
            on_log=logged.append)
        try:
            schemas = manager.tool_schemas()
            names = {s["function"]["name"] for s in schemas}
            self.assertIn("mcp__fake__echo", names)
            self.assertTrue(any("broken" in line for line in logged))
        finally:
            manager.close()

    def test_a_disabled_server_is_never_started(self):
        manager = mcp_client.MCPManager([{**_config(), "enabled": False}])
        try:
            self.assertEqual(manager.tool_schemas(), [])
        finally:
            manager.close()

    def test_calling_an_unknown_name_does_not_start_any_server(self):
        manager = mcp_client.MCPManager([_config()])
        try:
            result = manager.call("not_an_mcp_tool_at_all", {})
            self.assertIn("not a known MCP tool", result)
        finally:
            manager.close()


class WorkspaceToolsIntegrationTests(unittest.TestCase):
    """`WorkspaceTools.execute()` routes an MCP-prefixed name to the manager
    instead of a `tool_<name>` method, and leaves every built-in tool alone."""

    def test_execute_dispatches_mcp_tools_through_the_manager(self):
        import tempfile
        from ollama_terminal.tools import WorkspaceTools

        manager = mcp_client.MCPManager([_config()])
        try:
            with tempfile.TemporaryDirectory() as folder:
                tools = WorkspaceTools(Path(folder), client=None, approve=lambda _q: True, mcp=manager)
                result = tools.execute("mcp__fake__echo", {"text": "via workspace tools"})
                self.assertEqual(result, "echo: via workspace tools")
        finally:
            manager.close()

    def test_execute_without_mcp_still_rejects_unknown_names(self):
        import tempfile
        from ollama_terminal.tools import WorkspaceTools

        with tempfile.TemporaryDirectory() as folder:
            tools = WorkspaceTools(Path(folder), client=None, approve=lambda _q: True)
            result = tools.execute("mcp__fake__echo", {"text": "x"})
            self.assertTrue(result.startswith("Tool error"))


if __name__ == "__main__":
    unittest.main()
