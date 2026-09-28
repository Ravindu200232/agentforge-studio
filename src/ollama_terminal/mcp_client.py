"""A minimal Model Context Protocol (MCP) client: stdio transport only.

MCP servers are ordinary subprocesses that speak newline-delimited JSON-RPC
2.0 over stdin/stdout (https://modelcontextprotocol.io/specification/2025-06-18).
This client only implements the lifecycle and the `tools/*` methods — enough
to let an MCP server's tools show up as more entries in the same tool-calling
loop `Agent`/`WorkspaceTools` already run. It never touches resources or
prompts, and it never speaks the Streamable HTTP transport: stdio is what the
spec says a client SHOULD support first, and it is what every general-purpose
MCP server (filesystem, git, fetch, ...) ships as by default.

One `_StdioServer` owns one subprocess and blocks the calling thread for the
one in-flight JSON-RPC request/response pair it cares about; that matches how
every other tool call in this codebase already works (synchronous, one call
at a time), so no asyncio is introduced just for this.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from typing import Any, Callable

PROTOCOL_VERSION = "2025-06-18"
START_TIMEOUT = 20
CALL_TIMEOUT = 120
MAX_OUTPUT = 24_000

# MCP tool names are only unique within one server. Prefixing them with the
# server id keeps two servers from colliding, and the double underscore
# matches the `mcp__<server>__<tool>` shape this same host environment already
# uses for its own first-party MCP tools.
NAME_PREFIX = "mcp__"


class MCPError(RuntimeError):
    """An MCP server could not be started, or rejected a request."""


def _prefixed(server_id: str, tool_name: str) -> str:
    return f"{NAME_PREFIX}{server_id}__{tool_name}"


class _StdioServer:
    """One running MCP server process and its JSON-RPC pipe."""

    def __init__(self, server_id: str, command: str, args: list[str],
                 env: dict[str, str] | None = None,
                 on_log: Callable[[str], None] | None = None):
        self.id = server_id
        self._on_log = on_log or (lambda _line: None)
        full_env = {**os.environ, **(env or {})}
        try:
            self._process = subprocess.Popen(
                [command, *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
                env=full_env, bufsize=1)
        except OSError as exc:
            raise MCPError(f"could not start '{command}': {exc}") from exc
        self._next_id = 1
        self._write_lock = threading.Lock()
        self._replies: "queue.Queue[dict[str, Any]]" = queue.Queue()
        self.tools: list[dict[str, Any]] = []
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self._process.stdout is not None
        for line in iter(self._process.stdout.readline, ""):
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if isinstance(message, dict):
                self._replies.put(message)

    def _read_stderr(self) -> None:
        # The spec reserves stderr for the server's own logging, not protocol
        # traffic. Draining it (rather than leaving it unread) is what keeps a
        # chatty server from filling its pipe buffer and deadlocking.
        assert self._process.stderr is not None
        for line in iter(self._process.stderr.readline, ""):
            if line.strip():
                self._on_log(line.strip()[:500])

    def _send(self, payload: dict[str, Any]) -> None:
        if self._process.poll() is not None:
            raise MCPError(f"MCP server '{self.id}' has exited")
        assert self._process.stdin is not None
        with self._write_lock:
            self._process.stdin.write(json.dumps(payload) + "\n")
            self._process.stdin.flush()

    def _request(self, method: str, params: dict[str, Any] | None, timeout: float) -> Any:
        with self._write_lock:
            request_id = self._next_id
            self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)
        deadline = time.monotonic() + timeout
        misdirected: list[dict[str, Any]] = []
        try:
            while time.monotonic() < deadline:
                try:
                    message = self._replies.get(timeout=max(0.05, deadline - time.monotonic()))
                except queue.Empty:
                    break
                if message.get("id") != request_id:
                    # Another request's response, or a server-initiated request
                    # this minimal client doesn't serve — put it back for
                    # whoever is actually waiting on it and keep looking.
                    misdirected.append(message)
                    continue
                if "error" in message:
                    error = message["error"] or {}
                    raise MCPError(f"{self.id}: {error.get('message', error)}")
                return message.get("result")
        finally:
            for message in misdirected:
                self._replies.put(message)
        raise MCPError(f"MCP server '{self.id}' timed out answering {method}")

    def _notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self._send(payload)

    def initialize(self) -> None:
        result = self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "agentforge-studio", "version": "1.0"},
        }, START_TIMEOUT)
        if not isinstance(result, dict):
            raise MCPError(f"MCP server '{self.id}' returned an invalid initialize response")
        self._notify("notifications/initialized")

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        for _ in range(20):  # a misbehaving server can't paginate forever
            params = {"cursor": cursor} if cursor else {}
            result = self._request("tools/list", params, START_TIMEOUT) or {}
            tools.extend(t for t in (result.get("tools") or []) if isinstance(t, dict) and t.get("name"))
            cursor = result.get("nextCursor")
            if not cursor:
                break
        self.tools = tools
        return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        result = self._request("tools/call", {"name": name, "arguments": arguments}, CALL_TIMEOUT) or {}
        parts: list[str] = []
        for item in result.get("content") or []:
            if not isinstance(item, dict):
                continue
            kind = item.get("type")
            if kind == "text":
                parts.append(str(item.get("text") or ""))
            elif kind == "resource_link":
                parts.append(f"[resource: {item.get('uri', '')}]")
            elif kind == "resource":
                inner = item.get("resource") or {}
                parts.append(str(inner.get("text") or f"[resource: {inner.get('uri', '')}]"))
            else:
                parts.append(f"[{kind or 'content'}]")
        text = "\n".join(parts).strip()
        if not text and result.get("structuredContent") is not None:
            text = json.dumps(result["structuredContent"], ensure_ascii=False)
        if result.get("isError"):
            text = f"Tool error: {text}"
        return text[:MAX_OUTPUT]

    def close(self) -> None:
        if self._process.poll() is not None:
            return
        try:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
        except Exception:  # noqa: BLE001 - shutdown is best-effort
            pass


class MCPManager:
    """Every configured MCP server for one agent session.

    `configs` is the saved `mcp_servers` setting: a list of
    `{"id", "command", "args", "env", "enabled"}`. Servers are started lazily,
    on the first call to `tool_schemas()`/`is_mcp_tool()`/`call()` — most
    agent turns never touch a tool at all, so nothing is spawned until one is
    actually needed. A server that fails to start or answer `tools/list` is
    skipped (logged via `on_log`) rather than failing the whole agent: one
    broken server should not cost every other tool, built-in or MCP.
    """

    def __init__(self, configs: list[dict[str, Any]] | None,
                 on_log: Callable[[str], None] | None = None):
        self._on_log = on_log or (lambda _line: None)
        self._configs = [c for c in (configs or [])
                         if isinstance(c, dict) and c.get("enabled", True) and c.get("id") and c.get("command")]
        self._servers: dict[str, _StdioServer] = {}
        self._schemas: list[dict[str, Any]] | None = None
        self._tool_owner: dict[str, tuple[str, str]] = {}
        self._lock = threading.Lock()

    def _start(self) -> None:
        with self._lock:
            if self._schemas is not None:
                return
            schemas: list[dict[str, Any]] = []
            for cfg in self._configs:
                server_id = str(cfg["id"])
                try:
                    server = _StdioServer(server_id, str(cfg["command"]),
                                          [str(a) for a in (cfg.get("args") or [])],
                                          {str(k): str(v) for k, v in (cfg.get("env") or {}).items()},
                                          on_log=self._on_log)
                    server.initialize()
                    tools = server.list_tools()
                except MCPError as exc:
                    self._on_log(f"MCP server '{server_id}' unavailable: {exc}")
                    continue
                self._servers[server_id] = server
                for tool in tools:
                    tool_name = str(tool["name"])
                    full_name = _prefixed(server_id, tool_name)
                    self._tool_owner[full_name] = (server_id, tool_name)
                    schemas.append({"type": "function", "function": {
                        "name": full_name,
                        "description": str(tool.get("description")
                                           or f"{tool_name} (from MCP server {server_id})")[:1000],
                        "parameters": tool.get("inputSchema") or {"type": "object", "properties": {}},
                    }})
            self._schemas = schemas

    def tool_schemas(self) -> list[dict[str, Any]]:
        self._start()
        return list(self._schemas or [])

    def is_mcp_tool(self, name: str) -> bool:
        self._start()
        return name in self._tool_owner

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        self._start()
        owner = self._tool_owner.get(name)
        if owner is None:
            return f"Tool error: {name} is not a known MCP tool"
        server_id, tool_name = owner
        server = self._servers.get(server_id)
        if server is None:
            return f"Tool error: MCP server '{server_id}' is not available"
        try:
            return server.call_tool(tool_name, arguments)
        except MCPError as exc:
            return f"Tool error: {exc}"

    def close(self) -> None:
        with self._lock:
            for server in self._servers.values():
                server.close()
            self._servers.clear()


def probe(config: dict[str, Any], timeout: float = START_TIMEOUT) -> list[dict[str, Any]]:
    """Start one server just long enough to list its tools, then stop it.

    Used by the settings UI's "test connection" action, where the customer
    wants to see what a server offers before saving it — never adds anything
    to a running agent's own tool list.
    """
    server_id = str(config.get("id") or "probe")
    server = _StdioServer(server_id, str(config.get("command") or ""),
                          [str(a) for a in (config.get("args") or [])],
                          {str(k): str(v) for k, v in (config.get("env") or {}).items()})
    try:
        server.initialize()
        return server.list_tools()
    finally:
        server.close()
