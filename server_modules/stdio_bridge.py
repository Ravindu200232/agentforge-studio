"""The backend with no ports: the desktop app talks to it over this process's stdin and stdout.

One JSON object per line, each way. The app sends

    {"type": "request", "id": "7", "method": "GET", "path": "/models", "query": {}, "body": {}}
    {"type": "feed", "message": {...}}          what the studio used to send over its WebSocket
    {"type": "ping"}

and reads back

    {"type": "ready", "protocol": 1}
    {"type": "response", "id": "7", "status": 200, "contentType": "application/json", "json": {...}}
    {"type": "response", "id": "8", "status": 200, "contentType": "application/pdf", "base64": "...", "filename": "x.pdf"}
    {"type": "event", "event": {...}}           every bus event, what the WebSocket feed used to broadcast
    {"type": "pong"}

A request is answered by `httpd.respond`, the same function behind the HTTP API, so both answer alike.

stdout is the protocol and nothing else. Anything else that would write to it (a print, a traceback, a child
process that inherits this one's output) goes to stderr instead, and stdin is closed to children for the same
reason: the descriptors the protocol uses are private copies taken before anything else runs.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TextIO

PROTOCOL = 1
WORKERS = 16


def _private_streams() -> tuple[TextIO, TextIO]:
    """Copies of stdin/stdout for the protocol, with the real descriptors pointed away from it."""
    proto_in = os.fdopen(os.dup(0), "r", encoding="utf-8", newline="\n")
    proto_out = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n", buffering=1)
    os.dup2(2, 1)                                   # fd 1 (and any child that inherits it) now writes to stderr
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)                             # and a child that reads stdin reads nothing
    if os.name == "nt":
        # Windows children inherit the process's standard *handles*, not its CRT descriptors: point those too.
        import ctypes
        import msvcrt

        kernel = ctypes.windll.kernel32
        kernel.SetStdHandle(-11, msvcrt.get_osfhandle(2))      # STD_OUTPUT_HANDLE
        kernel.SetStdHandle(-10, msvcrt.get_osfhandle(devnull))  # STD_INPUT_HANDLE
    sys.stdout = sys.stderr
    return proto_in, proto_out


class Bridge:
    def __init__(self, reader: TextIO, writer: TextIO):
        self.reader, self.writer = reader, writer
        self.lock = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="bridge")

    def send(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, ensure_ascii=False, default=str)
        with self.lock:
            self.writer.write(line + "\n")
            self.writer.flush()

    def answer(self, request: dict[str, Any]) -> None:
        from . import httpd

        method = str(request.get("method") or "GET").upper()
        path = str(request.get("path") or "/")
        body = request.get("body") if isinstance(request.get("body"), dict) else {}
        query = {str(k): str(v) for k, v in (request.get("query") or {}).items()}
        status, payload, content_type, filename = httpd.respond(method, path, body if method == "POST" else {}, query)
        reply: dict[str, Any] = {"type": "response", "id": request.get("id"), "status": status,
                                 "contentType": content_type}
        if isinstance(payload, (bytes, bytearray)):
            reply["base64"] = base64.b64encode(payload).decode("ascii")
            if filename:
                reply["filename"] = filename
        else:
            reply["json"] = payload
        self.send(reply)

    def feed(self, message: dict[str, Any]) -> None:
        from . import bus, runs

        try:
            runs.handle(message)
        except Exception as exc:  # noqa: BLE001 - one bad message must not stop the feed (as in wsd.py)
            project = message.get("project")
            if project:
                bus.failed(project, str(exc), agent=message.get("agent") or bus.DEVELOPER)
            else:
                self.send({"type": "event", "event": {"type": "error", "text": str(exc)}})

    def serve(self) -> None:
        from . import bus

        bus.set_viewer_count(lambda: 1)                 # the app's window is the one viewer
        bus.subscribe(lambda event: self.send({"type": "event", "event": event}))
        self.send({"type": "ready", "protocol": PROTOCOL})
        for line in self.reader:
            line = line.strip().lstrip("﻿")        # a writer may open its stream with a byte-order mark
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                continue
            kind = message.get("type")
            if kind == "request":
                self.pool.submit(self._guarded, self.answer, message)
            elif kind == "feed" and isinstance(message.get("message"), dict):
                self.pool.submit(self._guarded, self.feed, message["message"])
            elif kind == "ping":
                self.send({"type": "pong"})
        # stdin closed: the app is gone, and so is this backend, once what was asked has been answered.
        self.pool.shutdown(wait=True)

    def _guarded(self, work, message: dict[str, Any]) -> None:
        try:
            work(message)
        except Exception as exc:  # noqa: BLE001 - a request must always be answered
            if message.get("type") == "request":
                self.send({"type": "response", "id": message.get("id"), "status": 500,
                           "contentType": "application/json", "json": {"error": str(exc)}})


def serve() -> int:
    reader, writer = _private_streams()
    Bridge(reader, writer).serve()
    return 0
