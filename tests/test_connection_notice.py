"""The model service does not answer: the chat is told, a person can press "Try again", and the run goes on from there."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

import httpx

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, connection, httpd, llm, session  # noqa: E402


def server_error(text: str = "Internal Server Error (ref: 1f2e3d4c-aaaa-bbbb-cccc-0123456789ab)") -> Exception:
    exc = Exception(text)
    exc.status_code = 500
    return exc


class Told:
    """The events the chat would be told, as (state, fields)."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, state, fields):
        self.events.append((state, dict(fields)))

    @property
    def states(self):
        return [state for state, _ in self.events]


class FailsThenAnswers:
    def __init__(self, failures: int, error=server_error):
        self.failures, self.error, self.calls = failures, error, 0

    def chat(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            raise self.error()
        return "answer"


class PressCounterTests(unittest.TestCase):
    def test_a_press_moves_the_count_of_its_project_only(self):
        before = connection.presses("press-a"), connection.presses("press-b")
        self.assertTrue(connection.retry("press-a"))
        self.assertEqual(connection.presses("press-a"), before[0] + 1)
        self.assertEqual(connection.presses("press-b"), before[1])

    def test_a_press_without_a_project_is_refused(self):
        self.assertFalse(connection.retry(""))
        self.assertEqual(connection.presses(""), 0)

    def test_the_route_presses_for_the_project(self):
        before = connection.presses("press-route")
        self.assertEqual(httpd.dispatch("POST", "/connection/retry", {"project": " press-route "}), {"ok": True})
        self.assertEqual(connection.presses("press-route"), before + 1)
        self.assertEqual(httpd.dispatch("POST", "/connection/retry", {}), {"ok": False})


class ConnectionEventTests(unittest.TestCase):
    def test_the_event_carries_the_state_and_only_the_known_fields(self):
        seen = []
        stop = bus.subscribe(seen.append)
        self.addCleanup(stop)
        bus.connection("conn-event", "retrying", failed=2, of=10, pause=4, detail="Internal Server Error", secret="no")
        event = [e for e in seen if e.get("type") == "connection"][-1]
        self.assertEqual((event["project"], event["state"], event["failed"], event["of"], event["pause"]),
                         ("conn-event", "retrying", 2, 10, 4))
        self.assertEqual(event["agent"], bus.DEVELOPER)
        self.assertNotIn("secret", event)

    def test_it_is_live_only_and_never_written_to_the_project_record(self):
        self.assertNotIn("connection", bus.DURABLE)


class RetryingClientNoticeTests(unittest.TestCase):
    def client(self, inner, told, **kwargs):
        return session.RetryingClient(inner, on_connection=told, **kwargs)

    def test_a_failed_request_is_told_and_asked_again_and_then_said_to_be_back(self):
        told, inner = Told(), FailsThenAnswers(2)
        with mock.patch.object(session.time, "sleep"):
            answer = self.client(inner, told).chat(model="m", messages=[])
        self.assertEqual(answer, "answer")
        self.assertEqual(told.states, ["retrying", "retrying", "ok"])
        first = told.events[0][1]
        self.assertEqual((first["failed"], first["of"], first["pause"]), (1, session.RETRY_ATTEMPTS, 2))
        self.assertEqual(told.events[1][1]["failed"], 2)
        self.assertIn("500", first["detail"])
        self.assertNotIn("1f2e3d4c", first["detail"])         # the service's own reference number is noise in a notice

    def test_a_request_that_never_failed_says_nothing(self):
        told = Told()
        self.assertEqual(self.client(FailsThenAnswers(0), told).chat(model="m", messages=[]), "answer")
        self.assertEqual(told.events, [])

    def test_a_stream_is_told_the_same_way_and_is_back_with_its_first_chunk(self):
        told, calls = Told(), []

        class Inner:
            def chat(self, **kwargs):
                calls.append(1)
                if len(calls) < 3:
                    raise server_error()
                return iter(["a", "b"])

        with mock.patch.object(session.time, "sleep"):
            chunks = list(self.client(Inner(), told).chat(model="m", messages=[], stream=True))
        self.assertEqual(chunks, ["a", "b"])
        self.assertEqual(len(calls), 3)
        self.assertEqual(told.states, ["retrying", "ok"])     # the first attempt only opens the stream; nothing is sent yet

    def test_a_failure_that_asking_again_cannot_mend_is_raised_at_once(self):
        told = Told()
        bad = Exception("bad request")
        bad.status_code = 400
        client = self.client(FailsThenAnswers(5, error=lambda: bad), told, hold=True)
        with self.assertRaises(Exception) as caught:
            client.chat(model="m", messages=[])
        self.assertIs(caught.exception, bad)
        self.assertEqual(told.events, [])

    def test_without_a_hold_it_gives_up_after_its_attempts_as_before(self):
        told = Told()
        with mock.patch.object(session.time, "sleep"), mock.patch.object(session, "RETRY_ATTEMPTS", 3):
            with self.assertRaises(Exception):
                self.client(FailsThenAnswers(99), told).chat(model="m", messages=[])
        self.assertEqual(told.states, ["retrying", "retrying"])

    def test_a_notice_that_cannot_be_shown_never_stops_the_request(self):
        def broken(state, fields):
            raise RuntimeError("the chat is gone")

        with mock.patch.object(session.time, "sleep"):
            answer = session.RetryingClient(FailsThenAnswers(1), on_connection=broken).chat(model="m", messages=[])
        self.assertEqual(answer, "answer")


class TryAgainTests(unittest.TestCase):
    """The person's press while the run waits."""

    def run_in_thread(self, call):
        box = {}

        def work():
            try:
                box["value"] = call()
            except BaseException as exc:  # noqa: BLE001 - checked by the test
                box["error"] = exc

        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread, box

    def until(self, condition, seconds=5.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if condition():
                return True
            time.sleep(0.02)
        return False

    def test_a_press_ends_the_pause_between_attempts_at_once(self):
        told, project = Told(), "try-pause"
        client = session.RetryingClient(FailsThenAnswers(1), on_connection=told,
                                        presses=lambda: connection.presses(project))
        with mock.patch.object(session, "RETRY_BACKOFF", (30,)):
            thread, box = self.run_in_thread(lambda: client.chat(model="m", messages=[]))
            self.assertTrue(self.until(lambda: told.states == ["retrying"]))
            started = time.monotonic()
            connection.retry(project)
            thread.join(5)
        self.assertEqual(box.get("value"), "answer")
        self.assertLess(time.monotonic() - started, 3)       # not the thirty seconds of the pause
        self.assertEqual(told.states, ["retrying", "ok"])

    def test_the_run_holds_after_its_attempts_until_the_press_and_then_goes_on_from_that_request(self):
        told, project = Told(), "try-hold"
        inner = FailsThenAnswers(3)
        client = session.RetryingClient(inner, on_connection=told, presses=lambda: connection.presses(project),
                                        hold=True)
        with mock.patch.object(session, "RETRY_ATTEMPTS", 3), mock.patch.object(session, "RETRY_BACKOFF", (0, 0)):
            thread, box = self.run_in_thread(lambda: client.chat(model="m", messages=[]))
            self.assertTrue(self.until(lambda: "waiting" in told.states))
            time.sleep(0.4)
            self.assertTrue(thread.is_alive())                # it is held, not failed
            self.assertEqual(inner.calls, 3)
            waiting = [fields for state, fields in told.events if state == "waiting"][0]
            self.assertTrue(waiting["hold"])
            self.assertIn("500", waiting["detail"])
            connection.retry(project)
            thread.join(5)
        self.assertEqual(box.get("value"), "answer")          # the request that failed was asked for again, not skipped
        self.assertEqual(inner.calls, 4)
        self.assertEqual(told.states[-1], "ok")

    def test_one_press_releases_every_call_that_waits(self):
        project, results = "try-lanes", []
        with mock.patch.object(session, "RETRY_ATTEMPTS", 1):
            threads = []
            for _ in range(3):
                client = session.RetryingClient(FailsThenAnswers(1), presses=lambda: connection.presses(project),
                                                hold=True)
                thread, box = self.run_in_thread(lambda c=client: c.chat(model="m", messages=[]))
                threads.append((thread, box))
            time.sleep(0.6)
            self.assertTrue(all(thread.is_alive() for thread, _ in threads))
            connection.retry(project)
            for thread, _ in threads:
                thread.join(5)
        self.assertEqual([box.get("value") for _, box in threads], ["answer"] * 3)

    def test_a_press_made_when_nothing_waited_does_not_release_a_later_wait(self):
        project = "try-early"
        connection.retry(project)                              # nobody was waiting
        client = session.RetryingClient(FailsThenAnswers(1), presses=lambda: connection.presses(project), hold=True)
        with mock.patch.object(session, "RETRY_ATTEMPTS", 1):
            thread, box = self.run_in_thread(lambda: client.chat(model="m", messages=[]))
            time.sleep(0.6)
            self.assertTrue(thread.is_alive())
            connection.retry(project)
            thread.join(5)
        self.assertEqual(box.get("value"), "answer")

    def test_stop_ends_a_held_run(self):
        project, stop = "try-stop", threading.Event()
        client = session.RetryingClient(FailsThenAnswers(9), presses=lambda: connection.presses(project), hold=True,
                                        cancelled=stop.is_set, wait_for_cancel=stop.wait)
        with mock.patch.object(session, "RETRY_ATTEMPTS", 1):
            thread, box = self.run_in_thread(lambda: client.chat(model="m", messages=[]))
            time.sleep(0.6)
            self.assertTrue(thread.is_alive())
            stop.set()
            thread.join(5)
        self.assertIsInstance(box.get("error"), session.RunCancelled)

    def test_a_hold_that_nobody_answers_ends_in_the_failure_itself(self):
        client = session.RetryingClient(FailsThenAnswers(9), presses=lambda: 0, hold=True)
        with mock.patch.object(session, "RETRY_ATTEMPTS", 1), mock.patch.object(session, "HOLD_SECONDS", 0.3):
            with self.assertRaises(Exception) as caught:
                client.chat(model="m", messages=[])
        self.assertEqual(getattr(caught.exception, "status_code", None), 500)


class ProjectSessionWiringTests(unittest.TestCase):
    def test_a_session_client_reports_to_its_project_and_holds_for_the_person(self):
        source = (ROOT / "server_modules" / "session.py").read_text(encoding="utf-8")
        self.assertIn("presses=lambda: connection.presses(self.project)", source)
        self.assertIn("hold=True", source)
        self.assertIn("on_connection=", source)


class LlmWiringTests(unittest.TestCase):
    def setUp(self):
        self.seen: list[dict] = []
        stop = bus.subscribe(self.seen.append)
        self.addCleanup(stop)
        self.addCleanup(llm.bind_stop, None)
        llm._local.project, llm._local.role = "", ""

    def told(self):
        return [event for event in self.seen if event.get("type") == "connection"]

    def test_a_call_made_for_a_project_tells_that_project_and_role(self):
        llm._local.project, llm._local.role = "llm-conn", bus.DESIGNER
        llm._connection_report("retrying", {"failed": 1, "of": 10, "pause": 2, "detail": "x"})
        event = self.told()[-1]
        self.assertEqual((event["project"], event["agent"], event["state"]), ("llm-conn", bus.DESIGNER, "retrying"))

    def test_a_call_made_for_no_project_tells_nobody(self):
        llm._connection_report("retrying", {"failed": 1})
        self.assertEqual(self.told(), [])

    def test_the_press_count_is_the_one_of_the_calls_project(self):
        llm._local.project = "llm-presses"
        before = llm._connection_presses()
        connection.retry("llm-presses")
        self.assertEqual(llm._connection_presses(), before + 1)

    def test_it_holds_for_the_person_only_for_a_project_that_can_be_stopped(self):
        self.assertFalse(llm._hold_for_person())
        llm._local.project = "llm-hold"
        self.assertFalse(llm._hold_for_person())               # no Stop to end it with
        llm.bind_stop(threading.Event())
        self.assertTrue(llm._hold_for_person())

    def test_complete_binds_the_project_and_role_of_the_call(self):
        class Message:
            content, thinking = "fine", ""

        with mock.patch.object(llm, "client"), mock.patch.object(llm, "_tools_for", return_value=None), \
             mock.patch("server_modules.llm_tools.run_chat", return_value=Message()), \
             mock.patch("server_modules.llm_tools.tag_effort"), mock.patch.object(llm, "_model", return_value="m"), \
             mock.patch.object(llm, "_context_for", return_value=0):
            self.assertEqual(llm.complete("s", "u", project="llm-bound", role=bus.DESIGNER), "fine")
        self.assertEqual((llm._local.project, llm._local.role), ("llm-bound", bus.DESIGNER))

    def test_a_cached_client_is_given_the_notice_and_the_press(self):
        llm._local.client = None
        inner = object()
        with mock.patch.object(llm, "config") as cfg, mock.patch.object(llm.ollama, "Client", return_value=inner):
            cfg.settings.return_value = {"cloud": False, "ollama_host": "http://x"}
            cfg.engine.return_value = "local"
            built = llm.client()
        self.addCleanup(setattr, llm._local, "client", None)
        self.assertIs(built._on_connection, llm._connection_report)
        self.assertIs(built._presses, llm._connection_presses)
        self.assertIs(built._hold, llm._hold_for_person)


if __name__ == "__main__":
    unittest.main()
