"""The desktop app's backend: no ports. Requests and the live feed over stdin/stdout, the live E2E view through a
folder, a sign-in callback answered only while it is waited for, and the user's data outside the app."""
from __future__ import annotations

import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import bus, config, httpd, live, oauth_listener, stdio_bridge  # noqa: E402


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class RespondTests(unittest.TestCase):
    def test_one_answer_whichever_way_the_request_came(self):
        self.assertEqual(httpd.respond("GET", "/nowhere")[0], 404)
        with mock.patch.object(httpd, "dispatch", side_effect=ValueError("bad input")):
            self.assertEqual(httpd.respond("POST", "/x")[:2], (400, {"error": "bad input"}))
        with mock.patch.object(httpd, "dispatch", return_value=httpd.Raw(b"%PDF", "application/pdf", "a.pdf")):
            self.assertEqual(httpd.respond("GET", "/x"), (200, b"%PDF", "application/pdf", "a.pdf"))
        with mock.patch.object(httpd, "dispatch", return_value=None):
            self.assertEqual(httpd.respond("GET", "/x")[1], {"ok": True})


class BridgeTests(unittest.TestCase):
    def run_bridge(self, *messages: dict) -> list[dict]:
        reader = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        writer = io.StringIO()
        unsubscribe = []
        real_subscribe = bus.subscribe
        with mock.patch.object(bus, "subscribe", side_effect=lambda fn: unsubscribe.append(real_subscribe(fn))):
            stdio_bridge.Bridge(reader, writer).serve()
        for cancel in unsubscribe:
            cancel()
        return [json.loads(line) for line in writer.getvalue().splitlines()]

    def test_requests_files_feed_messages_and_pings_are_answered_over_the_streams(self):
        def route(method, path, body=None, query=None):
            if path == "/file":
                return httpd.Raw(b"\x00\x01binary", "application/pdf", "report.pdf")
            return {"method": method, "path": path, "body": body, "query": query}

        with mock.patch.object(httpd, "dispatch", side_effect=route), \
             mock.patch("server_modules.runs.handle") as handle:
            out = self.run_bridge(
                {"type": "request", "id": "1", "method": "POST", "path": "/settings", "body": {"a": 1}, "query": {"q": "x"}},
                {"type": "request", "id": "2", "method": "GET", "path": "/file"},
                {"type": "feed", "message": {"type": "agent_update", "project": "p"}},
                {"type": "ping"},
                "not json at all" and {"type": "unknown"},
            )
        self.assertEqual(out[0], {"type": "ready", "protocol": stdio_bridge.PROTOCOL})
        replies = {m["id"]: m for m in out if m["type"] == "response"}
        self.assertEqual(replies["1"]["json"], {"method": "POST", "path": "/settings", "body": {"a": 1}, "query": {"q": "x"}})
        self.assertEqual(replies["2"]["contentType"], "application/pdf")
        self.assertEqual(replies["2"]["filename"], "report.pdf")
        self.assertEqual(replies["2"]["base64"], "AAFiaW5hcnk=")
        handle.assert_called_once_with({"type": "agent_update", "project": "p"})
        self.assertIn({"type": "pong"}, out)

    def test_every_bus_event_reaches_the_app_and_a_failing_feed_message_becomes_one(self):
        with mock.patch("server_modules.runs.handle", side_effect=ValueError("no handler for that")):
            out = self.run_bridge({"type": "feed", "message": {"type": "odd", "project": "prj_bridge_test"}})
        events = [m["event"] for m in out if m["type"] == "event"]
        self.assertTrue(any(e.get("type") == "error" and "no handler" in e.get("text", "") for e in events))
        bus.forget("prj_bridge_test")

    def test_the_real_backend_answers_over_stdio_and_listens_on_nothing(self):
        with tempfile.TemporaryDirectory() as data, tempfile.TemporaryDirectory() as work:
            env = {**os.environ, "AGENTFORGE_DATA": data, "AGENTFORGE_WORKSPACES": work,
                   "PYTHONPATH": os.pathsep.join([str(ROOT / ".deps"), str(ROOT / "src")])}
            proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "server.py"), "--stdio"], cwd=ROOT, env=env,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True, encoding="utf-8")
            try:
                self.assertEqual(json.loads(proc.stdout.readline())["type"], "ready")
                proc.stdin.write(json.dumps({"type": "request", "id": "a", "method": "GET", "path": "/projects"}) + "\n")
                proc.stdin.flush()
                answer = json.loads(proc.stdout.readline())
                self.assertEqual((answer["id"], answer["status"], answer["json"]), ("a", 200, []))
                listening = subprocess.run(["netstat", "-ano", "-p", "tcp"] if os.name == "nt" else ["true"],
                                           capture_output=True, text=True).stdout
                self.assertFalse([line for line in listening.splitlines()
                                  if "LISTENING" in line and line.split()[-1] == str(proc.pid)])
                self.assertTrue((Path(data) / "state").is_dir())       # the user's data, outside the app
            finally:
                proc.stdin.close()
                proc.wait(timeout=20)
                proc.stdout.close()
            self.assertEqual(proc.returncode, 0)


class LiveFolderTests(unittest.TestCase):
    def test_without_a_port_a_run_drops_its_messages_into_a_watched_folder(self):
        with tempfile.TemporaryDirectory() as directory, \
             mock.patch.object(config, "TRANSPORT", "stdio"), \
             mock.patch.object(config, "record_dir", return_value=Path(directory)), \
             mock.patch.object(live, "handle") as handle:
            channel = live.channel_for("prj_live_test")
            folder = Path(channel["AGENTFORGE_LIVE_DIR"])
            self.assertNotIn("AGENTFORGE_LIVE_URL", channel)
            (folder / "000000000000001-0000000.json").write_text(json.dumps({"kind": "event", "n": 1}), encoding="utf-8")
            (folder / "000000000000002-0000001.json").write_text(json.dumps({"kind": "end"}), encoding="utf-8")
            end = time.time() + 5
            while time.time() < end and handle.call_count < 2:
                time.sleep(0.05)
            self.assertEqual([c.args[1]["kind"] for c in handle.call_args_list], ["event", "end"])   # in order
            self.assertFalse(list(folder.glob("0*.json")))
            self.assertTrue((folder / "watching.json").is_file())

    def test_with_the_api_listening_a_run_posts_to_it(self):
        with mock.patch.object(config, "TRANSPORT", "http"):
            self.assertIn("/live/prj_x", live.channel_for("prj_x")["AGENTFORGE_LIVE_URL"])


class SignInCallbackTests(unittest.TestCase):
    def test_the_callback_is_answered_once_then_the_port_closes(self):
        port = free_port()
        with mock.patch.object(config, "TRANSPORT", "stdio"), mock.patch.object(config, "API_PORT", port), \
             mock.patch.object(httpd, "respond", return_value=(200, b"signed in", "text/html", "")) as respond:
            oauth_listener.open_for("/supabase-oauth/callback", 10)
            self.assertTrue(oauth_listener.is_open())
            with self.assertRaises(Exception):
                urllib.request.urlopen(f"http://127.0.0.1:{port}{config.API_PREFIX}/projects", timeout=5)
            page = urllib.request.urlopen(
                f"http://127.0.0.1:{port}{config.API_PREFIX}/supabase-oauth/callback?code=c&state=s", timeout=5).read()
            self.assertEqual(page, b"signed in")
            self.assertEqual(respond.call_args.args[:2], ("GET", "/supabase-oauth/callback"))
            end = time.time() + 5
            while time.time() < end and oauth_listener.is_open():
                time.sleep(0.05)
            self.assertFalse(oauth_listener.is_open())

    def test_the_http_backend_needs_no_extra_listener(self):
        with mock.patch.object(config, "TRANSPORT", "http"):
            oauth_listener.open_for("/supabase-oauth/callback", 10)
            self.assertFalse(oauth_listener.is_open())


class ReleaseStageTests(unittest.TestCase):
    def test_every_file_the_backend_reads_is_in_the_release(self):
        """An installed app once failed every specification: the SRS catalogues were left out of the zip."""
        import re

        from server_modules.validation import corpus
        from srs_agent import document

        script = (ROOT / "release" / "build.ps1").read_text(encoding="utf-8")
        listed = re.search(r"foreach \(\$folder in (.+?)\) \{", script, re.DOTALL).group(1)
        staged = {name.replace("\\", "/") for name in re.findall(r"'([^']+)'", listed)}
        for needed in (corpus.CATALOG, document._NOTATION_CATALOG):  # noqa: SLF001 - the paths themselves
            relative = needed.resolve().relative_to(ROOT).as_posix()
            self.assertTrue(any(relative.startswith(folder + "/") for folder in staged),
                            f"{relative} is not copied into the release (release/build.ps1)")


if __name__ == "__main__":
    unittest.main()
