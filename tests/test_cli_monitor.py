"""The evidence a deployment's own command line tools can give: chosen by id, run on a click, streamed, masked."""
from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import cli_monitor, cli_signin, config, httpd, prompts  # noqa: E402

PROJECT = "prj_monitor_test"
RUN = {"target": "vercel", "host": {"project": "shop", "deployment_url": "https://shop-abc123.vercel.app"},
       "repository": {"url": "https://github.com/someone/shop"}}


def stand_in(commands: list[dict], target: str = "vercel") -> dict:
    """A catalogue whose tool is this Python, so a command can print, wait or fail on purpose."""
    return {"targets": {target: ["test"]}, "sets": {"test": {"tool": "python", "title": "Test tool", "commands": commands}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.run_record = dict(RUN)
        for patch in (mock.patch.object(config, "workspace_for", lambda project: self.workspace),
                      mock.patch.object(config, "SETTINGS_FILE", self.workspace / "settings.json"),
                      mock.patch.object(cli_signin, "_where", lambda name: sys.executable if name == "python" else ""),
                      mock.patch("deploy_agent.deploy.run_state", lambda project: self.run_record)):
            patch.start()
            self.addCleanup(patch.stop)

    def use(self, commands, target="vercel"):
        patch = mock.patch.object(cli_monitor, "_catalogue", lambda scope="deploy": stand_in(commands, target))
        patch.start()
        self.addCleanup(patch.stop)

    def read(self, job: str, timeout: float = 15.0) -> dict:
        lines, since, seen = [], 0, {}
        end = time.time() + timeout
        while time.time() < end:
            seen = cli_monitor.MONITORS.poll(job, since)
            lines += seen["lines"]
            since = seen["next"]
            if seen["status"] != "running":
                break
            time.sleep(0.05)
        return {**seen, "lines": lines}


class CatalogueTests(Base):
    def test_every_deployment_type_has_commands_and_only_those_it_can_fill_in_are_offered(self):
        real = prompts.data("deployment/monitors")
        self.assertEqual(set(real["targets"]), {"vercel", "netlify", "aws_ec2", "aws_ecs", "azure", "github"})
        offered = cli_monitor.catalogue(PROJECT, RUN)
        labels = {row["label"] for row in offered["items"]}
        self.assertEqual(offered["target"], "vercel")
        self.assertTrue({"Deployments", "Deployment", "Build logs", "Runtime logs", "Variables", "Domains", "Repository",
                         "CI runs"} <= labels)
        self.assertNotIn("Site details", labels)                     # another type's command is not offered
        thin = {row["label"] for row in cli_monitor.catalogue(PROJECT, {"target": "vercel"})["items"]}   # nothing recorded yet
        self.assertTrue({"Account", "Teams", "Deployments", "Variables", "Domains", "Aliases", "GitHub account", "Commits",
                         "Branches"} <= thin)                             # what needs nothing from the record
        self.assertTrue(thin < labels)
        for needs_the_record in ("Project", "Deployment", "Build logs", "Runtime logs", "Repository", "CI runs"):
            self.assertNotIn(needs_the_record, thin)

    def test_every_command_has_a_page_of_its_own_and_no_id_is_a_view_the_panel_already_has(self):
        sets = prompts.data("deployment/monitors")["sets"]
        registry = (ROOT / "studio/components/deploy/cli/index.js").read_text(encoding="utf-8")
        for name, group in sets.items():
            for command in group["commands"]:
                self.assertIn(f"'{name}/{command['id']}':", registry, f"{name}/{command['id']} has no page")
                self.assertNotEqual(command["id"], "deploy")             # the panel's own first view

    def test_a_command_shows_as_a_person_would_type_it_and_never_carries_its_arguments_out(self):
        row = next(r for r in cli_monitor.catalogue(PROJECT, RUN)["items"] if r["id"] == "deployment")
        self.assertEqual(row["display"], "vercel inspect https://shop-abc123.vercel.app --format json")
        self.assertNotIn("argv", row)
        config.save_settings({"aws_profile": "agentforge-console"})
        aws = cli_monitor.catalogue(PROJECT, {"target": "aws_ecs", "host": {"stack_name": "shop-prod", "region": "eu-west-1",
                                                                            "cluster": "c", "service": "s"}})
        service = next(r for r in aws["items"] if r["id"] == "service")
        self.assertIn('--query "…"', service["display"])                # a long query is elided
        self.assertIn("--region eu-west-1", service["display"])

    def test_a_github_address_becomes_owner_and_name_and_a_value_that_is_not_plain_is_refused(self):
        row = next(r for r in cli_monitor.catalogue(PROJECT, RUN)["items"] if r["id"] == "gh-runs")
        self.assertIn("-R someone/shop", row["display"])
        risky = {"target": "vercel", "host": {"project": "shop & del *", "deployment_url": "-rf"}}
        labels = {r["label"] for r in cli_monitor.catalogue(PROJECT, risky)["items"]}
        self.assertNotIn("Project", labels)                            # a space and an ampersand
        self.assertNotIn("Deployment", labels)                         # would be read as an option

    def test_no_command_id_is_used_twice_for_one_deployment_type(self):
        for target in prompts.data("deployment/monitors")["targets"]:
            run = {"target": target}
            ids = [row["id"] for row in cli_monitor.catalogue(PROJECT, run)["items"]]
            self.assertEqual(len(ids), len(set(ids)), target)
        sets = prompts.data("deployment/monitors")
        for target, names in sets["targets"].items():
            every = [command["id"] for name in names for command in sets["sets"][name]["commands"]]
            self.assertEqual(len(every), len(set(every)), target)

    def test_an_aws_log_group_path_is_a_plain_value_and_secrets_are_found_by_the_path_recorded_or_the_log_group(self):
        config.save_settings({"aws_profile": "agentforge-console"})
        host = {"region": "ap-south-1", "stack_name": "shop-bootstrap", "instance_id": "i-0abc", "log_group": "/deployment-agent/shop"}
        rows = {r["id"]: r for r in cli_monitor.catalogue(PROJECT, {"target": "aws_ec2", "host": host})["items"]}
        self.assertIn("/deployment-agent/shop", rows["ec2-logs"]["display"])            # a leading slash is not an option
        self.assertIn("Values=/deployment-agent/shop", rows["secrets"]["display"])      # no secret_name: the log group path
        named = {"target": "aws_ec2", "host": {**host, "secret_name": "/deployment-agent/shop/runtime"}}
        again = {r["id"]: r for r in cli_monitor.catalogue(PROJECT, named)["items"]}
        self.assertIn("Values=/deployment-agent/shop/runtime", again["secrets"]["display"])
        risky = {"target": "aws_ec2", "host": {**host, "log_group": "-rf"}}
        self.assertNotIn("ec2-logs", {r["id"] for r in cli_monitor.catalogue(PROJECT, risky)["items"]})   # `-` still is

    def test_a_record_with_no_deployment_has_no_monitors(self):
        self.assertEqual(cli_monitor.catalogue(PROJECT, {})["items"], [])


class RunTests(Base):
    def test_a_command_streams_its_output_as_it_is_written_and_ends_with_its_exit_code(self):
        self.use([{"id": "slow", "group": "T", "label": "Slow", "follow": True,
                   "argv": ["-c", "import time\nprint('one', flush=True)\ntime.sleep(0.8)\nprint('two', flush=True)"]}])
        started = cli_monitor.MONITORS.start(PROJECT, "slow")
        self.assertIn("python -c", started["display"])
        first = {"status": "running", "lines": []}
        end = time.time() + 5
        while time.time() < end and not first["lines"]:
            first = cli_monitor.MONITORS.poll(started["job"], 0)
            time.sleep(0.05)
        self.assertEqual((first["status"], first["lines"]), ("running", ["one"]))     # seen before it finished
        done = self.read(started["job"])
        self.assertEqual((done["status"], done["exit_code"], done["lines"]), ("done", 0, ["one", "two"]))

    def test_a_failing_command_says_so_and_a_reader_only_gets_what_is_new(self):
        self.use([{"id": "bad", "group": "T", "label": "Bad", "argv": ["-c", "print('x');print('y');raise SystemExit(3)"]}])
        job = cli_monitor.MONITORS.start(PROJECT, "bad")["job"]
        done = self.read(job)
        self.assertEqual((done["status"], done["exit_code"]), ("failed", 3))
        self.assertEqual(cli_monitor.MONITORS.poll(job, 1)["lines"], ["y"])
        self.assertEqual(cli_monitor.MONITORS.poll(job, 2)["lines"], [])

    def test_stopping_ends_a_command_that_would_run_on(self):
        self.use([{"id": "long", "group": "T", "label": "Long", "follow": True,
                   "argv": ["-c", "import time\nprint('up', flush=True)\ntime.sleep(60)"]}])
        job = cli_monitor.MONITORS.start(PROJECT, "long")["job"]
        time.sleep(0.5)
        cli_monitor.MONITORS.stop(job)
        self.assertEqual(self.read(job)["status"], "stopped")

    def test_starting_the_same_monitor_again_replaces_the_earlier_one(self):
        self.use([{"id": "long", "group": "T", "label": "Long", "follow": True,
                   "argv": ["-c", "import time\nprint('up', flush=True)\ntime.sleep(60)"]}])
        first = cli_monitor.MONITORS.start(PROJECT, "long")["job"]
        time.sleep(0.4)
        second = cli_monitor.MONITORS.start(PROJECT, "long")["job"]
        self.assertEqual(self.read(first)["status"], "stopped")
        cli_monitor.MONITORS.stop(second)
        self.read(second)

    def test_a_command_that_outlives_its_time_is_stopped(self):
        self.use([{"id": "hang", "group": "T", "label": "Hang", "timeout": 1,
                   "argv": ["-c", "import time\ntime.sleep(60)"]}])
        job = cli_monitor.MONITORS.start(PROJECT, "hang")["job"]
        self.assertEqual(self.read(job, 10)["status"], "timeout")

    def test_only_a_listed_command_can_be_run_and_only_when_its_values_are_known(self):
        self.use([{"id": "needs", "group": "T", "label": "Needs", "argv": ["-c", "print('{{host.nothing}}')"]}])
        with self.assertRaisesRegex(ValueError, "no monitor called"):
            cli_monitor.MONITORS.start(PROJECT, "rm -rf")
        with self.assertRaisesRegex(ValueError, "host.nothing"):
            cli_monitor.MONITORS.start(PROJECT, "needs")
        self.run_record = {}
        with self.assertRaisesRegex(ValueError, "no deployment"):
            cli_monitor.MONITORS.start(PROJECT, "needs")

    def test_a_tool_that_is_not_installed_is_said_so(self):
        self.use([{"id": "x", "group": "T", "label": "X", "tool": "nosuchtool", "argv": ["a"]}])
        with self.assertRaisesRegex(ValueError, "not installed"):
            cli_monitor.MONITORS.start(PROJECT, "x")

    def test_the_assistants_own_environment_is_not_handed_to_the_tool(self):
        self.use([{"id": "env", "group": "T", "label": "Env", "argv": ["-c",
                   "import os;print(os.environ.get('CLAUDECODE', 'none'), os.environ.get('ANTHROPIC_API_KEY', 'none'), os.environ.get('KEEP_ME'))"]}])
        with mock.patch.dict("os.environ", {"CLAUDECODE": "1", "ANTHROPIC_API_KEY": "sk-ant-x", "KEEP_ME": "yes"}):
            job = cli_monitor.MONITORS.start(PROJECT, "env")["job"]
            self.assertEqual(self.read(job)["lines"], ["none none yes"])

    def test_it_runs_in_the_projects_own_folder(self):
        self.use([{"id": "where", "group": "T", "label": "Where", "argv": ["-c", "import os;print(os.getcwd())"]}])
        job = cli_monitor.MONITORS.start(PROJECT, "where")["job"]
        self.assertEqual(Path(self.read(job)["lines"][0]).resolve(), self.workspace.resolve())


class MaskingTests(Base):
    def test_a_plain_value_the_customer_gave_is_not_hidden_but_a_secret_one_is(self):
        from server_modules import deploy_vars

        deploy_vars.save("ADMIN_NAME", "Ravindu Perera", secret=False)
        deploy_vars.save("ADMIN_PASSWORD", "Hunter2-Hunter2", secret=True)
        self.assertEqual(deploy_vars.secret_values(), ["Hunter2-Hunter2"])
        self.use([{"id": "who", "group": "T", "label": "Who", "argv": ["-c", "print('Ravindu Perera signed in with Hunter2-Hunter2')"]}])
        out = "\n".join(self.read(cli_monitor.MONITORS.start(PROJECT, "who")["job"])["lines"])
        self.assertEqual(out, "Ravindu Perera signed in with <hidden>")

    def test_colour_codes_credentials_and_the_customers_saved_values_never_reach_the_studio(self):
        config.save_settings({"deploy_env": {"ADMIN_PASSWORD": "Hunter2-Hunter2"}})
        code = ("print('\\x1b[31mred\\x1b[0m mongodb+srv://u:Secr3tPass99@h.example.net/db')\n"
                "print('the value Hunter2-Hunter2 leaked')\n"
                "print('token ghp_' + 'a1B2c3D4' * 5)")
        self.use([{"id": "leaky", "group": "T", "label": "Leaky", "argv": ["-c", code]}])
        out = "\n".join(self.read(cli_monitor.MONITORS.start(PROJECT, "leaky")["job"])["lines"])
        self.assertIn("red", out)
        self.assertNotIn("\x1b", out)
        for secret in ("Secr3tPass99", "Hunter2-Hunter2", "a1B2c3D4a1B2c3D4"):
            self.assertNotIn(secret, out)
        self.assertIn("<hidden>", out)


class RouteTests(Base):
    def test_the_routes_list_start_poll_and_stop(self):
        self.use([{"id": "hello", "group": "T", "label": "Hello", "argv": ["-c", "print('hi')"]}])
        with mock.patch.object(httpd.store, "require", lambda project: None):
            listed = httpd.cli_monitor_list({"project": PROJECT})
            started = httpd.cli_monitor_start({"project": PROJECT, "command": "hello"})
        self.assertEqual([row["id"] for row in listed["items"]], ["hello"])
        done = self.read(started["job"])
        self.assertEqual(done["lines"], ["hi"])
        self.assertEqual(httpd.cli_monitor_poll({"job": started["job"], "since": 1})["lines"], [])
        self.assertTrue(httpd.cli_monitor_stop({"job": started["job"]})["ok"])
        self.assertEqual(httpd.cli_monitor_poll({"job": "nope"})["status"], "gone")


if __name__ == "__main__":
    unittest.main()
