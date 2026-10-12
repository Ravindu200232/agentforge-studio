"""A run that fails is shown once in the chat, not once by the session and again by the worker that ran it."""
from __future__ import annotations

import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, config, runs  # noqa: E402


class FailureEchoTests(unittest.TestCase):
    def setUp(self):
        # A project of its own per test: `bus.forget` retires a project, and a retired one emits nothing.
        self.project = f"prj_echo_{uuid.uuid4().hex[:8]}"
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patch = mock.patch.object(config, "WORKSPACES", Path(folder.name))
        patch.start()
        self.addCleanup(patch.stop)
        self.events: list[dict] = []
        self.addCleanup(bus.subscribe(self.events.append))
        self.addCleanup(bus.forget, self.project)

    def errors(self) -> list[dict]:
        # The bus files every event under both chats; one failure is one event in each.
        return [e for e in self.events if e.get("type") == "error" and e.get("agent") == bus.DEVELOPER]

    def test_the_same_failure_reported_twice_in_a_row_is_shown_once(self):
        bus.failed(self.project, "E2E user-journey coverage is incomplete: UJ-001, UJ-002")
        bus.failed(self.project, "E2E user-journey coverage is incomplete: UJ-001, UJ-002")
        self.assertEqual(len(self.errors()), 1)

    def test_a_different_failure_is_always_shown(self):
        bus.failed(self.project, "the build stopped")
        bus.failed(self.project, "the preview did not start")
        self.assertEqual([e["text"] for e in self.errors()], ["the build stopped", "the preview did not start"])

    def test_the_session_and_the_worker_that_ran_it_report_one_failure_between_them(self):
        # What a build does: the session says it failed, then the exception goes on to the worker thread.
        def build():
            bus.failed(self.project, "E2E user-journey coverage is incomplete: UJ-001")      # session.fail
            raise ValueError("E2E user-journey coverage is incomplete: UJ-001")              # then the worker sees it

        runs._guarded("build", build, (), {"_project": self.project})
        self.assertEqual(len(self.errors()), 1)

    def test_a_worker_still_reports_a_failure_nobody_reported_before_it(self):
        def build():
            raise ValueError("the model service could not be reached")

        runs._guarded("build", build, (), {"_project": self.project})
        self.assertEqual([e["text"] for e in self.errors()], ["the model service could not be reached"])

    def test_a_retry_that_fails_the_same_way_is_shown_again(self):
        bus.failed(self.project, "Sign in to MongoDB Atlas first.")
        bus.run_state(self.project, "queued")                       # the person pressed Retry: a new run
        bus.failed(self.project, "Sign in to MongoDB Atlas first.")
        self.assertEqual(len(self.errors()), 2)

    def test_the_same_failure_a_while_later_is_shown_again(self):
        bus.failed(self.project, "the build stopped")
        with mock.patch.object(bus.time, "time", return_value=bus.time.time() + bus.FAILURE_ECHO_SECONDS + 1):
            bus.failed(self.project, "the build stopped")
        self.assertEqual(len(self.errors()), 2)

    def test_the_run_state_is_still_failed_after_an_echo_is_dropped(self):
        bus.failed(self.project, "the build stopped")
        bus.failed(self.project, "the build stopped")
        self.assertEqual(bus._runs[self.project][bus.DEVELOPER]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
