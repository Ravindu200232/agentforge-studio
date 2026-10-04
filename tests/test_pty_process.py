"""A command run in a pseudo-terminal, for sign-ins that refuse to start without one (the Atlas CLI's menu)."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import pty_process  # noqa: E402


def idle() -> pty_process.PtyProcess:
    return pty_process.PtyProcess(1, lambda: None, lambda data: None, lambda: None)


class WhatTheTerminalPrintsTests(unittest.TestCase):
    def lines(self, *chunks: str) -> list[str]:
        process = idle()
        pending = ""
        for chunk in chunks:
            pending = process._feed(pending, chunk)
        process._feed(pending, None)
        return list(process.stdout)

    def test_colour_and_title_codes_are_removed(self):
        self.assertEqual(self.lines("\x1b[32mHello\x1b[0m world\r\n\x1b]0;a title\x07done\r\n"), ["Hello world", "done"])

    def test_a_cursor_move_to_the_next_line_keeps_the_lines_apart(self):
        # The Atlas CLI draws "code, then a sentence" with cursor movement, not newlines.
        text = "copy your one-time verification code:\x1b[1E9PXK-D7YC\x1b[1EPaste the code in the browser."
        self.assertEqual(self.lines(text), ["copy your one-time verification code:", "9PXK-D7YC", "Paste the code in the browser."])

    def test_a_line_split_across_two_reads_is_one_line(self):
        self.assertEqual(self.lines("To continue, go to https://acc", "ount.mongodb.com/connect\r\nnext\r\n"),
                         ["To continue, go to https://account.mongodb.com/connect", "next"])

    def test_the_last_line_without_a_newline_is_not_lost(self):
        self.assertEqual(self.lines("first\r\nname? "), ["first", "name?"])

    def test_blank_lines_are_dropped(self):
        self.assertEqual(self.lines("a\r\n\r\n\r\nb\r\n"), ["a", "b"])


class RealTerminalTests(unittest.TestCase):
    """A real child through a real pseudo-terminal: it must see a terminal, take typed input, and report its exit."""

    CHILD = ("import sys; print('tty:', sys.stdin.isatty(), sys.stdout.isatty(), flush=True); "
             "name = input('name? '); print('hello', name, flush=True)")

    def run_child(self, *typed: str) -> tuple[list[str], int | None]:
        process = pty_process.spawn([sys.executable, "-c", self.CHILD])
        seen: list[str] = []
        reader = threading.Thread(target=lambda: seen.extend(process.stdout), daemon=True)
        reader.start()
        deadline = time.time() + 20
        while not any(line.startswith("tty:") for line in seen) and time.time() < deadline:
            time.sleep(0.1)
        time.sleep(0.5)                       # the child is now waiting at its prompt
        for text in typed:
            process.send(text)
        reader.join(20)
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        return seen, process.poll()

    def test_the_child_sees_a_terminal_and_is_answered_at_its_prompt(self):
        seen, code = self.run_child("bob\r")
        self.assertIn("tty: True True", seen)
        self.assertTrue(any(line.endswith("hello bob") for line in seen), seen)
        self.assertEqual(code, 0)

    def test_a_child_that_is_ended_reports_it(self):
        process = pty_process.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
        self.assertIsNone(process.poll())
        process.kill()
        deadline = time.time() + 10
        while process.poll() is None and time.time() < deadline:
            time.sleep(0.1)
        self.assertIsNotNone(process.poll())


if __name__ == "__main__":
    unittest.main()
