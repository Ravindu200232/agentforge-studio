"""The browser a prototype journey is clicked through in: Puppeteer, driven from here one command at a time.

`server_modules/scripts/prototype-driver.mjs` is a thin remote for a headless browser that is already on the computer (the
one `ollama_terminal.screenshot` found and tried): open a page, list what can be clicked or filled, click it, fill it,
take a picture. All the thinking stays in Python. While it runs, what the browser shows (a picture, the pointer) is handed to
`relay`, which is how the Studio's preview shows the walk live, the way it shows a build's end-to-end tests.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ollama_terminal import screenshot
from server_modules import mermaid
from server_modules.session import RunCancelled

SCRIPT = Path(__file__).resolve().parents[2] / "server_modules" / "scripts" / "prototype-driver.mjs"
SIZE = (1280, 800)
SECONDS = 60          # the longest one command may take
LAUNCH_SECONDS = 90


class DriverError(RuntimeError):
    """The browser could not do what was asked: the message is what it said."""


class Driver:
    """One browser, one tab, a fresh profile. Not thread-safe: a walk is one driver."""

    def __init__(self, relay: Callable[[dict[str, Any]], None] | None = None, live: bool = False, pace: int = 0,
                 size: tuple[int, int] = SIZE, sample: str = "",
                 cancelled: Callable[[], bool] | None = None):
        self.relay = relay
        self.live = live
        self.pace = pace
        self.size = size
        self.sample = sample
        self.cancelled = cancelled
        self._process: subprocess.Popen | None = None
        self._next = 0
        self._answers: dict[int, dict[str, Any]] = {}
        self._waiting: dict[int, threading.Event] = {}
        self._lock = threading.Lock()

    # --- the process ------------------------------------------------------------------------------------------

    def start(self) -> "Driver":
        if self.cancelled and self.cancelled():
            raise RunCancelled("prototype")
        try:
            browser = screenshot.working_browser(cancelled=self.cancelled)
        except InterruptedError as exc:
            raise RunCancelled("prototype") from exc
        if not browser:
            raise DriverError("no browser (Edge, Chrome or Chromium) could be used to walk the journeys")
        nodes = mermaid._node_binaries()  # noqa: SLF001 - the one Node lookup the Studio has
        if not nodes:
            raise DriverError("walking the journeys needs Node.js, and the Studio could not find it")
        env = {**os.environ, "STUDIO_ROOT": str(mermaid._STUDIO_ROOT)}  # noqa: SLF001
        self._process = subprocess.Popen(
            [nodes[0], str(SCRIPT)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", bufsize=1, cwd=str(mermaid._STUDIO_ROOT), env=env,  # noqa: SLF001
            creationflags=mermaid._NO_WINDOW, start_new_session=os.name != "nt")  # noqa: SLF001
        threading.Thread(target=self._read, daemon=True, name="journey-driver").start()
        try:
            self.call("launch", seconds=LAUNCH_SECONDS, exe=browser[0], how=browser[1], width=self.size[0],
                      height=self.size[1], live=self.live, pace=self.pace, sample=self.sample)
        except Exception:
            self.close(fast=bool(self.cancelled and self.cancelled()))
            raise
        return self

    def _read(self) -> None:
        process = self._process
        try:
            for line in process.stdout:
                try:
                    message = json.loads(line)
                except ValueError:
                    continue
                if "live" in message:
                    if self.relay:
                        try:
                            self.relay(message["live"])
                        except Exception:  # noqa: BLE001 - a picture nobody could show is only a picture
                            pass
                    continue
                with self._lock:
                    self._answers[message.get("id")] = message
                    waiting = self._waiting.get(message.get("id"))
                if waiting:
                    waiting.set()
        finally:
            with self._lock:      # the process is gone: whoever waits is told
                for waiting in self._waiting.values():
                    waiting.set()

    def call(self, command: str, seconds: int = SECONDS, **args: Any) -> dict[str, Any]:
        process = self._process
        if process is None or process.poll() is not None:
            raise DriverError("the browser has stopped")
        with self._lock:
            self._next += 1
            number = self._next
            waiting = self._waiting[number] = threading.Event()
        try:
            process.stdin.write(json.dumps({"id": number, "cmd": command, **args}) + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise DriverError(f"the browser could not be reached: {exc}") from exc
        deadline = time.monotonic() + seconds
        while not waiting.wait(0.1):
            if self.cancelled and self.cancelled():
                with self._lock:
                    self._waiting.pop(number, None)
                self.close(fast=True)
                raise RunCancelled("prototype")
            if time.monotonic() >= deadline:
                self.close(fast=True)
                raise DriverError(f"the browser did not answer `{command}` within {seconds} seconds")
        with self._lock:
            answer = self._answers.pop(number, None)
            self._waiting.pop(number, None)
        if answer is None:
            raise DriverError("the browser stopped")
        if not answer.get("ok"):
            raise DriverError(str(answer.get("error") or f"`{command}` failed"))
        return answer

    def close(self, fast: bool = False) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.poll() is None and not fast:
                try:
                    process.stdin.write(json.dumps({"id": 0, "cmd": "close"}) + "\n")
                    process.stdin.flush()
                    process.wait(5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        finally:
            if process.poll() is None:
                # Only this browser, by its own process: never every browser on the computer.
                if os.name == "nt":
                    try:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                                       timeout=1, creationflags=mermaid._NO_WINDOW)  # noqa: SLF001
                    except subprocess.TimeoutExpired:
                        process.kill()
                else:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except OSError:
                        process.kill()
            try:
                process.wait(0.5 if fast else 5)
            except subprocess.TimeoutExpired:
                pass
            for stream in (process.stdin, process.stdout):
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

    def __enter__(self) -> "Driver":
        return self.start()

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # --- what a person does ---------------------------------------------------------------------------------

    def goto(self, file: Path | str) -> dict[str, Any]:
        return self.call("goto", file=str(file))["state"]

    def state(self) -> dict[str, Any]:
        return self.call("state")["state"]

    def elements(self) -> list[dict[str, Any]]:
        return self.call("elements")["elements"]

    def text(self) -> str:
        """The start of what the screen says."""
        return str(self.call("text").get("text") or "")

    def click(self, index: int) -> dict[str, Any]:
        return self.call("click", i=index)

    def fill(self, index: int, value: str) -> dict[str, Any]:
        return self.call("fill", i=index, value=value)

    def key(self, name: str) -> dict[str, Any]:
        """Press a key (Escape closes a dialog that is open)."""
        return self.call("key", key=name)

    def screenshot(self, path: Path) -> Path:
        self.call("screenshot", path=str(path))
        return path

    def errors(self) -> list[str]:
        return self.call("errors")["errors"]

    def reset(self) -> None:
        """A new profile: nothing signed in, nothing remembered."""
        self.call("reset")
