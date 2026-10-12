"""The connection check (server_modules/scripts/mongo-ping.mjs) on a computer whose own DNS server is unreliable.

A home router often fails an SRV lookup once, or never answers it. That used to be reported as "check the host name in
the string" for a string that was fine. The check now asks again, then asks public DNS, and only blames the host name
when public DNS agrees it does not exist.
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import mongo_check  # noqa: E402

REAL_HOST_URI = "mongodb+srv://someone:not-a-real-password@cluster0.3xjuesg.mongodb.net/app?retryWrites=true&w=majority"
NO_SUCH_HOST_URI = "mongodb+srv://someone:not-a-real-password@no-such-cluster-xyz.mongodb.net/app"
DEAD_DNS = "127.0.0.1:9"        # nothing listens here: the lookup is refused at once


def public_dns_answers() -> bool:
    """Whether a public DNS server answers a question from here (the tests that need the internet are skipped without it).
    Some networks block one of the two the check falls back to, so either will do."""
    query = bytes.fromhex("1234010000010000000000000765786d706c6503636f6d0000010001")
    for server in ("1.1.1.1", "8.8.8.8"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(3)
                sock.sendto(query, (server, 53))
                if sock.recv(512):
                    return True
        except OSError:
            continue
    return False


@unittest.skipUnless(shutil.which("node"), "node is needed to run the check")
class FlakyDnsTests(unittest.TestCase):
    def check(self, uri: str, **env: str) -> dict:
        clean = {k: v for k, v in os.environ.items() if k not in ("CHECK_DNS_SERVERS", "CHECK_PUBLIC_DNS_SERVERS")}
        # These tests are about finding the host, with a made-up password: with a MongoDB driver on this computer (any project
        # that was built here installed one) the check goes on to the password and, rightly, refuses it. No driver, as on a clean one.
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True), mock.patch.object(mongo_check, "_driver_base", lambda: ""):
            return mongo_check.check(uri)

    def test_no_dns_server_answering_at_all_is_said_to_be_a_connection_problem_not_a_wrong_host(self):
        result = self.check(REAL_HOST_URI, CHECK_DNS_SERVERS=DEAD_DNS, CHECK_PUBLIC_DNS_SERVERS=DEAD_DNS)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "dns")
        self.assertIn("could not be looked up", result["message"])
        self.assertIn("internet connection", result["message"])
        self.assertNotIn("host name", result["message"])

    def test_the_message_never_contains_the_connection_string_or_its_password(self):
        result = self.check(REAL_HOST_URI, CHECK_DNS_SERVERS=DEAD_DNS, CHECK_PUBLIC_DNS_SERVERS=DEAD_DNS)
        self.assertNotIn("not-a-real-password", str(result))

    @unittest.skipUnless(public_dns_answers(), "public DNS is not reachable from here")
    def test_a_dead_local_dns_server_falls_back_to_public_dns_and_says_so(self):
        result = self.check(REAL_HOST_URI, CHECK_DNS_SERVERS=DEAD_DNS)
        self.assertTrue(result["ok"], result)
        self.assertTrue(any("public DNS" in note for note in result["warnings"]), result)

    @unittest.skipUnless(public_dns_answers(), "public DNS is not reachable from here")
    def test_a_host_that_public_dns_also_cannot_find_is_still_called_wrong(self):
        result = self.check(NO_SUCH_HOST_URI)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "dns")
        self.assertIn("public DNS could not find it either", result["message"])
        self.assertIn("Check the host name", result["message"])
        # A name that does not exist anywhere is, for an Atlas cluster, most often one that is paused.
        self.assertIn("may be paused", result["message"])
        self.assertIn("resume it in Atlas", result["message"])

    @unittest.skipUnless(public_dns_answers(), "public DNS is not reachable from here")
    def test_a_working_dns_server_changes_nothing(self):
        result = self.check(REAL_HOST_URI)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["warnings"], [])


@unittest.skipUnless(shutil.which("node"), "node is needed to run the check")
class WhatTheCheckSaysTests(unittest.TestCase):
    """The words the check gives back arrive as written, and a refused login says what can be done about it."""

    def run_script(self, body: str):
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "ping.mjs"
            script.write_text(body, encoding="utf-8")
            with mock.patch.object(mongo_check, "SCRIPT", script),                     mock.patch.object(mongo_check.deploy_vars, "check_database_uri", lambda uri, allow_local=False: uri):
                return mongo_check.check("mongodb+srv://u:pw@c.mongodb.net/app")

    ARROW = ("console.log(JSON.stringify({ok: false, stage: 'auth', message: "
             "'The cluster answered but refused the username or password. Check the database user in Atlas → Database Access.'}))")

    def test_an_arrow_in_the_message_is_not_turned_into_garbage_on_windows(self):
        with mock.patch("server_modules.mongo_connect.can_repair", return_value=False):
            result = self.run_script(self.ARROW)
        self.assertIn("Atlas → Database Access", result["message"])
        self.assertNotIn("â", result["message"])                       # what the arrow became when read as Windows-1252

    def test_a_refused_login_the_studio_can_mend_says_so_and_flags_it(self):
        with mock.patch("server_modules.mongo_connect.can_repair", return_value=True):
            result = self.run_script(self.ARROW)
        self.assertTrue(result["repairable"])
        self.assertIn("Fix the connection", result["message"])

    def test_one_it_cannot_mend_is_not_flagged_and_adds_nothing(self):
        with mock.patch("server_modules.mongo_connect.can_repair", return_value=False):
            result = self.run_script(self.ARROW)
        self.assertFalse(result["repairable"])
        self.assertNotIn("Fix the connection", result["message"])

    def test_the_results_are_read_as_utf8_whatever_the_computers_own_encoding_is(self):
        source = (ROOT / "server_modules" / "mongo_check.py").read_text(encoding="utf-8")
        self.assertIn('encoding="utf-8"', source)


@unittest.skipUnless(shutil.which("node"), "node is needed to run the script")
class InspectingAnAddressThatIsGoneTests(unittest.TestCase):
    """The Database tab reads through the application's own driver; a paused Atlas cluster has no address to connect to."""

    def inspect(self, failure: str) -> dict:
        import json
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as folder:
            driver = Path(folder) / "node_modules" / "mongodb"
            driver.mkdir(parents=True)
            (driver / "package.json").write_text('{"name":"mongodb","main":"index.js"}', encoding="utf-8")
            (driver / "index.js").write_text(
                "exports.MongoClient = class { async connect() { throw new Error(%s) } async close() {} }" % json.dumps(failure),
                encoding="utf-8")
            (Path(folder) / "package.json").write_text("{}", encoding="utf-8")
            script = ROOT / "server_modules" / "scripts" / "mongo-inspect.mjs"
            done = subprocess.run(["node", str(script), "overview"], capture_output=True, text=True, timeout=60,
                                  env={**os.environ, "CHECK_URI": "mongodb+srv://u:not-a-real-password@gone.example.mongodb.net/app",
                                       "DRIVER_BASE": folder})
        return json.loads(done.stdout.strip().splitlines()[-1])

    def test_an_address_that_does_not_exist_says_the_cluster_may_be_paused(self):
        result = self.inspect("querySrv ENOTFOUND _mongodb._tcp.gone.example.mongodb.net")
        self.assertFalse(result["ok"])
        self.assertTrue(result["message"].startswith("The database could not be read: querySrv ENOTFOUND"), result)
        self.assertIn("may be paused", result["message"])
        self.assertIn("choose another cluster", result["message"])

    def test_another_failure_gets_no_such_guess(self):
        result = self.inspect("connection timed out")
        self.assertEqual(result["message"], "The database could not be read: connection timed out")
        self.assertNotIn("paused", result["message"])

    def test_the_password_never_reaches_the_message(self):
        result = self.inspect("querySrv ENOTFOUND for not-a-real-password")
        self.assertNotIn("not-a-real-password", str(result))


if __name__ == "__main__":
    unittest.main()
