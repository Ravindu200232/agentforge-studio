"""Parallel project previews and the live browser that shows a test run in them."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "builder-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, live, preview_runtime, supabase_connect  # noqa: E402


class FakeProcess:
    _next = 1000
    environments: list[dict] = []
    commands: list[list[str]] = []

    def __init__(self, *args, **kwargs):
        FakeProcess._next += 1
        FakeProcess.environments.append(kwargs.get("env") or {})
        FakeProcess.commands.append(args[0])
        self.pid = FakeProcess._next
        self.returncode = None

    def poll(self):
        return self.returncode


class PreviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.terminated: list[int] = []
        self.events: list[tuple] = []
        for name in ("alpha", "beta"):
            workspace = self.root / name
            (workspace / ".agentforge").mkdir(parents=True)
            (workspace / "package.json").write_text(json.dumps({"scripts": {"dev": "x", "start": "y"}}))
        preview_runtime._processes.clear()
        preview_runtime._last.clear()
        self.open_ports: set[int] = set()

        def terminate(pid):
            self.terminated.append(pid)

        patches = [
            mock.patch.object(preview_runtime.config, "workspace_for", lambda project: self.root / project),
            mock.patch.object(preview_runtime.config, "record_dir", lambda project: self.root / project / ".agentforge"),
            mock.patch.object(preview_runtime.subprocess, "Popen", FakeProcess),
            mock.patch.object(preview_runtime, "_terminate_tree", terminate),
            mock.patch.object(preview_runtime, "_wait_ready", lambda *a, **k: None),
            mock.patch.object(preview_runtime, "_listening_pids", lambda port: []),
            mock.patch.object(preview_runtime, "_port_open", lambda port: port in self.open_ports),
            mock.patch.object(preview_runtime.bus, "runtime_state", lambda *a, **k: self.events.append(a)),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_opening_another_project_keeps_the_first_preview_running(self):
        first = preview_runtime.open_preview("alpha")
        self.assertEqual(first["status"], "starting")
        alpha_pid = preview_runtime._processes["alpha"]["process"].pid

        second = preview_runtime.open_preview("beta")
        self.assertEqual(second["status"], "starting")
        self.assertNotEqual(first["port"], second["port"])
        self.assertEqual(preview_runtime._processes["alpha"]["process"].pid, alpha_pid)
        self.assertEqual(set(preview_runtime._processes), {"alpha", "beta"})
        self.assertEqual(self.terminated, [])

    def test_stopping_one_project_leaves_the_other_preview_running(self):
        first = preview_runtime.open_preview("alpha")
        preview_runtime.open_preview("beta")
        alpha_pid = preview_runtime._processes["alpha"]["process"].pid
        beta_pid = preview_runtime._processes["beta"]["process"].pid

        stopped = preview_runtime.stop("beta")

        self.assertEqual(stopped["status"], "stopped")
        self.assertEqual(stopped["project"], "beta")
        self.assertEqual(first["port"], preview_runtime._processes["alpha"]["port"])
        self.assertNotIn("beta", preview_runtime._processes)
        self.assertIn(beta_pid, self.terminated)
        self.assertNotIn(alpha_pid, self.terminated)

    def test_reopening_the_project_on_screen_keeps_its_running_preview(self):
        preview_runtime.open_preview("alpha")
        preview_runtime._processes["alpha"]["status"] = "running"
        self.open_ports.add(preview_runtime._processes["alpha"]["port"])
        pid = preview_runtime._processes["alpha"]["process"].pid
        again = preview_runtime.open_preview("alpha")
        self.assertEqual(again["status"], "running")
        self.assertEqual(preview_runtime._processes["alpha"]["process"].pid, pid)   # not restarted
        self.assertEqual(self.terminated, [])

    def test_vite_stack_preview_uses_a_private_dynamic_port(self):
        manifest = self.root / "alpha" / "package.json"
        manifest.write_text(json.dumps({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "6.0.0"}}))
        FakeProcess.environments.clear()
        state = preview_runtime.open_preview("alpha")
        self.assertGreaterEqual(state["port"], preview_runtime.PREVIEW_PORT_FIRST)
        self.assertLessEqual(state["port"], preview_runtime.PREVIEW_PORT_LAST)
        self.assertEqual(state["url"], f"http://127.0.0.1:{state['port']}/")
        self.assertEqual(FakeProcess.environments[-1]["PORT"], str(state["port"]))
        self.assertEqual(FakeProcess.environments[-1]["HOST"], "127.0.0.1")
        self.assertNotIn("VITE_PORT", FakeProcess.environments[-1])

    def test_remix_preview_does_not_take_nextjs_port(self):
        manifest = self.root / "alpha" / "package.json"
        manifest.write_text(json.dumps({"scripts": {"dev": "remix vite:dev"},
                                        "dependencies": {"@remix-run/serve": "2"}}))
        state = preview_runtime.open_preview("alpha")
        self.assertGreaterEqual(state["port"], preview_runtime.PREVIEW_PORT_FIRST)
        self.assertEqual(FakeProcess.environments[-1]["PORT"], str(state["port"]))
        self.assertNotIn("VITE_PORT", FakeProcess.environments[-1])

    def test_a_project_restarts_its_own_preview_when_its_framework_changes(self):
        manifest = self.root / "alpha" / "package.json"
        manifest.write_text(json.dumps({"scripts": {"dev": "vite"}, "devDependencies": {"vite": "6.0.0"}}))
        first = preview_runtime.open_preview("alpha")
        preview_runtime._processes["alpha"]["status"] = "running"
        old = preview_runtime._processes["alpha"]["process"].pid
        self.open_ports.add(first["port"])
        manifest.write_text(json.dumps({"scripts": {"dev": "next dev"}, "dependencies": {"next": "15.0.0"}}))
        state = preview_runtime.open_preview("alpha")
        self.assertIn(old, self.terminated)
        self.assertNotEqual(state["port"], first["port"])

    def test_unavailable_port_returns_failed_state_instead_of_http_error(self):
        with mock.patch.object(preview_runtime, "_port_open", return_value=True), \
             mock.patch.object(preview_runtime.bus, "log"):
            state = preview_runtime.open_preview("alpha")
        self.assertEqual(state["status"], "failed")
        self.assertIn("No private preview port", state["detail"])

    def test_a_preview_whose_port_stopped_answering_is_started_again(self):
        preview_runtime.open_preview("alpha")
        preview_runtime._processes["alpha"]["status"] = "running"      # ... but nothing listens on the port
        pid = preview_runtime._processes["alpha"]["process"].pid
        preview_runtime.open_preview("alpha")
        self.assertIn(pid, self.terminated)
        self.assertNotEqual(preview_runtime._processes["alpha"]["process"].pid, pid)

    def test_the_dev_server_is_replaced_once_a_production_build_exists(self):
        preview_runtime.open_preview("alpha")
        self.assertEqual(preview_runtime._processes["alpha"]["script"], "dev")
        preview_runtime._processes["alpha"]["status"] = "running"
        self.open_ports.add(preview_runtime._processes["alpha"]["port"])
        (self.root / "alpha" / ".next").mkdir()
        (self.root / "alpha" / ".next" / "BUILD_ID").write_text("x")
        preview_runtime.open_preview("alpha")
        self.assertEqual(preview_runtime._processes["alpha"]["script"], "start")

    def test_a_finished_build_is_served_by_a_fresh_process(self):
        preview_runtime.open_preview("alpha")
        preview_runtime._processes["alpha"]["status"] = "running"
        self.open_ports.add(preview_runtime._processes["alpha"]["port"])
        old = preview_runtime._processes["alpha"]["process"].pid
        preview_runtime.reopen("alpha")
        self.assertIn(old, self.terminated)
        self.assertNotEqual(preview_runtime._processes["alpha"]["process"].pid, old)

    def test_the_preview_process_is_started_with_the_frame_hook(self):
        FakeProcess.environments.clear()
        preview_runtime.open_preview("alpha")
        options = FakeProcess.environments[-1]["NODE_OPTIONS"]
        self.assertIn("--require", options)
        self.assertIn(preview_runtime.FRAME_HOOK.as_posix(), options)
        self.assertTrue(preview_runtime.FRAME_HOOK.is_file())

    def test_preview_gets_its_own_supabase_environment(self):
        FakeProcess.environments.clear()
        with mock.patch.object(supabase_connect, "env_for", return_value={
                "NEXT_PUBLIC_SUPABASE_URL": "https://example.supabase.co",
                "NEXT_PUBLIC_SUPABASE_ANON_KEY": "anon-key"}) as env_for:
            preview_runtime.open_preview("alpha")
        env_for.assert_called_once_with("alpha")
        self.assertEqual(FakeProcess.environments[-1]["NEXT_PUBLIC_SUPABASE_URL"],
                         "https://example.supabase.co")

    def test_a_project_with_nothing_built_leaves_the_running_preview_alone(self):
        preview_runtime.open_preview("alpha")
        (self.root / "beta" / "package.json").unlink()
        state = preview_runtime.open_preview("beta")
        self.assertEqual(state["status"], "stopped")
        self.assertEqual(list(preview_runtime._processes), ["alpha"])
        self.assertEqual(self.terminated, [])


class FrameHookTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "node is needed to run the hook")
    def test_the_hook_lets_this_machine_frame_an_app_that_forbids_framing(self):
        script = (
            "const http=require('node:http');"
            "const s=http.createServer((q,r)=>{r.setHeader('X-Frame-Options','DENY');"
            "r.setHeader('Content-Security-Policy',\"default-src 'self'; frame-ancestors 'none'\");r.end('x')})"
            ".listen(0,async()=>{const r=await fetch('http://127.0.0.1:'+s.address().port);"
            "console.log(JSON.stringify([r.headers.get('x-frame-options'),r.headers.get('content-security-policy')]));s.close()})")
        for hook, expect_open in (([], False), (["--require", str(preview_runtime.FRAME_HOOK)], True)):
            done = subprocess.run(["node", *hook, "-e", script], capture_output=True, text=True, timeout=30)
            frame_options, policy = json.loads(done.stdout)
            self.assertEqual(frame_options is None, expect_open)
            self.assertEqual("http://localhost:*" in policy, expect_open)
            self.assertEqual("'none'" in policy, not expect_open)


class LiveBrowserTests(unittest.TestCase):
    def setUp(self):
        self.seen: list[dict] = []
        self.addCleanup(bus.subscribe(self.seen.append))
        live._active.clear()

    def test_a_frame_reaches_the_studio_but_is_not_kept_in_the_history(self):
        before = len(bus.history("live-test-project"))
        live.handle("live-test-project", {"kind": "frame", "frame": "data:image/jpeg;base64,AAAA",
                                           "url": "http://localhost/x", "viewport": {"width": 800, "height": 600}})
        frame = next(e for e in self.seen if e["type"] == "browser_frame")
        self.assertEqual(frame["frame"], "data:image/jpeg;base64,AAAA")
        self.assertEqual((frame["viewport"]["width"], frame["agent"]), (800, bus.DEVELOPER))
        self.assertEqual(len(bus.history("live-test-project")), before)

    def test_anything_that_is_not_a_picture_or_is_huge_is_dropped(self):
        live.handle("p", {"kind": "frame", "frame": "javascript:alert(1)"})
        live.handle("p", {"kind": "frame", "frame": "data:image/jpeg;base64," + "A" * live.MAX_FRAME_CHARS})
        self.assertEqual(self.seen, [])

    def test_a_test_frame_says_it_is_a_test_and_brings_the_pages_own_background(self):
        live.handle("p", {"kind": "frame", "frame": "data:image/jpeg;base64,AAAA", "bg": "rgb(250, 250, 250)"})
        frame = next(e for e in self.seen if e["type"] == "browser_frame")
        self.assertEqual((frame["kind"], frame["bg"]), ("test", "rgb(250, 250, 250)"))
        live.handle("p", {"kind": "frame", "frame": "data:image/jpeg;base64,AAAA", "bg": "url(http://evil)"})
        self.assertEqual(self.seen[-1]["bg"], "")                          # only a colour is passed on

    def test_the_pointer_arrives_on_its_own_with_the_element_it_is_using(self):
        live.handle("p", {"kind": "cursor", "bg": "white", "cursor": {
            "x": 40, "y": 60, "action": "click", "box": {"x": 30, "y": 50, "width": 100, "height": 32}}})
        row = next(e for e in self.seen if e["type"] == "browser_cursor")
        self.assertEqual((row["cursor"]["x"], row["cursor"]["action"]), (40.0, "click"))
        self.assertEqual(row["cursor"]["box"]["width"], 100.0)
        before = len(self.seen)
        live.handle("p", {"kind": "cursor", "cursor": {"x": "left", "y": 1}})       # not a position
        live.handle("p", {"kind": "cursor", "cursor": {"x": 1, "y": 1, "action": "rm -rf"}})
        self.assertEqual(len(self.seen), before + 1)
        self.assertEqual(self.seen[-1]["cursor"]["action"], "move")         # an unknown action is just a move

    def test_the_steps_of_a_run_arrive_with_their_progress(self):
        live.handle("p", {"kind": "event", "state": "journey_start", "title": "adds an item", "index": 2, "total": 9,
                          "secret": "not passed on"})
        row = next(e for e in self.seen if e["type"] == "e2e_event")
        self.assertEqual((row["title"], row["index"], row["total"]), ("adds an item", 2, 9))
        self.assertNotIn("secret", row)

    def test_the_end_of_a_run_gives_the_preview_back_once(self):
        live.handle("p", {"kind": "frame", "frame": "data:image/png;base64,AAAA"})
        live.handle("p", {"kind": "end"})
        live.handle("p", {"kind": "end"})                       # nothing more is live: silent
        live.finish("p")
        types = [e["type"] for e in self.seen]
        self.assertEqual(types.count("e2e_done"), 1)
        cleared = [e for e in self.seen if e["type"] == "browser_frame" and e["frame"] is None]
        self.assertEqual(len(cleared), 1)

    def test_finishing_a_command_that_streamed_nothing_says_nothing(self):
        live.finish("quiet-project")
        self.assertEqual(self.seen, [])

    def test_a_run_is_told_whether_anyone_is_watching(self):
        try:
            bus.set_viewer_count(lambda: 2)
            self.assertEqual(live.handle("p", {"kind": "hello"}), {"ok": True, "watching": True})
            bus.set_viewer_count(lambda: 0)
            self.assertEqual(live.handle("p", {"kind": "hello"}), {"ok": True, "watching": False})
            bus.set_viewer_count(lambda: 1 / 0)                   # a broken counter never stops a run
            self.assertTrue(live.handle("p", {"kind": "hello"})["watching"])
        finally:
            bus.set_viewer_count(lambda: 1)

    def test_commands_are_told_where_to_stream(self):
        self.assertTrue(live.url_for("prj_1").endswith("/__agentforge/api/live/prj_1"))


if __name__ == "__main__":
    unittest.main()
