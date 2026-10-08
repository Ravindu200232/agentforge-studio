"""Signing in through the deployment providers' own command line tools."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import cli_signin, config, httpd, routes_deploy  # noqa: E402

GH_STATUS = """github.com
  ✓ Logged in to github.com account octocat (keyring)
  - Active account: true
  - Git operations protocol: https
  - Token: gho_************************************
  - Token scopes: 'gist', 'read:org', 'repo'
"""


class FakeProcess:
    """A login that prints what a real one prints, then finishes when told to."""

    def __init__(self, lines, exit_code=0):
        self.stdout = iter(l + "\n" for l in lines)
        self.returncode = None
        self._exit = exit_code
        self.pid = 4242
        self.typed = []

    def poll(self):
        return self.returncode

    def finish(self):
        self.returncode = self._exit

    def send(self, text):          # a login run in a terminal is answered at its prompts
        self.typed.append(text)


def cli(tools=("gh", "aws", "vercel", "netlify", "az", "atlas")):
    """Pretend these tools are installed."""
    return mock.patch.object(cli_signin, "_where", lambda name: f"/bin/{name}" if name in tools else "")


class WhatTheToolsPrintTests(unittest.TestCase):
    def code_of(self, line):
        for pattern in cli_signin._CODES:
            found = pattern.search(line)
            if found:
                return found.group(1)
        return None

    def test_the_code_in_each_tools_own_words(self):
        samples = {
            "! One-time code (8F28-41D4) copied to clipboard": "8F28-41D4",                                  # gh
            "  Visit https://vercel.com/oauth/device?user_code=DTRZ-QHQR": "DTRZ-QHQR",                       # vercel
            "To sign in, use a web browser to open the page https://microsoft.com/devicelogin and "
            "enter the code AB12CD34 to authenticate.": "AB12CD34",                                          # az
            "First copy your one-time code: 0123-ABCD": "0123-ABCD",                                         # older gh
        }
        for line, code in samples.items():
            self.assertEqual(self.code_of(line), code, line)
        self.assertIsNone(self.code_of("Attempting to open your default browser."))

    def test_a_tool_that_opens_no_browser_is_not_told_it_did(self):
        self.assertTrue(cli_signin.PROVIDERS["aws"].opens_browser)
        for key in ("github", "vercel", "netlify", "azure"):
            self.assertFalse(cli_signin.PROVIDERS[key].opens_browser, key)
        self.assertFalse(cli_signin.PROVIDERS["aws"].shows_code)          # a link to approve, no code to type


class WhoIsSignedInTests(unittest.TestCase):
    def setUp(self):
        cli_signin.SIGNINS._seen.clear()

    def run_output(self, table):
        def fake(command, timeout=30):
            key = " ".join(str(x) for x in command[1:3])
            for needle, out in table.items():
                if needle in key or needle in " ".join(str(x) for x in command):
                    return subprocess.CompletedProcess(command, 0, out, "")
            return subprocess.CompletedProcess(command, 1, "", "no")
        return mock.patch.object(cli_signin, "_run", fake)

    def test_github_is_read_from_gh_auth_status_and_the_missing_permission_is_named(self):
        with cli(), self.run_output({"auth status": GH_STATUS}):
            row = cli_signin.SIGNINS.available("github", fresh=True)["github"]
        self.assertEqual((row["installed"], row["signed_in"], row["identity"]["account"]), (True, True, "octocat"))
        self.assertEqual(row["identity"]["missing_scopes"], ["workflow"])

    def test_a_tool_that_is_not_installed_says_how_to_install_it(self):
        with cli(tools=("gh",)):
            rows = cli_signin.SIGNINS.available(fresh=True)
        self.assertFalse(rows["azure"]["installed"])
        self.assertIn("winget install Microsoft.AzureCLI", rows["azure"]["install"])
        self.assertIn("npm i -g netlify-cli", rows["netlify"]["install"])
        with cli(tools=()), self.assertRaisesRegex(ValueError, "winget install Amazon.AWSCLI"):
            cli_signin.SIGNINS.start("aws")

    def test_a_signed_out_tool_is_signed_out(self):
        # A developer's real CLI login files must not turn the fake signed-out case into signed-in.
        with cli(), self.run_output({}), mock.patch.object(cli_signin, "_netlify_token", return_value=""):
            rows = cli_signin.SIGNINS.available(fresh=True)
        self.assertTrue(all(row["installed"] and not row["signed_in"] for row in rows.values()))

    def test_azure_names_the_account_and_subscription(self):
        shown = json.dumps({"user": {"name": "me@example.com"}, "name": "Pay-As-You-Go", "id": "sub-1", "tenantId": "t-1"})
        with cli(), self.run_output({"account show": shown}):
            row = cli_signin.SIGNINS.available("azure", fresh=True)["azure"]
        self.assertEqual((row["identity"]["account"], row["identity"]["subscription"]), ("me@example.com", "Pay-As-You-Go"))

    def test_the_answer_is_kept_briefly_so_that_looking_is_not_slow(self):
        calls = []

        def fake(command, timeout=30):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, GH_STATUS, "")
        with cli(), mock.patch.object(cli_signin, "_run", fake):
            cli_signin.SIGNINS.available("github", fresh=True)
            cli_signin.SIGNINS.available("github")
        self.assertEqual(len(calls), 1)


class LoginFlowTests(unittest.TestCase):
    def setUp(self):
        cli_signin.SIGNINS._flows.clear()
        cli_signin.SIGNINS._seen.clear()

    def test_the_login_command_asks_for_the_permission_a_deployment_needs(self):
        github = cli_signin.PROVIDERS["github"]
        fresh = github.login("gh", {}, None)
        self.assertEqual(fresh[:3], ["gh", "auth", "login"])
        self.assertIn("repo,workflow", fresh)
        self.assertIn("--web", fresh)
        # Already signed in, only missing a permission: add it instead of starting over.
        refresh = github.login("gh", {}, {"account": "octocat", "missing_scopes": ["workflow"]})
        self.assertEqual(refresh[:3], ["gh", "auth", "refresh"])
        aws = cli_signin.PROVIDERS["aws"].login("aws", {"region": "ap-south-1"}, None)
        self.assertEqual(aws, ["aws", "login", "--profile", cli_signin.AWS_PROFILE, "--region", "ap-south-1"])

    def test_a_login_shows_its_code_and_link_then_keeps_what_the_tool_left_behind(self):
        process = FakeProcess(["", "! One-time code (8F28-41D4) copied to clipboard",
                               "Open this URL to continue in your web browser: https://github.com/login/device"])
        with cli(), mock.patch.object(cli_signin.subprocess, "Popen", return_value=process), \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"github": {"identity": None}}):
            started = cli_signin.SIGNINS.start("github")
            cli_signin.SIGNINS._flows[started["flow_id"]]  # registered
            for thread in [t for t in __import__("threading").enumerate() if t.daemon]:
                thread.join(0.3)
            pending = cli_signin.SIGNINS.poll(started["flow_id"])
            self.assertEqual((pending["status"], pending["user_code"]), ("pending", "8F28-41D4"))
            self.assertEqual(pending["verification_uri"], "https://github.com/login/device")
            self.assertTrue(pending["shows_code"])
            # ... the person approves it in the browser and the tool finishes.
            process.finish()
            with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: subprocess.CompletedProcess(
                    command, 0, "gho_thetoken\n" if "token" in command else GH_STATUS, "")):
                done = cli_signin.SIGNINS.poll(started["flow_id"])
        self.assertEqual(done["status"], "ready")
        self.assertEqual(done["values"], {"github_token": "gho_thetoken", "github_login": "octocat"})
        self.assertEqual(cli_signin.SIGNINS._flows, {})

    def test_a_login_that_fails_says_why_in_the_tools_own_words(self):
        process = FakeProcess(["error: authorization was denied"], exit_code=1)
        with cli(), mock.patch.object(cli_signin.subprocess, "Popen", return_value=process), \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"vercel": {"identity": None}}):
            started = cli_signin.SIGNINS.start("vercel")
            for thread in [t for t in __import__("threading").enumerate() if t.daemon]:
                thread.join(0.3)
            process.finish()
            with self.assertRaisesRegex(ValueError, "authorization was denied"):
                cli_signin.SIGNINS.poll(started["flow_id"])

    def test_netlify_is_asked_whether_its_link_was_approved(self):
        answers = iter([{"status": "pending"}, {"status": "authorized"}])

        def fake(command, timeout=30):
            if "--request" in command:
                return subprocess.CompletedProcess(command, 0, json.dumps(
                    {"ticket_id": "t-1", "url": "https://app.netlify.com/authorize?ticket=t-1"}), "")
            if "--check" in command:
                return subprocess.CompletedProcess(command, 0, json.dumps(next(answers)), "")
            return subprocess.CompletedProcess(command, 1, "", "")
        with cli(), mock.patch.object(cli_signin, "_run", fake), mock.patch.object(cli_signin, "_netlify_token", lambda: "nfp_x"):
            started = cli_signin.SIGNINS.start("netlify")
            self.assertEqual(started["verification_uri"], "https://app.netlify.com/authorize?ticket=t-1")
            self.assertFalse(started["shows_code"])
            self.assertEqual(cli_signin.SIGNINS.poll(started["flow_id"])["status"], "pending")
            done = cli_signin.SIGNINS.poll(started["flow_id"])
        self.assertEqual(done, {"status": "ready", "values": {"netlify_token": "nfp_x"}})

    def test_cancelling_ends_the_tool_and_forgets_the_flow(self):
        process = FakeProcess([])
        with cli(), mock.patch.object(cli_signin.subprocess, "Popen", return_value=process), \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"aws": {"identity": None}}), \
                mock.patch.object(cli_signin.SIGNINS, "_stop") as stop:
            started = cli_signin.SIGNINS.start("aws", {"region": "ap-south-1"})
            self.assertEqual(cli_signin.SIGNINS.cancel(started["flow_id"]), {"status": "cancelled"})
        stop.assert_called_once_with(process)
        self.assertEqual(cli_signin.SIGNINS._flows, {})

    def test_an_account_the_tool_is_already_signed_in_as_is_used_without_a_browser(self):
        with cli(), mock.patch.object(cli_signin, "_run", lambda command, timeout=30: subprocess.CompletedProcess(
                command, 0, "gho_thetoken\n" if "token" in command else GH_STATUS, "")):
            kept = cli_signin.SIGNINS.use_existing("github")
        self.assertEqual(kept["values"]["github_token"], "gho_thetoken")
        with cli(), mock.patch.object(cli_signin, "_run", lambda command, timeout=30: subprocess.CompletedProcess(command, 1, "", "")):
            with self.assertRaisesRegex(ValueError, "not signed in"):
                cli_signin.SIGNINS.use_existing("github")

    # What `atlas auth login --noBrowser` printed through a terminal (recorded from the real CLI).
    ATLAS_LOGIN = [
        "? Select authentication type:  [Use arrows to move, type to filter]",
        "> UserAccount - (best for getting started)",
        "ServiceAccount - (best for automation)",
        "APIKeys - (for existing automations)",
        "? Select authentication type: UserAccount",
        "To verify your account, copy your one-time verification code:",
        "9PXK-D7YC",
        "Paste the code in the browser when prompted to activate your Atlas CLI. Your code will expire after 3 minutes.",
        "To continue, go to https://account.mongodb.com/account/connect",
    ]

    def wait_for_output(self):
        for thread in [t for t in __import__("threading").enumerate() if t.daemon]:
            thread.join(0.3)

    def test_atlas_is_signed_in_through_its_terminal_menu_and_shows_its_code_and_link(self):
        process = FakeProcess(self.ATLAS_LOGIN)
        with cli(), mock.patch.object(cli_signin.pty_process, "spawn", return_value=process) as spawn, \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"atlas": {"identity": None}}):
            started = cli_signin.SIGNINS.start("atlas")
            self.wait_for_output()
            pending = cli_signin.SIGNINS.poll(started["flow_id"])
        self.assertEqual(spawn.call_args.args[0], ["/bin/atlas", "auth", "login", "--noBrowser"])
        self.assertEqual((pending["status"], pending["user_code"]), ("pending", "9PXK-D7YC"))
        self.assertEqual(pending["verification_uri"], "https://account.mongodb.com/account/connect")
        # The menu is answered once (its first entry is the browser sign-in), not again when it redraws.
        self.assertEqual(process.typed, ["\r"])

    def test_atlas_later_questions_take_their_default_once_each(self):
        process = FakeProcess(self.ATLAS_LOGIN + ["Successfully logged in as me@example.com.",
                                                  "? Select default organization:  [Use arrows to move, type to filter]",
                                                  "> Acme", "? Select default organization: Acme",
                                                  "? Select default project:  [Use arrows to move, type to filter]"])
        with cli(), mock.patch.object(cli_signin.pty_process, "spawn", return_value=process), \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"atlas": {"identity": None}}):
            cli_signin.SIGNINS.start("atlas")
            self.wait_for_output()
        self.assertEqual(process.typed, ["\r", "\r", "\r"])

    def test_atlas_is_finished_once_it_says_so_even_while_it_waits_at_a_question(self):
        self.atlas_settings()
        process = FakeProcess(self.ATLAS_LOGIN + ["Successfully logged in as me@example.com."])
        whoami = subprocess.CompletedProcess([], 0, "Logged in as me@example.com [Atlas CLI]", "")
        with cli(), mock.patch.object(cli_signin.pty_process, "spawn", return_value=process), \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"atlas": {"identity": None}}), \
                mock.patch.object(cli_signin.SIGNINS, "_stop") as stop, \
                mock.patch.object(cli_signin, "_run", lambda command, timeout=30: whoami):
            started = cli_signin.SIGNINS.start("atlas")
            self.wait_for_output()
            self.assertEqual(cli_signin.SIGNINS.poll(started["flow_id"])["status"], "pending")   # not yet: a moment's grace
            cli_signin.SIGNINS._flows[started["flow_id"]].done_at -= cli_signin.FINISH_GRACE_SECONDS + 1
            done = cli_signin.SIGNINS.poll(started["flow_id"])
        stop.assert_called_once_with(process)
        self.assertEqual(done, {"status": "ready", "values": {"mongodb_atlas_account": "me@example.com",
                                                              "mongodb_atlas_profile": ""}})

    def test_atlas_who_is_signed_in_is_read_from_its_own_whoami(self):
        out = subprocess.CompletedProcess([], 0, "Logged in as me@example.com [Atlas CLI]", "")
        with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: out):
            self.assertEqual(cli_signin._atlas_identity("atlas"), {"account": "me@example.com"})
        signed_out = subprocess.CompletedProcess([], 1, "", "Error: not logged in with an Atlas account, Service Account or API key")
        with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: signed_out):
            self.assertIsNone(cli_signin._atlas_identity("atlas"))
            self.assertEqual(cli_signin._atlas_read("atlas", {}), {})

    def atlas_settings(self, **saved):
        import tempfile
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        patch = mock.patch.object(config, "SETTINGS_FILE", Path(temp.name) / "settings.json")
        patch.start()
        self.addCleanup(patch.stop)
        if saved:
            config.save_settings(saved)

    def test_adding_an_atlas_account_signs_in_under_a_profile_of_its_own_and_keeps_the_first(self):
        self.atlas_settings()
        process = FakeProcess(self.ATLAS_LOGIN)
        listed = subprocess.CompletedProcess([], 0, json.dumps(["default", "agentforge-2"]), "")
        with cli(), mock.patch.object(cli_signin.pty_process, "spawn", return_value=process) as spawn, \
                mock.patch.object(cli_signin, "_run", lambda command, timeout=30: listed), \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"atlas": {"identity": None}}):
            started = cli_signin.SIGNINS.start("atlas", {"add": True})
        # The next free name, so the account already signed in (the default profile, and agentforge-2) is not touched.
        self.assertEqual(spawn.call_args.args[0], ["/bin/atlas", "auth", "login", "--noBrowser", "-P", "agentforge-3"])
        self.assertEqual(cli_signin.SIGNINS._flows[started["flow_id"]].options["profile"], "agentforge-3")

    def test_signing_in_again_to_atlas_uses_the_profile_in_use(self):
        self.atlas_settings(mongodb_atlas_profile="agentforge-2")
        login = cli_signin.PROVIDERS["atlas"].login("atlas", {}, None)
        self.assertEqual(login, ["atlas", "auth", "login", "--noBrowser", "-P", "agentforge-2"])
        self.atlas_settings(mongodb_atlas_profile="")
        self.assertEqual(cli_signin.PROVIDERS["atlas"].login("atlas", {}, None), ["atlas", "auth", "login", "--noBrowser"])

    def test_signing_in_again_while_signed_in_signs_that_profile_out_first(self):
        # The Atlas CLI refuses: "already authenticated with an account ... To log out, run: atlas auth logout".
        self.atlas_settings(mongodb_atlas_profile="agentforge-2")
        ran = []
        with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: ran.append(command)):
            login = cli_signin.PROVIDERS["atlas"].login("atlas", {}, {"account": "me@example.com"})
        self.assertEqual(ran, [["atlas", "auth", "logout", "--force", "-P", "agentforge-2"]])
        self.assertEqual(login, ["atlas", "auth", "login", "--noBrowser", "-P", "agentforge-2"])

    def test_the_default_profile_is_signed_out_without_a_profile_flag(self):
        self.atlas_settings(mongodb_atlas_profile="")
        ran = []
        with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: ran.append(command)):
            cli_signin.PROVIDERS["atlas"].login("atlas", {}, {"account": "me@example.com"})
        self.assertEqual(ran, [["atlas", "auth", "logout", "--force"]])

    def test_nobody_is_signed_out_when_nobody_is_signed_in_or_another_account_is_added(self):
        self.atlas_settings(mongodb_atlas_profile="")
        ran = []
        listed = subprocess.CompletedProcess([], 0, json.dumps(["default"]), "")

        def run(command, timeout=30):
            ran.append(command)
            return listed

        with mock.patch.object(cli_signin, "_run", run):
            cli_signin.PROVIDERS["atlas"].login("atlas", {}, None)                                   # signed out already
            cli_signin.PROVIDERS["atlas"].login("atlas", {"add": True}, {"account": "me@example.com"})   # a new profile
        self.assertFalse([command for command in ran if "logout" in command])

    def test_the_profile_a_sign_in_used_is_what_is_kept_with_the_account(self):
        self.atlas_settings()
        whoami = subprocess.CompletedProcess([], 0, "Logged in as work@example.com [Atlas CLI]", "")
        seen = []

        def run(command, timeout=30):
            seen.append(command)
            return whoami
        with mock.patch.object(cli_signin, "_run", run):
            values = cli_signin.PROVIDERS["atlas"].read("atlas", {"profile": "agentforge-2"})
        self.assertEqual(values, {"mongodb_atlas_account": "work@example.com", "mongodb_atlas_profile": "agentforge-2"})
        self.assertEqual(seen[0], ["atlas", "auth", "whoami", "-P", "agentforge-2"])

    def test_who_is_signed_in_is_asked_of_the_profile_in_use(self):
        self.atlas_settings(mongodb_atlas_profile="agentforge-2")
        seen = []

        def run(command, timeout=30):
            seen.append(command)
            return subprocess.CompletedProcess(command, 0, "Logged in as work@example.com", "")
        with mock.patch.object(cli_signin, "_run", run):
            cli_signin._atlas_identity("atlas")
        self.assertEqual(seen[0], ["atlas", "auth", "whoami", "-P", "agentforge-2"])

    def test_a_finished_sign_in_makes_its_profile_the_account_in_use(self):
        self.atlas_settings()
        result = {"status": "ready", "values": {"mongodb_atlas_account": "work@example.com", "mongodb_atlas_profile": "agentforge-2"}}
        with mock.patch.object(httpd.mongo_connect, "switch_account") as switch:
            kept = httpd._keep_signin(result)
        switch.assert_called_once_with("agentforge-2")
        self.assertEqual(config.setting("mongodb_atlas_account"), "work@example.com")
        self.assertNotIn("values", kept)
        # Another provider's sign-in carries no profile and switches nothing.
        with mock.patch.object(httpd.mongo_connect, "switch_account") as switch:
            httpd._keep_signin({"status": "ready", "values": {"netlify_token": "nfp"}})
        switch.assert_not_called()

    def test_the_atlas_profiles_are_read_whatever_shape_the_cli_lists_them_in(self):
        for text, expected in (('["default", "work"]', ["default", "work"]),
                               ('[{"name": "default"}, {"name": "work"}]', ["default", "work"]),
                               ("A new version is available\n[\"default\"]", ["default"]),
                               ("[]", []), ("", []), ("not json", [])):
            out = subprocess.CompletedProcess([], 0, text, "")
            with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: out):
                self.assertEqual(cli_signin.atlas_profiles("atlas"), expected, text)

    def test_the_route_passes_add_on_to_the_sign_in(self):
        with mock.patch.object(cli_signin.SIGNINS, "start", return_value={"flow_id": "f"}) as start:
            httpd.dispatch("POST", "/cli-signin/start", {"provider": "atlas", "add": True}, {})
        self.assertEqual(start.call_args.args[1]["add"], True)

    def test_a_code_on_a_line_of_its_own_counts_only_after_a_line_that_talks_about_a_code(self):
        process = FakeProcess(["Some build id", "ABCD-1234", "copy your one-time verification code:", "WXYZ-9876"])
        with cli(), mock.patch.object(cli_signin.pty_process, "spawn", return_value=process), \
                mock.patch.object(cli_signin.SIGNINS, "available", lambda *a, **k: {"atlas": {"identity": None}}):
            started = cli_signin.SIGNINS.start("atlas")
            self.wait_for_output()
            self.assertEqual(cli_signin.SIGNINS.poll(started["flow_id"])["user_code"], "WXYZ-9876")

    def test_signing_in_to_azure_never_creates_a_service_principal(self):
        source = Path(cli_signin.__file__).read_text(encoding="utf-8")
        self.assertNotIn("create-for-rbac", source)          # that changes the customer's tenant: a step they take on purpose
        shown = json.dumps({"user": {"name": "me@example.com"}, "name": "Sub", "id": "s", "tenantId": "t"})
        with cli(), mock.patch.object(cli_signin, "_run", lambda command, timeout=30: subprocess.CompletedProcess(command, 0, shown, "")):
            values = cli_signin.PROVIDERS["azure"].read("az", {})
        self.assertEqual(list(values), ["azure_account"])


class VercelCredentialTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.appdata = self.home / "AppData" / "Roaming"
        env = mock.patch.dict("os.environ", {"APPDATA": str(self.appdata), "LOCALAPPDATA": str(self.home / "Local")})
        env.start()
        self.addCleanup(env.stop)
        home = mock.patch.object(cli_signin, "HOME", self.home)
        home.start()
        self.addCleanup(home.stop)

    def write(self, folder: Path, token="vcp_thetoken", expires=None):
        folder.mkdir(parents=True, exist_ok=True)
        body = {"// Note": "x", "token": token, "refreshToken": "vcr_r", "userId": "u"}
        if expires is not None:
            body["expiresAt"] = expires
        (folder / "auth.json").write_text(json.dumps(body), encoding="utf-8")

    def test_the_token_in_the_data_folder_is_found(self):
        # Vercel CLI 59 keeps it in `com.vercel.cli/Data`, not in `com.vercel.cli` itself.
        self.write(self.appdata / "com.vercel.cli" / "Data", expires=4102444800)
        self.assertEqual(cli_signin._vercel_token(), "vcp_thetoken")
        self.assertEqual(cli_signin._vercel_auth()["expires_at"], 4102444800)

    def test_an_older_clis_location_is_still_read(self):
        self.write(self.appdata / "com.vercel.cli", token="vcp_old")
        self.assertEqual(cli_signin._vercel_token(), "vcp_old")
        self.assertEqual(cli_signin._vercel_auth()["expires_at"], None)

    def test_nothing_written_is_nothing(self):
        self.assertEqual(cli_signin._vercel_auth(), {})
        self.assertEqual(cli_signin._vercel_read("vercel", {}), {})

    def test_a_token_about_to_lapse_is_renewed_by_the_cli_before_it_is_kept(self):
        import time
        folder = self.appdata / "com.vercel.cli" / "Data"
        self.write(folder, token="vcp_stale", expires=int(time.time()) + 30)

        def whoami(command, timeout=30):
            self.write(folder, token="vcp_fresh", expires=int(time.time()) + 3600 * 8)   # the CLI renewed it
            return subprocess.CompletedProcess(command, 0, "octocat", "")
        with mock.patch.object(cli_signin, "_run", whoami):
            self.assertEqual(cli_signin._vercel_read("vercel", {}), {"vercel_token": "vcp_fresh"})

    def test_a_token_that_has_lapsed_and_could_not_be_renewed_is_not_kept(self):
        import time
        self.write(self.appdata / "com.vercel.cli" / "Data", expires=int(time.time()) - 60)
        with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: subprocess.CompletedProcess(command, 1, "", "")):
            self.assertEqual(cli_signin._vercel_read("vercel", {}), {})

    def test_the_person_is_told_the_token_lapses_and_what_that_means(self):
        import time
        self.write(self.appdata / "com.vercel.cli" / "Data", expires=int(time.time()) + 3600 * 12 + 60)
        with cli():
            answer = cli_signin.SIGNINS.use_existing("vercel")
        self.assertEqual(answer["values"], {"vercel_token": "vcp_thetoken"})
        self.assertIn("about 12 hours", answer["note"])
        self.assertIn("personal access token", answer["note"])
        self.assertNotIn("note", cli_signin.SIGNINS._ready(cli_signin.PROVIDERS["github"], {"github_token": "x"}))


class WhereTheToolsAreTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows installers put .exe tools under Program Files; elsewhere a tool has no suffix")
    def test_a_tool_installed_after_the_server_started_is_still_found(self):
        with tempfile_dir() as folder:
            (folder / "AWSCLIV2").mkdir()
            (folder / "AWSCLIV2" / "aws.exe").write_text("x")
            env = {"ProgramFiles": str(folder), "PATHEXT": ".EXE", "APPDATA": "", "LOCALAPPDATA": ""}
            with mock.patch.dict("os.environ", env), mock.patch.object(cli_signin.shutil, "which", lambda name: None):
                # Program Files/Amazon/AWSCLIV2 is where the installer puts it.
                (folder / "Amazon").mkdir()
                (folder / "AWSCLIV2").rename(folder / "Amazon" / "AWSCLIV2")
                self.assertTrue(cli_signin._where("aws").lower().endswith("aws.exe"))


class WhatTheStudioKeepsTests(unittest.TestCase):
    def test_a_finished_sign_in_becomes_this_accounts_settings_and_the_secret_is_not_returned(self):
        saved = {}
        with mock.patch.object(config, "save_settings", lambda patch: saved.update(patch)), \
                mock.patch.object(httpd, "read_settings", lambda ctx: {"deploy": {"github_token_set": True}}):
            answer = httpd._keep_signin({"status": "ready", "values": {"github_token": "gho_x", "github_login": "octocat"}})
        self.assertEqual(saved, {"github_token": "gho_x", "github_login": "octocat"})
        self.assertNotIn("values", answer)
        self.assertNotIn("gho_x", json.dumps(answer))
        self.assertEqual(httpd._keep_signin({"status": "pending"}), {"status": "pending"})

    def test_azure_counts_as_connected_and_says_who_after_a_cli_sign_in(self):
        saved = {"azure_account": json.dumps({"account": "me@example.com", "subscription": "Sub"})}
        with mock.patch.object(config, "settings", lambda: saved):
            got = routes_deploy.provider_status({"_match": mock.Mock(group=lambda name: "azure")})
            status = routes_deploy.onboarding_status({})
        self.assertTrue(got["connected"])
        self.assertEqual(got["account"], "me@example.com · Sub")
        self.assertTrue(status["accounts"]["azure"])


def tempfile_dir():
    import contextlib
    import tempfile

    @contextlib.contextmanager
    def manager():
        with tempfile.TemporaryDirectory() as temp:
            yield Path(temp)
    return manager()


if __name__ == "__main__":
    unittest.main()
