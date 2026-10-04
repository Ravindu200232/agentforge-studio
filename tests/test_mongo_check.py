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
        with mock.patch.dict(os.environ, {**clean, **env}, clear=True):
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
