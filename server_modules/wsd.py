"""The live feed.

A minimal RFC 6455 server on the standard library, because the one thing this
socket has to do — push the event bus at every open browser — does not justify a
dependency. The studio proxies `/__agentforge/ws` here, so the path is whatever
Next.js forwarded and is not inspected.
"""
from __future__ import annotations

import base64
import hashlib
import json
import socket
import struct
import threading
from typing import Any, Callable

from . import bus, config

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

OP_CONTINUE, OP_TEXT, OP_BINARY = 0x0, 0x1, 0x2
OP_CLOSE, OP_PING, OP_PONG = 0x8, 0x9, 0xA

MAX_FRAME = 8 * 1024 * 1024


def _accept_key(client_key: str) -> str:
    digest = hashlib.sha1((client_key + GUID).encode("ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


def _read_exactly(conn: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        block = conn.recv(count - len(chunks))
        if not block:
            raise ConnectionError("the socket closed mid-frame")
        chunks.extend(block)
    return bytes(chunks)


def _read_frame(conn: socket.socket) -> tuple[int, bytes]:
    first, second = _read_exactly(conn, 2)
    opcode = first & 0x0F
    masked = bool(second & 0x80)
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", _read_exactly(conn, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _read_exactly(conn, 8))[0]
    if length > MAX_FRAME:
        raise ConnectionError("frame is too large")
    mask = _read_exactly(conn, 4) if masked else b""
    payload = _read_exactly(conn, length) if length else b""
    if masked:
        payload = bytes(byte ^ mask[i % 4] for i, byte in enumerate(payload))
    return opcode, payload


def _frame(opcode: int, payload: bytes) -> bytes:
    header = bytearray([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 1 << 16:
        header.append(126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(127)
        header.extend(struct.pack(">Q", length))
    return bytes(header) + payload


class Client:
    def __init__(self, conn: socket.socket, address: Any):
        self.conn = conn
        self.address = address
        self.lock = threading.Lock()
        self.open = True

    def send(self, message: dict) -> None:
        if not self.open:
            return
        data = json.dumps(message, ensure_ascii=False, default=str).encode("utf-8")
        try:
            with self.lock:
                self.conn.sendall(_frame(OP_TEXT, data))
        except OSError:
            self.close()

    def pong(self, payload: bytes) -> None:
        try:
            with self.lock:
                self.conn.sendall(_frame(OP_PONG, payload))
        except OSError:
            self.close()

    def close(self) -> None:
        if not self.open:
            return
        self.open = False
        try:
            self.conn.close()
        except OSError:
            pass


class FeedServer:
    """Broadcasts every bus event, and hands incoming messages to one handler."""

    def __init__(self, handler: Callable[[dict], None], port: int = 0):
        self.handler = handler
        self.port = port or config.WS_PORT
        self.clients: list[Client] = []
        self.clients_lock = threading.Lock()
        self.socket: socket.socket | None = None
        self._unsubscribe: Callable[[], None] | None = None
        self._stop = threading.Event()

    # --- broadcasting -------------------------------------------------------

    def broadcast(self, event: dict) -> None:
        with self.clients_lock:
            listeners = [c for c in self.clients if c.open]
        for client in listeners:
            client.send(event)
        self._reap()

    def _reap(self) -> None:
        with self.clients_lock:
            self.clients = [c for c in self.clients if c.open]

    # --- accepting ----------------------------------------------------------

    def _handshake(self, conn: socket.socket) -> bool:
        request = bytearray()
        while b"\r\n\r\n" not in request:
            block = conn.recv(4096)
            if not block:
                return False
            request.extend(block)
            if len(request) > 64_000:
                return False
        lines = request.decode("latin-1").split("\r\n")
        headers = {}
        for line in lines[1:]:
            if ":" in line:
                name, _, value = line.partition(":")
                headers[name.strip().lower()] = value.strip()
        key = headers.get("sec-websocket-key")
        if not key or "websocket" not in headers.get("upgrade", "").lower():
            conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return False
        conn.sendall(
            b"HTTP/1.1 101 Switching Protocols\r\n"
            b"Upgrade: websocket\r\n"
            b"Connection: Upgrade\r\n"
            b"Sec-WebSocket-Accept: " + _accept_key(key).encode("ascii") + b"\r\n\r\n")
        return True

    def _serve_client(self, conn: socket.socket, address: Any) -> None:
        try:
            if not self._handshake(conn):
                conn.close()
                return
        except OSError:
            conn.close()
            return

        client = Client(conn, address)
        with self.clients_lock:
            self.clients.append(client)

        # A browser that just connected gets whatever is already waiting on it.
        for question in bus.pending_decisions():
            client.send(question)

        buffer = bytearray()
        try:
            while client.open and not self._stop.is_set():
                opcode, payload = _read_frame(conn)
                if opcode == OP_CLOSE:
                    break
                if opcode == OP_PING:
                    client.pong(payload)
                    continue
                if opcode == OP_PONG:
                    continue
                if opcode in (OP_TEXT, OP_CONTINUE):
                    buffer.extend(payload)
                    try:
                        message = json.loads(buffer.decode("utf-8"))
                    except (UnicodeDecodeError, ValueError):
                        continue
                    buffer.clear()
                    if isinstance(message, dict):
                        self._dispatch(client, message)
        except (ConnectionError, OSError):
            pass
        finally:
            client.close()
            self._reap()

    def _dispatch(self, client: Client, message: dict) -> None:
        if message.get("type") == "ping":
            client.send({"type": "pong"})
            return
        try:
            self.handler(message)
        except Exception as exc:  # noqa: BLE001 - one bad message must not drop the socket
            project = message.get("project")
            if project:
                bus.failed(project, str(exc), agent=message.get("agent") or bus.DEVELOPER)
            else:
                client.send({"type": "error", "text": str(exc)})

    # --- lifecycle ----------------------------------------------------------

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", self.port))
        listener.listen(64)
        self.socket = listener
        self._unsubscribe = bus.subscribe(self.broadcast)
        bus.set_viewer_count(lambda: sum(1 for client in list(self.clients) if client.open))

        def accept_loop() -> None:
            while not self._stop.is_set():
                try:
                    conn, address = listener.accept()
                except OSError:
                    break
                conn.settimeout(None)
                threading.Thread(target=self._serve_client, args=(conn, address),
                                 daemon=True).start()

        threading.Thread(target=accept_loop, name="ws-accept", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        if self._unsubscribe:
            self._unsubscribe()
        with self.clients_lock:
            for client in self.clients:
                client.close()
            self.clients.clear()
        if self.socket:
            # Close alone leaves a listening socket bound on Linux and macOS while the accept loop still holds
            # it, so a restarted feed could not take its port back; shutdown wakes that loop and frees the port.
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self.socket.close()
            except OSError:
                pass
