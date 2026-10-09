"""A browser that stops reading the live feed must never hold up the builds that emit events."""
from __future__ import annotations

import socket
import struct
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", ".deps/py312"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import wsd  # noqa: E402


def pair():
    """Two connected sockets: the server's side of a browser, and the browser."""
    server, browser = socket.socketpair()
    return server, browser


def read_frame(conn):
    first, second = conn.recv(2)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", conn.recv(2))[0]
    elif length == 127:
        length = struct.unpack(">Q", conn.recv(8))[0]
    data = b""
    while len(data) < length:
        data += conn.recv(length - len(data))
    return first & 0x0F, data


class WriterTests(unittest.TestCase):
    def test_what_is_sent_arrives_in_order(self):
        server, browser = pair()
        self.addCleanup(browser.close)
        client = wsd.Client(server, ("127.0.0.1", 1))
        for number in range(5):
            client.send({"type": "log", "n": number})
        client.pong(b"pong!")
        seen = [read_frame(browser) for _ in range(6)]
        self.assertEqual([op for op, _ in seen], [wsd.OP_TEXT] * 5 + [wsd.OP_PONG])
        self.assertEqual([data for _, data in seen[:5]], [b'{"type": "log", "n": %d}' % n for n in range(5)])
        client.close()

    def test_a_browser_that_is_not_reading_never_blocks_the_one_that_sends(self):
        server, browser = pair()
        self.addCleanup(browser.close)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        browser.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        client = wsd.Client(server, ("127.0.0.1", 2), limit=3_000_000)
        big = {"type": "file", "content": "x" * 200_000}
        started = time.time()
        for _ in range(60):                           # about 12 MB toward a browser that never reads
            client.send(big)
        self.assertLess(time.time() - started, 5, "sending toward a browser that does not read must not wait for it")
        self.assertFalse(client.open, "a browser that fell that far behind is dropped")

    def test_every_emitting_thread_goes_on_while_one_browser_is_stuck(self):
        """The failure seen live: builds of three projects all waited behind one browser's full socket."""
        stuck_server, stuck_browser = pair()
        live_server, live_browser = pair()
        self.addCleanup(stuck_browser.close)
        self.addCleanup(live_browser.close)
        stuck_server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
        stuck_browser.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        feed = wsd.FeedServer(lambda _message: None, port=1)
        stuck, live = wsd.Client(stuck_server, ("127.0.0.1", 3), limit=1_000_000), wsd.Client(live_server, ("127.0.0.1", 4))
        feed.clients = [stuck, live]
        done: list[int] = []
        received = [0]

        def reader():                                # the live browser keeps reading
            live_browser.settimeout(0.5)
            try:
                while True:
                    block = live_browser.recv(1 << 20)
                    if not block:
                        return
                    received[0] += len(block)
            except OSError:
                return
        threading.Thread(target=reader, daemon=True).start()

        def build(number):
            for step in range(20):
                feed.broadcast({"type": "file", "project": f"p{number}", "content": "y" * 100_000, "step": step})
            done.append(number)

        threads = [threading.Thread(target=build, args=(n,), daemon=True) for n in range(3)]
        started = time.time()
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        self.assertEqual(sorted(done), [0, 1, 2])
        self.assertLess(time.time() - started, 10)
        self.assertFalse(stuck.open)
        self.assertTrue(live.open)
        self.assertEqual(feed.clients, [live])           # the dropped one is forgotten
        deadline = time.time() + 5
        while received[0] < 6_000_000 and time.time() < deadline:
            time.sleep(0.05)
        self.assertGreaterEqual(received[0], 6_000_000)  # the reading browser got every event of the three builds
        live.close()

    def test_closing_a_client_ends_its_writer(self):
        server, browser = pair()
        self.addCleanup(browser.close)
        client = wsd.Client(server, ("127.0.0.1", 5))
        client.close()
        client.send({"type": "log"})                       # a closed client ignores what is sent to it
        self.assertFalse(client.open)
        self.assertEqual(len(client._frames), 0)  # noqa: SLF001


if __name__ == "__main__":
    unittest.main()
