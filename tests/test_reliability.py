"""Fifty customer-facing reliability scenarios for AgentForge Studio.

These are deliberately small and deterministic: they exercise the error paths
that matter to someone using the Studio without needing Ollama, a browser, or a
network connection.  Run this file by itself to see the 50-scenario count.
"""
from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent"):
    path = str(ROOT / folder) if folder else str(ROOT)
    if path not in sys.path:
        sys.path.insert(0, path)

from server_modules import bus, config, httpd, runs, session  # noqa: E402
from support import isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


def _reset_bus() -> None:
    with bus._lock:  # noqa: SLF001 - reset process-local test state
        bus._history.clear()  # noqa: SLF001
        bus._runs.clear()  # noqa: SLF001
        bus._listeners.clear()  # noqa: SLF001
        bus._pending_decisions.clear()  # noqa: SLF001
        bus._loaded.clear()  # noqa: SLF001
        bus._discarded.clear()  # noqa: SLF001


class ReliabilityScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_bus()
        with runs._active_lock:  # noqa: SLF001 - reset process-local test state
            runs._active.clear()  # noqa: SLF001
        with session._sessions_lock:  # noqa: SLF001 - reset process-local test state
            session._sessions.clear()  # noqa: SLF001
            session._discarded_projects.clear()  # noqa: SLF001

    def _new_session(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        patcher = patch.object(config, "WORKSPACES", root / "workspaces")
        patcher.start()
        self.addCleanup(patcher.stop)
        return session.ProjectSession("prj_reliability")

    def test_retry_recovers_after_a_transient_network_failure(self):
        calls = []

        class Client:
            def chat(self, **_kwargs):
                calls.append(1)
                if len(calls) == 1:
                    raise httpx.ConnectError("offline")
                return "recovered"

        with patch.object(session.time, "sleep"):
            self.assertEqual(session.RetryingClient(Client()).chat(model="m"), "recovered")
        self.assertEqual(len(calls), 2)

    def test_retry_stops_after_the_tenth_total_attempt(self):
        calls = []

        class Client:
            def chat(self, **_kwargs):
                calls.append(1)
                raise httpx.ReadTimeout("slow")

        with patch.object(session.time, "sleep"):
            with self.assertRaises(httpx.ReadTimeout):
                session.RetryingClient(Client()).chat(model="m")
        self.assertEqual(len(calls), session.RETRY_ATTEMPTS)

    def test_non_retryable_model_error_is_not_replayed(self):
        calls = []

        class Client:
            def chat(self, **_kwargs):
                calls.append(1)
                error = RuntimeError("bad request")
                error.status_code = 400
                raise error

        with self.assertRaises(RuntimeError):
            session.RetryingClient(Client()).chat(model="m")
        self.assertEqual(len(calls), 1)

    def test_stop_before_a_model_call_prevents_the_call(self):
        client = MagicMock()
        with self.assertRaises(session.RunCancelled):
            session.RetryingClient(client, cancelled=lambda: True).chat(model="m")
        client.chat.assert_not_called()

    def test_stop_during_retry_backoff_returns_immediately(self):
        class Client:
            def chat(self, **_kwargs):
                raise httpx.ConnectError("offline")

        waited = []
        with self.assertRaises(session.RunCancelled):
            session.RetryingClient(Client(), wait_for_cancel=lambda seconds: waited.append(seconds) or True).chat(model="m")
        self.assertEqual(waited, [session.RETRY_BACKOFF[0]])

    def test_retry_message_names_the_next_attempt_and_total_limit(self):
        messages = []
        calls = []

        class Client:
            def chat(self, **_kwargs):
                calls.append(1)
                if len(calls) == 1:
                    raise httpx.RemoteProtocolError("disconnected")
                return "ok"

        with patch.object(session.time, "sleep"):
            session.RetryingClient(Client(), announce=messages.append).chat(model="m")
        self.assertIn("Retrying attempt 2 of 10", messages[0])

    def test_retry_without_a_session_uses_the_existing_sleep_fallback(self):
        calls = []

        class Client:
            def chat(self, **_kwargs):
                calls.append(1)
                if len(calls) == 1:
                    raise httpx.ConnectError("offline")
                return "ok"

        with patch.object(session.time, "sleep") as sleep:
            session.RetryingClient(Client()).chat(model="m")
        sleep.assert_called_once_with(session.RETRY_BACKOFF[0])

    def test_discarded_session_is_cancelled(self):
        prototype = self._new_session()
        with session._sessions_lock:  # noqa: SLF001 - register this test session
            session._sessions[prototype.project] = prototype  # noqa: SLF001
        session.drop(prototype.project)
        active = prototype
        self.assertTrue(active.cancelled)
        with self.assertRaises(session.RunCancelled):
            session.session_for(active.project)

    def test_discarded_session_cannot_begin_a_new_run(self):
        active = self._new_session()
        active.discard()
        with self.assertRaises(session.RunCancelled):
            active.begin("build")

    def test_discarded_session_cannot_write_a_record(self):
        active = self._new_session()
        active.discard()
        with self.assertRaises(session.RunCancelled):
            active.write_record("build", "report.json", data={})

    def test_discarded_session_does_not_recreate_a_removed_workspace(self):
        active = self._new_session()
        active._agent = SimpleNamespace(memory_summary="", tool_call_count=0, messages=[])  # noqa: SLF001
        workspace = active.workspace
        active.discard()
        shutil.rmtree(workspace)
        active.save_context()
        self.assertFalse(workspace.exists())

    def test_forget_removes_a_pending_customer_question(self):
        bus._pending_decisions["ask-1"] = {"project": "prj_deleted"}  # noqa: SLF001
        bus.forget("prj_deleted")
        self.assertEqual(bus.pending_decisions(), [])

    def test_forget_discards_late_events_from_a_deleted_project(self):
        # Its own workspace folder: history() reads events back from disk, and a folder left by another run
        # would answer for this one.
        with tempfile.TemporaryDirectory() as folder, patch.object(config, "WORKSPACES", Path(folder) / "workspaces"):
            bus.forget("prj_deleted")
            bus.emit({"type": "log", "project": "prj_deleted", "agent": bus.DEVELOPER, "text": "late"})
            self.assertEqual(bus.history("prj_deleted"), [])

    def test_project_creation_releases_its_event_tombstone(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(config, "WORKSPACES", Path(folder) / "workspaces"):
            bus.forget("prj_reused")
            bus.project_created("prj_reused")
            bus.log("prj_reused", "INFO", "new run")
            self.assertTrue(any(event.get("text") == "new run" for event in bus.history("prj_reused")))

    def test_discarded_mirrored_event_never_reaches_listeners(self):
        received = []
        bus.subscribe(received.append)
        bus.forget("prj_deleted")
        bus.emit({"type": "log", "project": "prj_deleted", "agent": bus.DESIGNER, "text": "late"})
        self.assertEqual(received, [])

    def test_background_start_claims_its_project_before_the_thread_runs(self):
        class Thread:
            def __init__(self, **_kwargs):
                pass

            def start(self):
                pass

        with patch.object(runs.threading, "Thread", Thread):
            runs._in_background("build:prj", "prj", bus.DEVELOPER, lambda: None, _project="prj")  # noqa: SLF001
        self.assertEqual(runs.active_run("prj"), "build:prj")

    def test_second_background_start_is_rejected_before_it_can_write(self):
        with runs._active_lock:  # noqa: SLF001
            runs._active["prj"] = "build:prj"  # noqa: SLF001
        with self.assertRaisesRegex(ValueError, "already working"):
            runs._in_background("test:prj", "prj", bus.DEVELOPER, lambda: None, _project="prj")  # noqa: SLF001

    def test_cancelled_worker_releases_its_project_claim(self):
        with runs._active_lock:  # noqa: SLF001
            runs._active["prj"] = "build:prj"  # noqa: SLF001

        def cancelled():
            raise session.RunCancelled("stopped")

        with patch.object(bus, "cancelled"):
            runs._guarded("build:prj", cancelled, (), {"_project": "prj"})  # noqa: SLF001
        self.assertEqual(runs.active_run("prj"), "")

    def test_stop_requires_a_project_name(self):
        with self.assertRaisesRegex(ValueError, "choose a project"):
            runs.cancel("")

    def test_deleted_project_cannot_start_a_ghost_run(self):
        with patch.object(runs.store, "require", side_effect=KeyError("gone")):
            with self.assertRaises(KeyError):
                runs.agent_build({"project": "gone", "prompt": "continue"})

    def test_stop_active_run_returns_stopping_state(self):
        running = MagicMock(stage="build")
        with runs._active_lock:  # noqa: SLF001
            runs._active["prj"] = "build:prj"  # noqa: SLF001
        with patch.object(runs.store, "require", return_value={}), patch.object(runs, "session_for", return_value=running):
            self.assertEqual(runs.cancel("prj")["status"], "stopping")
        running.cancel.assert_called_once()

    def test_stop_idle_run_is_safe_and_idempotent(self):
        idle = MagicMock(stage="idle")
        with patch.object(runs.store, "require", return_value={}), patch.object(runs, "session_for", return_value=idle):
            result = runs.cancel("prj")
        self.assertEqual(result["status"], "idle")
        idle.cancel.assert_called_once()

    def _delete(self, move_fails: bool = False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        source = root / "workspaces" / "prj_delete"
        source.mkdir(parents=True)
        started = []

        class Thread:
            def __init__(self, **kwargs):
                started.append(kwargs)

            def start(self):
                pass

        patches = [
            patch.object(httpd.config, "workspace_for", return_value=source),
            patch.object(httpd.config, "STATE", root / "state"),
            patch.object(httpd.preview_runtime, "stop"),
            patch.object(httpd.store, "require", return_value={"id": "prj_delete"}),
            patch.object(httpd.store, "delete"),
            patch.object(session, "drop"),
            patch.object(httpd.threading, "Thread", Thread),
        ]
        if move_fails:
            patches.append(patch.object(Path, "replace", side_effect=OSError("locked")))
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        return source, started, httpd.delete_project({"project": "prj_delete"})

    def test_delete_removes_the_project_from_the_logical_store_before_cleanup(self):
        _source, _started, result = self._delete()
        self.assertTrue(result["ok"])
        httpd.store.delete.assert_called_once_with("prj_delete")
        session.drop.assert_called_once_with("prj_delete")

    def test_delete_moves_workspace_as_the_fast_cleanup_path(self):
        source, started, result = self._delete()
        self.assertEqual(result["cleanup"], "moved")
        self.assertFalse(source.exists())
        self.assertIn("deleted-workspaces", str(started[0]["args"][0]))

    def test_delete_schedules_cleanup_when_windows_has_a_file_lock(self):
        source, started, result = self._delete(move_fails=True)
        self.assertEqual(result["cleanup"], "scheduled")
        self.assertEqual(started[0]["args"][0], source)

    def test_network_errors_have_a_clear_recovery_message_in_the_client(self):
        source = (ROOT / "studio" / "lib" / "api.js").read_text(encoding="utf-8")
        self.assertIn("Unable to reach AgentForge right now", source)
        self.assertIn("Your project is saved", source)

    def test_client_wraps_fetch_rejections_as_network_errors(self):
        source = (ROOT / "studio" / "lib" / "api.js").read_text(encoding="utf-8")
        self.assertIn("throw networkError(cause)", source)
        self.assertIn("error.code = 'network'", source)

    def test_stop_button_gives_an_immediate_accessible_acknowledgement(self):
        source = (ROOT / "studio" / "components" / "AgentChat.jsx").read_text(encoding="utf-8")
        self.assertIn('role="status"', source)
        self.assertIn("Stop requested", source)


def _transport_case(error_type):
    def check(self):
        self.assertTrue(session._transient(error_type("network issue")))
    return check


def _retry_status_case(status):
    def check(self):
        error = RuntimeError(f"HTTP {status}")
        error.status_code = status
        self.assertTrue(session._transient(error))
    return check


def _non_retry_status_case(status):
    def check(self):
        error = RuntimeError(f"HTTP {status}")
        error.status_code = status
        self.assertFalse(session._transient(error))
    return check


for _label, _error in {
    "connect_error": httpx.ConnectError,
    "connect_timeout": httpx.ConnectTimeout,
    "read_timeout": httpx.ReadTimeout,
    "write_timeout": httpx.WriteTimeout,
    "pool_timeout": httpx.PoolTimeout,
    "read_error": httpx.ReadError,
    "write_error": httpx.WriteError,
    "proxy_error": httpx.ProxyError,
    "local_protocol_error": httpx.LocalProtocolError,
    "remote_protocol_error": httpx.RemoteProtocolError,
}.items():
    setattr(ReliabilityScenarioTests, f"test_network_{_label}_is_retryable", _transport_case(_error))

for _status in (408, 425, 429, 500, 502, 503, 504):
    setattr(ReliabilityScenarioTests, f"test_http_{_status}_is_retryable", _retry_status_case(_status))

for _status in (400, 401, 403, 404, 422):
    setattr(ReliabilityScenarioTests, f"test_http_{_status}_is_not_retryable", _non_retry_status_case(_status))


if __name__ == "__main__":
    unittest.main()
