"""Stop ends a run at once, not when the current step happens to finish.

Found live: Stop took about four minutes. Only the gaps between steps looked at it - a model writing a long
reply, or a build or test command running, was waited out in full. Now a model request (streamed or not), a
running command with its children, and the direct model calls a stage makes in its lanes all end on Stop.
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal.tools import WorkspaceTools  # noqa: E402
from server_modules import jobs, llm, runs  # noqa: E402
from server_modules.session import ProjectSession, RetryingClient, RunCancelled  # noqa: E402


class SlowModel:
    """A model that takes far longer than anyone waits after pressing Stop."""

    def __init__(self, first_token_after: float = 0.0, between_tokens: float = 30.0):
        self.first, self.between = first_token_after, between_tokens

    def chat(self, **kwargs):
        if kwargs.get("stream"):
            def stream():
                time.sleep(self.first)
                yield {"message": {"content": "Hello"}}
                time.sleep(self.between)
                yield {"message": {"content": " world"}}
            return stream()
        time.sleep(30)
        return {"message": {"content": "late"}}


def alive(pid: int) -> bool:
    """Running, not merely a dead child nobody has collected yet (a container's first process may never)."""
    try:
        state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
    except (OSError, IndexError):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        return True
    return state not in ("Z", "X")


def stop_after(event: threading.Event, seconds: float) -> None:
    threading.Timer(seconds, event.set).start()


class ModelRequestTests(unittest.TestCase):
    def client(self, inner, stop):
        return RetryingClient(inner, cancelled=stop.is_set, wait_for_cancel=stop.wait)

    def test_a_long_reply_is_walked_away_from_at_once(self):
        stop = threading.Event()
        stop_after(stop, 0.2)
        started = time.monotonic()
        with self.assertRaises(RunCancelled):
            self.client(SlowModel(), stop).chat(model="m", messages=[])
        self.assertLess(time.monotonic() - started, 1.5)

    def test_a_stream_stops_between_tokens(self):
        stop = threading.Event()
        stream = self.client(SlowModel(), stop).chat(model="m", messages=[], stream=True)
        started = time.monotonic()
        chunks = []
        with self.assertRaises(RunCancelled):
            for chunk in stream:
                chunks.append(chunk)
                stop_after(stop, 0.2)
        self.assertEqual(len(chunks), 1)
        self.assertLess(time.monotonic() - started, 1.5)

    def test_a_stream_stops_before_its_first_token(self):
        stop = threading.Event()
        stop_after(stop, 0.2)
        started = time.monotonic()
        with self.assertRaises(RunCancelled):
            list(self.client(SlowModel(first_token_after=30), stop).chat(model="m", messages=[], stream=True))
        self.assertLess(time.monotonic() - started, 1.5)

    def test_without_stop_the_reply_comes_through_unchanged(self):
        class Quick:
            def chat(self, **kwargs):
                if kwargs.get("stream"):
                    return iter([{"n": 1}, {"n": 2}])
                return {"message": "ok"}

        stop = threading.Event()
        client = self.client(Quick(), stop)
        self.assertEqual(client.chat(model="m"), {"message": "ok"})
        self.assertEqual(list(client.chat(model="m", stream=True)), [{"n": 1}, {"n": 2}])

    def test_a_model_error_still_reaches_the_caller(self):
        class Broken:
            def chat(self, **kwargs):
                raise ValueError("the model refused")

        with self.assertRaisesRegex(ValueError, "the model refused"):
            self.client(Broken(), threading.Event()).chat(model="m")


@unittest.skipIf(os.name == "nt", "the POSIX process group path; Windows stops the tree with taskkill /T")
class CommandTests(unittest.TestCase):
    def test_a_running_command_and_its_children_stop_at_once(self):
        stop = threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            tools = WorkspaceTools(Path(folder), client=None, approve=lambda _q: True)
            tools.stop_requested = stop.is_set
            marker = Path(folder) / "child.pid"
            stop_after(stop, 0.5)
            started = time.monotonic()
            output = tools.tool_run_command(f"sleep 60 & echo $! > {marker}; sleep 60", timeout_seconds=120)
            elapsed = time.monotonic() - started
            child = int(marker.read_text().strip())
        self.assertLess(elapsed, 4)
        self.assertIn("Stopped: the run was stopped", output)
        time.sleep(0.3)
        self.assertFalse(alive(child), "the background child went with the command")

    def test_a_command_finishes_normally_when_nobody_stops_it(self):
        with tempfile.TemporaryDirectory() as folder:
            tools = WorkspaceTools(Path(folder), client=None, approve=lambda _q: True)
            tools.stop_requested = threading.Event().is_set
            output = tools.tool_run_command("echo done")
        self.assertIn("exit_code=0", output)
        self.assertIn("done", output)


class DirectCallTests(unittest.TestCase):
    def tearDown(self):
        llm.bind_stop(None)

    def test_the_lanes_of_a_stopped_run_end_instead_of_reporting_failures(self):
        stop = threading.Event()
        llm.bind_stop(stop)
        failed = []

        def draw(page):
            if page == 0:
                stop.set()
            raise RuntimeError("stopped mid-draw")

        with self.assertRaises(RuntimeError):
            llm.in_lanes(list(range(4)), draw, lanes=1, on_error=lambda item, exc: failed.append(item))
        self.assertEqual(failed, [])

    def test_each_lane_sees_the_stop_of_the_run_that_opened_it(self):
        stop = threading.Event()
        llm.bind_stop(stop)
        seen = llm.in_lanes([1, 2, 3], lambda _item: llm._stop_event(), lanes=3)
        self.assertTrue(all(event is stop for event in seen))

    def test_without_a_stop_lanes_report_each_failure_as_before(self):
        llm.bind_stop(None)
        failed = []
        llm.in_lanes([1, 2], lambda item: 1 / 0, on_error=lambda item, exc: failed.append(item))
        self.assertEqual(sorted(failed), [1, 2])

    def test_a_blocking_tool_worker_is_abandoned_when_the_run_stops(self):
        class SlowMcp:
            def is_mcp_tool(self, _name):
                return True

            def call(self, _name, _args):
                time.sleep(30)
                return "late"

        stop = threading.Event()
        with tempfile.TemporaryDirectory() as folder:
            tools = WorkspaceTools(Path(folder), client=None, approve=lambda _q: True, mcp=SlowMcp())
            tools.stop_requested = stop.is_set
            stop_after(stop, 0.15)
            started = time.monotonic()
            result = tools.execute("slow_external_tool", {})
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertIn("stopped", result)


class QueuedRunTests(unittest.TestCase):
    def test_stop_between_queue_and_begin_is_not_cleared(self):
        session = ProjectSession.__new__(ProjectSession)
        session.project = "queued-stop"
        session.lock = threading.RLock()
        session._cancel_lock = threading.Lock()
        session._cancel = threading.Event()
        session._discarded = threading.Event()
        session.prepare_run()
        session.cancel()
        with self.assertRaises(RunCancelled):
            session.begin("srs")

    def test_a_cancelled_job_is_terminal_immediately_and_late_done_cannot_replace_it(self):
        started = threading.Event()
        release = threading.Event()
        notices = []

        def work():
            started.set()
            release.wait(5)
            return {"late": "done"}

        job = jobs.start(work, label="fast-stop", project="job-fast-stop",
                         on_cancel=lambda: notices.append("cancelled"))
        self.assertTrue(started.wait(1))
        began = time.monotonic()
        self.assertEqual(jobs.cancel_project("job-fast-stop"), 1)
        polled = jobs.poll(job)
        self.assertEqual(polled["status"], "cancelled")
        self.assertEqual(polled["result"], {"cancelled": True, "stopped": True})
        self.assertLess(time.monotonic() - began, 1.5)
        release.set()
        time.sleep(0.1)
        self.assertEqual(jobs.poll(job)["status"], "cancelled")
        self.assertEqual(notices, ["cancelled"])

    def test_the_project_stop_endpoint_cancels_its_queued_job_too(self):
        release = threading.Event()
        started = threading.Event()
        session = mock.Mock(stage="idle")

        def work():
            started.set()
            release.wait(5)

        job = jobs.start(work, project="endpoint-stop")
        self.assertTrue(started.wait(1))
        with mock.patch.object(runs.store, "require"), \
             mock.patch.object(runs, "session_for", return_value=session), \
             mock.patch.object(runs, "active_run", return_value=""):
            answer = runs.cancel("endpoint-stop")
        self.assertEqual(answer["status"], "stopping")
        session.cancel.assert_called_once_with()
        self.assertEqual(jobs.poll(job)["status"], "cancelled")
        release.set()


if __name__ == "__main__":
    unittest.main()
