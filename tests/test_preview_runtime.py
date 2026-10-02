"""Ownership rules for isolated, project-local Studio preview ports."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
for folder in ("", "src", "srs-agent", "prototype-agent", "builder-agent", "qa-agent", "deploy-agent", ".deps"):
    value = str(ROOT / folder) if folder else str(ROOT)
    if value not in sys.path:
        sys.path.insert(0, value)

from server_modules import preview_runtime, prompts, runs  # noqa: E402
from support import isolate_workspaces  # noqa: E402


def setUpModule():
    isolate_workspaces()


class PreviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        preview_runtime._processes.clear()  # noqa: SLF001 - reset module state
        preview_runtime._last.clear()  # noqa: SLF001 - reset module state

    def test_project_port_order_is_stable_and_in_the_private_preview_range(self):
        first = preview_runtime._port_candidates("demo")
        self.assertEqual(first, preview_runtime._port_candidates("demo"))
        self.assertEqual(len(first), preview_runtime.PREVIEW_PORT_LAST - preview_runtime.PREVIEW_PORT_FIRST + 1)
        self.assertEqual(len(set(first)), len(first))
        self.assertTrue(all(preview_runtime.PREVIEW_PORT_FIRST <= port <= preview_runtime.PREVIEW_PORT_LAST
                            for port in first))

    def test_busy_port_is_skipped_without_touching_the_unrelated_listener(self):
        candidates = preview_runtime._port_candidates("demo")
        with patch.object(preview_runtime, "_port_open", side_effect=lambda port: port == candidates[0]), \
             patch.object(preview_runtime, "_terminate_tree") as terminate:
            selected = preview_runtime._preview_port("demo", {})
        self.assertEqual(selected, candidates[1])
        terminate.assert_not_called()

    def test_status_rejects_stale_metadata_without_listener_ownership(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            (record / "preview-runtime.json").write_text(
                json.dumps({"port": preview_runtime.PREVIEW_PORT_FIRST}), encoding="utf-8")
            with patch.object(preview_runtime, "_metadata", return_value=record / "preview-runtime.json"), \
                 patch.object(preview_runtime, "_port_open", return_value=True), \
                 patch.object(preview_runtime, "_listening_pids", return_value=[8888]):
                self.assertEqual(preview_runtime.status("demo")["status"], "stopped")

    def test_status_accepts_only_the_recorded_listener(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            (record / "preview-runtime.json").write_text(
                json.dumps({"port": preview_runtime.PREVIEW_PORT_FIRST, "listenerPid": 8888,
                            "url": f"http://127.0.0.1:{preview_runtime.PREVIEW_PORT_FIRST}/"}),
                encoding="utf-8",
            )
            with patch.object(preview_runtime, "_metadata", return_value=record / "preview-runtime.json"), \
                 patch.object(preview_runtime, "_listening_pids", return_value=[8888]):
                self.assertEqual(preview_runtime.status("demo")["status"], "running")

    def test_cache_corrupted_detects_the_stale_chunk_signature(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "preview.log"
            log_path.write_bytes(b"info: compiling\nError: Cannot find module './611.js'\nRequire stack:\n")
            self.assertTrue(preview_runtime._cache_corrupted(log_path))

    def test_cache_corrupted_ignores_a_real_missing_package(self):
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "preview.log"
            log_path.write_bytes(b"Error: Cannot find module 'left-pad'\n")
            self.assertFalse(preview_runtime._cache_corrupted(log_path))

    def test_heal_clears_the_next_cache_and_relaunches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".next").mkdir()
            (root / ".next" / "marker.txt").write_text("stale", encoding="utf-8")
            log_path = root / "preview.log"
            log_path.touch()
            old_process = Mock(pid=111)
            new_process = Mock(pid=222)
            preview_runtime._processes["demo"] = {"process": old_process, "port": 3001}
            with patch.object(preview_runtime, "_terminate_tree") as terminate, \
                 patch.object(preview_runtime, "_launch", return_value=new_process) as launch, \
                 patch.object(preview_runtime, "_write_metadata"), \
                 patch.object(preview_runtime, "_wait_ready") as wait_ready:
                preview_runtime._heal("demo", old_process, "http://127.0.0.1:3001/", root,
                                      ["npm", "run", "dev"], {}, log_path, "dev")
            terminate.assert_called_once_with(111)
            launch.assert_called_once()
            self.assertFalse((root / ".next").exists())
            self.assertIs(preview_runtime._processes["demo"]["process"], new_process)
            wait_ready.assert_called_once()
            self.assertEqual(wait_ready.call_args.args[1], new_process)
            self.assertTrue(wait_ready.call_args.args[-1] or wait_ready.call_args.kwargs.get("healed"))

    def test_heal_does_nothing_once_a_newer_preview_has_replaced_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "preview.log"
            log_path.touch()
            old_process = Mock(pid=111)
            preview_runtime._processes["demo"] = {"process": Mock(pid=999), "port": 3001}
            with patch.object(preview_runtime, "_terminate_tree") as terminate, \
                 patch.object(preview_runtime, "_launch") as launch:
                preview_runtime._heal("demo", old_process, "http://127.0.0.1:3001/", root,
                                      ["npm", "run", "dev"], {}, log_path, "dev")
            terminate.assert_not_called()
            launch.assert_not_called()

    def test_wait_ready_heals_a_dev_server_that_died_with_a_corrupted_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "preview.log"
            log_path.write_bytes(b"Error: Cannot find module './611.js'\n")
            process = Mock()
            process.poll.return_value = 1
            with patch.object(preview_runtime, "_heal") as heal:
                preview_runtime._wait_ready("demo", process, "http://127.0.0.1:3001/", root,
                                            ["npm", "run", "dev"], {}, log_path, "dev")
            heal.assert_called_once()

    def test_wait_ready_never_heals_a_production_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log_path = root / "preview.log"
            log_path.write_bytes(b"Error: Cannot find module './611.js'\n")
            process = Mock()
            process.poll.return_value = 1
            with patch.object(preview_runtime, "_heal") as heal, \
                 patch.object(preview_runtime, "status", return_value={}):
                preview_runtime._wait_ready("demo", process, "http://127.0.0.1:3001/", root,
                                            ["npm", "run", "start"], {}, log_path, "start")
            heal.assert_not_called()

    def test_a_preview_that_never_answers_is_shown_as_failed_with_why(self):
        process = Mock()
        process.poll.return_value = None
        preview_runtime._processes["demo"] = {"process": process, "status": "starting", "port": 3100,
                                              "url": "http://127.0.0.1:3100/", "revision": 1}
        with patch.object(preview_runtime.bus, "runtime_state") as announced, \
             patch.object(preview_runtime.bus, "log"):
            preview_runtime._not_answering("demo", process, "http://127.0.0.1:3100/", Path("preview.log"))
        state = preview_runtime.status("demo")
        self.assertEqual(state["status"], "failed")
        self.assertIn("did not answer on http://127.0.0.1:3100/", state["detail"])
        self.assertEqual(announced.call_args.args[1], "failed")

    def test_an_exited_preview_names_the_error_its_output_ended_with(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)
            (record / "preview.log").write_text(
                "> dev\nError: Local development uses a fixed port\n    at file:///scripts/dev-all.mjs:66:9\n",
                encoding="utf-8")
            process = Mock()
            process.poll.return_value = 1
            process.returncode = 1
            preview_runtime._processes["demo"] = {"process": process, "status": "starting", "revision": 1}
            with patch.object(preview_runtime.config, "record_dir", return_value=record), \
                 patch.object(preview_runtime.bus, "runtime_state"):
                state = preview_runtime.status("demo")
        self.assertEqual(state["status"], "failed")
        self.assertIn("exited with code 1", state["detail"])
        self.assertIn("Error: Local development uses a fixed port", state["detail"])

    def test_start_brief_is_the_command_port_and_output_the_studio_uses(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "app"
            (root / "node_modules" / "vite" / "bin").mkdir(parents=True)
            (root / "node_modules" / "vite" / "bin" / "vite.js").write_text("", encoding="utf-8")
            (root / "package.json").write_text(json.dumps(
                {"scripts": {"dev": "vite"}, "devDependencies": {"vite": "5"}}), encoding="utf-8")
            record = Path(directory) / "record"
            record.mkdir()
            (record / "preview.log").write_text("\x1b[31mSyntaxError: Unexpected token\x1b[0m\n", encoding="utf-8")
            with patch.object(preview_runtime.config, "workspace_for", return_value=root), \
                 patch.object(preview_runtime.config, "record_dir", return_value=record), \
                 patch.object(preview_runtime, "_preview_port", return_value=4321), \
                 patch.object(preview_runtime, "_node_program", return_value=r"C:\Program Files\nodejs\node.exe"):
                brief = preview_runtime.start_brief("demo", "Preview exited with code 1.")
        self.assertEqual(brief["command"],
                         "node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4321 --strictPort")
        self.assertTrue(brief["run"].endswith(brief["command"]))
        self.assertIn("4321", brief["run"].split("node node_modules")[0])
        self.assertEqual(brief["url"], "http://127.0.0.1:4321/")
        self.assertEqual(brief["detail"], "Preview exited with code 1.")
        self.assertEqual(brief["log"], "SyntaxError: Unexpected token")
        # Every placeholder of the prompt is filled from the brief.
        text = prompts.load("preview/start", **brief)
        self.assertNotIn("{{", text)
        self.assertIn(brief["run"], text)

    def test_reopening_a_failed_preview_stops_the_one_still_alive_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "package.json").write_text(json.dumps({"scripts": {"dev": "node server.js"}}),
                                               encoding="utf-8")
            alive = Mock()
            alive.poll.return_value = None
            preview_runtime._processes["demo"] = {"process": alive, "status": "failed", "port": 3100,
                                                  "revision": 1}
            stops = []

            def stop(project):
                stops.append(project)
                preview_runtime._processes.pop(project, None)
                return {}

            with patch.object(preview_runtime.config, "workspace_for", return_value=root), \
                 patch.object(preview_runtime.config, "record_dir", return_value=root / ".agentforge"), \
                 patch.object(preview_runtime, "stop", side_effect=stop), \
                 patch.object(preview_runtime, "_preview_port", return_value=3200), \
                 patch.object(preview_runtime, "_launch", return_value=Mock(pid=5, poll=Mock(return_value=None))), \
                 patch.object(preview_runtime, "_write_metadata"), \
                 patch.object(preview_runtime.supabase_connect, "env_for", return_value={}), \
                 patch.object(preview_runtime.deploy_vars, "environment", return_value={}), \
                 patch.object(preview_runtime.bus, "runtime_state"), \
                 patch.object(preview_runtime.threading, "Thread"):
                state = preview_runtime.open_preview("demo")
        self.assertEqual(stops, ["demo"])
        self.assertEqual(state["status"], "starting")
        self.assertEqual(state["port"], 3200)


class StartWithAgentTests(unittest.TestCase):
    """The failed preview's "Start with agent": silent, unplanned, and the Studio reopens it."""

    def _run(self, settled):
        session = Mock()
        session.run_unplanned.return_value = {"text": "The start script demanded a fixed port; it now uses PORT."}
        brief = {"command": "npm run dev", "run": "PORT=4000 npm run dev", "port": 4000,
                 "url": "http://127.0.0.1:4000/", "script": "dev", "detail": "exited", "log": "Error"}
        with patch.object(runs, "session_for", return_value=session), \
             patch.object(runs.preview_runtime, "status", return_value={"detail": "Preview exited with code 1."}), \
             patch.object(runs.preview_runtime, "stop") as stop, \
             patch.object(runs.preview_runtime, "start_brief", return_value=brief) as start_brief, \
             patch.object(runs.preview_runtime, "open_preview") as reopen, \
             patch.object(runs.preview_runtime, "wait_settled", side_effect=settled), \
             patch.object(runs.bus, "agent_msg") as said, \
             patch.object(runs.bus, "user_msg") as user_msg:
            runs._start_preview("demo")
        return session, stop, start_brief, reopen, said, user_msg

    def test_the_agent_starts_it_without_a_plan_or_a_customer_message(self):
        session, stop, start_brief, reopen, said, user_msg = self._run([{"status": "running"}])
        session.begin.assert_called_once_with(runs.PREVIEW_START, role=runs.bus.DEVELOPER)
        session.run_task.assert_not_called()
        prompt = session.run_unplanned.call_args.args[0]
        self.assertIn("PORT=4000 npm run dev", prompt)
        self.assertIn("Do not write a plan", prompt)
        stop.assert_called_once_with("demo")
        start_brief.assert_called_once_with("demo", "Preview exited with code 1.", "")
        reopen.assert_called_once_with("demo")
        user_msg.assert_not_called()
        self.assertIn("now uses PORT", said.call_args.args[1])
        session.finish.assert_called_once()
        session.fail.assert_not_called()

    def test_it_tries_again_then_says_why_it_still_does_not_start(self):
        failed = {"status": "failed", "detail": "The app did not answer within 90 seconds."}
        session, *_ = self._run([failed, failed])
        self.assertEqual(session.run_unplanned.call_count, runs.PREVIEW_START_ROUNDS)
        session.finish.assert_not_called()
        self.assertIn("did not answer within 90 seconds", session.fail.call_args.args[0])

    def test_only_a_built_app_can_be_handed_to_the_agent(self):
        with patch.object(runs.store, "require"), \
             patch.object(runs.builder, "built", return_value=False), \
             self.assertRaises(ValueError):
            runs.preview_start({"type": "preview_start", "project": "demo"})

    def test_one_part_that_is_down_is_started_while_the_rest_keeps_running_then_checked(self):
        session = Mock()
        session.run_unplanned.return_value = {"text": "orders waited for a database that never answered; it now times out."}
        brief = {"command": "npm run dev", "run": "npm run dev", "port": 4900, "url": "u", "script": "dev", "detail": "d",
                 "log": "l", "part": "orders", "part_kind": "service", "part_port": 4003, "part_cwd": "packages/orders",
                 "part_command": "node src/server.js", "part_run": "Set-Location 'packages/orders'; node src/server.js",
                 "part_log": "[orders] connecting…"}
        with patch.object(runs, "session_for", return_value=session), \
             patch.object(runs.preview_runtime, "status", return_value={"detail": ""}), \
             patch.object(runs.preview_runtime, "stop") as stop, \
             patch.object(runs.preview_runtime, "start_brief", return_value=brief) as start_brief, \
             patch.object(runs.preview_runtime, "reopen") as reopen, \
             patch.object(runs.preview_runtime, "wait_settled", return_value={"status": "running"}), \
             patch.object(runs.preview_runtime, "wait_part", return_value=True) as wait_part, \
             patch.object(runs.bus, "agent_msg") as said:
            runs._start_preview("demo", "", "orders")
        stop.assert_not_called()                                   # the other parts keep running meanwhile
        start_brief.assert_called_once_with("demo", "", "orders")
        prompt = session.run_unplanned.call_args.args[0]
        self.assertIn("**orders** (service) should answer on port 4003", prompt)
        self.assertIn("Set-Location 'packages/orders'; node src/server.js", prompt)
        self.assertNotIn("{{", prompt)
        reopen.assert_called_once_with("demo")
        self.assertEqual(wait_part.call_args.args[:2], ("demo", "orders"))
        self.assertIn("now times out", said.call_args.args[1])
        session.finish.assert_called_once()

    def test_the_part_a_browser_opens_is_started_as_the_whole_app(self):
        ports = {"ports": [{"name": "client", "main": True}, {"name": "orders", "main": False}]}
        with patch.object(runs.store, "require"), patch.object(runs.builder, "built", return_value=True), \
             patch.object(runs.preview_runtime, "ports", return_value=ports), \
             patch.object(runs, "_in_background") as background:
            self.assertEqual(runs.preview_start({"project": "demo", "part": "client"})["part"], "")
            self.assertEqual(runs.preview_start({"project": "demo", "part": "orders"})["part"], "orders")
            with self.assertRaisesRegex(ValueError, "no part called"):
                runs.preview_start({"project": "demo", "part": "nope"})
        self.assertEqual(background.call_args.args[-1], "orders")


class PortsTests(unittest.TestCase):
    """What the Ports view shows: each part the app's runner listed, and whether it listens."""

    def setUp(self):
        preview_runtime._processes.clear()  # noqa: SLF001
        preview_runtime._last.clear()  # noqa: SLF001
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.record = Path(self.temp.name)
        for item in (patch.object(preview_runtime.config, "record_dir", return_value=self.record),
                     patch.object(preview_runtime.config, "workspace_for", return_value=self.record)):
            item.start()
            self.addCleanup(item.stop)

    def _declare(self, runtime="r1"):
        (self.record / "ports.json").write_text(json.dumps({"written_at": "2026-10-02T10:00:00Z", "runtime": runtime, "ports": [
            {"name": "client", "kind": "client", "port": 4900, "cwd": "client", "command": "node vite-dev.mjs"},
            {"name": "gateway", "kind": "gateway", "port": 4000, "cwd": "packages/gateway", "command": "node src/server.js",
             "env": {"PORT": "4000"}},
            {"name": "orders", "kind": "service", "port": 4003, "cwd": "packages/orders", "command": "node src/server.js",
             "env": {"PORT": "4003", "GATEWAY_URL": "http://127.0.0.1:4000"}},
        ]}), encoding="utf-8")

    def test_each_listed_part_says_whether_it_listens_and_the_browser_port_is_marked(self):
        self._declare()
        with patch.object(preview_runtime, "status", return_value={"status": "running", "url": "http://127.0.0.1:4900/",
                                                                     "port": 4900, "detail": ""}), \
             patch.object(preview_runtime, "_read_metadata", return_value={"runtimeId": "r1"}), \
             patch.object(preview_runtime, "_listeners", return_value={4900: 11, 4000: 12}):
            view = preview_runtime.ports("demo")
        rows = {row["name"]: row for row in view["ports"]}
        self.assertEqual(list(rows), ["client", "gateway", "orders"])
        self.assertTrue(rows["client"]["main"] and rows["client"]["listening"])
        self.assertEqual((rows["gateway"]["listening"], rows["gateway"]["pid"]), (True, 12))
        self.assertEqual((rows["orders"]["listening"], rows["orders"]["url"]), (False, "http://127.0.0.1:4003/"))
        self.assertTrue(view["current"])

    def test_a_single_server_app_is_its_own_preview_port(self):
        with patch.object(preview_runtime, "status", return_value={"status": "stopped", "url": "", "port": 0, "detail": ""}), \
             patch.object(preview_runtime, "_listeners", return_value={}):
            view = preview_runtime.ports("demo")
        self.assertEqual([(row["name"], row["main"], row["listening"]) for row in view["ports"]], [("app", True, False)])

    def test_the_agent_is_told_how_that_one_part_is_run_alone(self):
        self._declare()
        (self.record / "package.json").write_text(json.dumps({"scripts": {"dev": "node scripts/dev-all.mjs"}}), encoding="utf-8")
        (self.record / "preview.log").write_text("[gateway] listening\n[orders] connecting to the database…\n", encoding="utf-8")
        with patch.object(preview_runtime, "status", return_value={"status": "running", "url": "", "port": 4900, "detail": ""}):
            brief = preview_runtime.start_brief("demo", "", "orders")
        self.assertEqual((brief["part_port"], brief["part_cwd"]), (4003, "packages/orders"))
        self.assertIn("node src/server.js", brief["part_run"])
        self.assertIn("4003", brief["part_run"])
        self.assertIn("packages/orders", brief["part_run"])
        self.assertEqual(brief["part_log"], "[orders] connecting to the database…")
        self.assertNotIn("{{", prompts.load("preview/start-part", **brief))
        with self.assertRaisesRegex(ValueError, "no part called"):
            preview_runtime.start_brief("demo", "", "billing")


if __name__ == "__main__":
    unittest.main()
