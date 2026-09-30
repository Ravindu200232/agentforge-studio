"""Availability checks for the local API, live feed, and preview recovery.

These tests use real loopback sockets where it matters. They prove that the
Studio can answer its readiness probe, survive malformed or failing feed
messages, and let a fresh feed listener reclaim its port after a restart.
"""
from __future__ import annotations

import base64
import http.client
import json
import socket
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import config, httpd, wsd  # noqa: E402


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _read_http_headers(conn: socket.socket) -> bytes:
    response = bytearray()
    while b"\r\n\r\n" not in response:
        block = conn.recv(4096)
        if not block:
            break
        response.extend(block)
    return bytes(response)


def _read_frame(conn: socket.socket) -> tuple[int, bytes]:
    first = conn.recv(1)
    second = conn.recv(1)
    if not first or not second:
        raise ConnectionError("the feed closed before it responded")
    size = second[0] & 0x7F
    if size == 126:
        size = int.from_bytes(conn.recv(2), "big")
    elif size == 127:
        size = int.from_bytes(conn.recv(8), "big")
    data = bytearray()
    while len(data) < size:
        data.extend(conn.recv(size - len(data)))
    return first[0] & 0x0F, bytes(data)


class ApiAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = httpd.ThreadingHTTPServer(("127.0.0.1", 0), httpd.Studio)
        self.server.daemon_threads = True
        self.port = int(self.server.server_address[1])
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)

    def _request(self, method: str, path: str) -> tuple[int, dict[str, str], dict]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
        try:
            connection.request(method, path)
            response = connection.getresponse()
            raw = response.read()
            return response.status, dict(response.getheaders()), json.loads(raw) if raw else {}
        finally:
            connection.close()

    def test_health_route_is_dependency_free_and_describes_the_feed(self):
        with patch.object(httpd.ollama, "Client", side_effect=AssertionError("must not probe Ollama")):
            answer = httpd.dispatch("GET", "/health")
        self.assertEqual(answer["status"], "ready")
        self.assertTrue(answer["ok"])
        self.assertEqual(answer["service"], "agentforge-studio")
        self.assertEqual(answer["feed_url"], f"ws://127.0.0.1:{config.WS_PORT}")
        self.assertIsInstance(answer["timestamp"], int)

    def test_healthz_is_a_compatible_readiness_alias(self):
        answer = httpd.dispatch("GET", "/healthz")
        self.assertEqual(answer["status"], "ready")
        self.assertTrue(answer["timestamp"] <= int(time.time() * 1000))

    def test_health_rejects_the_wrong_http_method(self):
        with self.assertRaises(httpd.HttpError) as raised:
            httpd.dispatch("POST", "/health")
        self.assertEqual(raised.exception.status, 404)

    def test_readiness_endpoint_answers_over_real_http_with_no_cache_headers(self):
        status, headers, body = self._request("GET", f"{config.API_PREFIX}/health")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")
        self.assertEqual(body["status"], "ready")

    def test_healthz_answers_over_real_http(self):
        status, _headers, body = self._request("GET", f"{config.API_PREFIX}/healthz")
        self.assertEqual((status, body["service"]), (200, "agentforge-studio"))

    def test_non_api_path_returns_a_clear_404(self):
        status, _headers, body = self._request("GET", "/health")
        self.assertEqual((status, body["error"]), (404, "not an API path"))

    def test_unknown_api_path_returns_a_clear_404(self):
        status, _headers, body = self._request("GET", f"{config.API_PREFIX}/missing")
        self.assertEqual(status, 404)
        self.assertIn("no route", body["error"])

    def test_options_allows_a_browser_to_probe_before_requesting_health(self):
        status, headers, _body = self._request("OPTIONS", f"{config.API_PREFIX}/health")
        self.assertEqual(status, 204)
        self.assertIn("GET", headers["Access-Control-Allow-Methods"])

    def test_concurrent_readiness_probes_are_all_available(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            answers = list(pool.map(lambda _: self._request("GET", f"{config.API_PREFIX}/health")[0], range(12)))
        self.assertEqual(answers, [200] * 12)


class FeedAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.port = _free_port()
        self.feed = wsd.FeedServer(lambda _message: None, port=self.port)
        self.feed.start()
        self.addCleanup(self.feed.stop)

    def _connect(self) -> socket.socket:
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        conn.settimeout(2)
        key = base64.b64encode(b"availability-test").decode("ascii")
        conn.sendall(
            f"GET /__agentforge/ws HTTP/1.1\r\nHost: 127.0.0.1:{self.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n".encode("ascii"))
        self.assertIn(b"101 Switching Protocols", _read_http_headers(conn))
        self.addCleanup(conn.close)
        return conn

    def test_feed_accepts_a_websocket_handshake(self):
        conn = self._connect()
        self.assertTrue(conn.fileno() >= 0)
        deadline = time.monotonic() + 0.5
        while not self.feed.clients and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(len(self.feed.clients), 1)

    def test_protocol_ping_receives_a_matching_pong(self):
        conn = self._connect()
        conn.sendall(wsd._frame(wsd.OP_PING, b"still-here"))  # noqa: SLF001 - wire protocol probe
        self.assertEqual(_read_frame(conn), (wsd.OP_PONG, b"still-here"))

    def test_json_ping_receives_a_json_pong(self):
        conn = self._connect()
        conn.sendall(wsd._frame(wsd.OP_TEXT, b'{"type":"ping"}'))  # noqa: SLF001 - wire protocol probe
        opcode, payload = _read_frame(conn)
        self.assertEqual(opcode, wsd.OP_TEXT)
        self.assertEqual(json.loads(payload), {"type": "pong"})

    def test_bad_handshake_does_not_stop_the_listener(self):
        bad = socket.create_connection(("127.0.0.1", self.port), timeout=2)
        bad.settimeout(2)
        self.addCleanup(bad.close)
        bad.sendall(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        self.assertIn(b"400 Bad Request", _read_http_headers(bad))
        self._connect()

    def test_a_handler_failure_returns_an_error_without_dropping_the_socket(self):
        self.feed.handler = lambda _message: (_ for _ in ()).throw(RuntimeError("bad request"))
        conn = self._connect()
        conn.sendall(wsd._frame(wsd.OP_TEXT, b'{"type":"run"}'))  # noqa: SLF001 - wire protocol probe
        opcode, payload = _read_frame(conn)
        self.assertEqual(opcode, wsd.OP_TEXT)
        self.assertEqual(json.loads(payload), {"type": "error", "text": "bad request"})
        conn.sendall(wsd._frame(wsd.OP_TEXT, b'{"type":"ping"}'))  # noqa: SLF001 - wire protocol probe
        self.assertEqual(json.loads(_read_frame(conn)[1]), {"type": "pong"})

    def test_a_fresh_feed_reclaims_the_port_after_a_restart(self):
        self.feed.stop()
        replacement = wsd.FeedServer(lambda _message: None, port=self.port)
        replacement.start()
        self.addCleanup(replacement.stop)
        self._connect()


if __name__ == "__main__":
    unittest.main()
