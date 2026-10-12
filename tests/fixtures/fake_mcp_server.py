"""A minimal stdio MCP server used only by tests/test_mcp_client.py.

Speaks just enough of the real protocol (initialize, tools/list with
pagination, tools/call, both an ok and an isError result) to prove the
client's framing and lifecycle actually work against a real subprocess,
not a mocked one.
"""
import json
import sys


def send(obj):
    sys.stdout.write(json.dumps(obj) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        message = json.loads(line)
        method = message.get("method")
        request_id = message.get("id")

        if method == "initialize":
            send({"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": "2025-06-18", "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-mcp-server", "version": "0"}}})
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            cursor = (message.get("params") or {}).get("cursor")
            if not cursor:
                send({"jsonrpc": "2.0", "id": request_id, "result": {
                    "tools": [
                        {"name": "echo", "description": "Echoes its input back.",
                         "inputSchema": {"type": "object",
                                        "properties": {"text": {"type": "string"}},
                                        "required": ["text"]}},
                        {"name": "boom", "description": "Always fails.",
                         "inputSchema": {"type": "object", "properties": {}}},
                    ],
                    "nextCursor": "page-2"}})
            else:
                send({"jsonrpc": "2.0", "id": request_id, "result": {
                    "tools": [{"name": "second_page_tool", "description": "From page 2.",
                              "inputSchema": {"type": "object", "properties": {}}}]}})
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name == "boom":
                send({"jsonrpc": "2.0", "id": request_id, "result": {
                    "content": [{"type": "text", "text": "it broke"}], "isError": True}})
            else:
                send({"jsonrpc": "2.0", "id": request_id, "result": {
                    "content": [{"type": "text", "text": "echo: " + str(args.get("text", ""))}]}})
        elif request_id is not None:
            send({"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "unknown method"}})


if __name__ == "__main__":
    main()
