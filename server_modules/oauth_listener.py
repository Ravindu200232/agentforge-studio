"""The one port the desktop app ever opens: where a browser sign-in comes back to, only while one is running.

A provider's browser sign-in ends with a redirect to `http://localhost:<port>/...`. A person's own OAuth app
uses its registered fixed port; the engine's broker can return to a free port if another Studio already owns that one.
The HTTP
backend always does; the desktop app's backend listens on nothing (stdio_bridge.py), so it opens this instead,
answers that one path, and closes again as soon as the callback has arrived or the sign-in has expired.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import config

_lock = threading.Lock()
_open: dict[str, Any] = {"server": None, "paths": set(), "done": None, "closed": None}


class _CallbackServer(ThreadingHTTPServer):
    # ThreadingHTTPServer enables SO_REUSEADDR by default. On Windows that can bind a second
    # listener to a port already owned by the web Studio, so the browser callback is delivered
    # unpredictably. The desktop must exclusively reserve its callback port instead.
    allow_reuse_address = False


def _handler(done: threading.Event) -> type[BaseHTTPRequestHandler]:
    class Callback(BaseHTTPRequestHandler):
        def log_message(self, *_args: Any) -> None:  # noqa: A003 - quiet
            pass

        def do_GET(self) -> None:  # noqa: N802
            from . import httpd

            parsed = urlparse(self.path)
            path = parsed.path[len(config.API_PREFIX):] if parsed.path.startswith(config.API_PREFIX) else ""
            with _lock:
                allowed = path in _open["paths"]
            if not allowed:
                self.send_response(404)
                self.end_headers()
                return
            query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            status, payload, content_type, _ = httpd.respond("GET", path, {}, query)
            body = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            done.set()

    return Callback


def open_for(path: str, seconds: float, *, allow_dynamic: bool = False) -> int:
    """Answer `path` until one request or timeout, returning the port reserved for the callback.

    Nothing to do when the HTTP backend is running: it already answers every path.
    """
    if config.TRANSPORT != "stdio":
        return config.API_PORT
    with _lock:
        _open["paths"].add(path)
        if _open["server"] is not None:
            return _open["server"].server_port
        done = threading.Event()
        closed = threading.Event()
        try:
            server = _CallbackServer(("127.0.0.1", config.API_PORT), _handler(done))
        except OSError as exc:
            if not allow_dynamic:
                _open["paths"].discard(path)
                raise ValueError(f"The sign-in needs port {config.API_PORT} for a moment, and something else is using "
                                 "it. Close the other program (or another AgentForge) and try again.") from exc
            try:
                server = _CallbackServer(("127.0.0.1", 0), _handler(done))
            except OSError:
                _open["paths"].discard(path)
                raise
        server.daemon_threads = True
        _open["server"] = server
        _open["done"] = done
        _open["closed"] = closed

    def run() -> None:
        threading.Thread(target=server.serve_forever, name="oauth-callback", daemon=True).start()
        done.wait(seconds)
        server.shutdown()
        server.server_close()
        with _lock:
            _open["server"] = None
            _open["paths"].clear()
            _open["done"] = None
            _open["closed"] = None
        closed.set()

    threading.Thread(target=run, name="oauth-callback-timer", daemon=True).start()
    return server.server_port


def close() -> None:
    """Release a callback port if sign-in failed before the browser was opened."""
    with _lock:
        done, closed = _open["done"], _open["closed"]
    if done is not None:
        done.set()
    if closed is not None:
        closed.wait(5)


def is_open() -> bool:
    with _lock:
        return _open["server"] is not None
