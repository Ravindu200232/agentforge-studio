"""Connecting MongoDB Atlas: a browser sign-in through the Atlas CLI, or a Service Account, then one real cluster."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import cli_signin, config, mongo_connect as mc  # noqa: E402

GROUP, ORG = "5e2211c17a3e5a48f5497de3", "5e2211c17a3e5a48f5497de0"


class AtlasCase(unittest.TestCase):
    """A temporary settings.json, and an Atlas CLI that is a table of answers instead of a program."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.calls: list[list[str]] = []
        self.answers: dict[str, object] = {}
        self.signed_in = {"account": "me@example.com"}
        for patch in (
            mock.patch.object(config, "SETTINGS_FILE", Path(self.temp.name) / "settings.json"),
            mock.patch.object(cli_signin, "_where", lambda name: f"/bin/{name}"),
            mock.patch.object(cli_signin, "_run", self.fake_run),
            mock.patch.object(cli_signin.SIGNINS, "available", self.fake_available),
            mock.patch.object(mc.time, "sleep", lambda seconds: None),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def fake_available(self, only="", fresh=False):
        row = {"installed": True, "signed_in": bool(self.signed_in), "identity": self.signed_in or None}
        return {"atlas": row}

    def fake_run(self, command, timeout=30):
        args = [str(x) for x in command[1:]]
        self.calls.append(args)
        key = " ".join(args[:2])
        answer = self.answers.get(key)
        if callable(answer):
            answer = answer(args)
        if isinstance(answer, Exception):
            return subprocess.CompletedProcess(command, 1, "", f"Error: {answer}")
        if answer is None:
            return subprocess.CompletedProcess(command, 1, "", f"Error: no answer for {key}")
        return subprocess.CompletedProcess(command, 0, json.dumps(answer), "")

    def ran(self, key: str) -> list[list[str]]:
        return [args for args in self.calls if " ".join(args[:2]) == key]

    def project_and_cluster_ready(self):
        self.answers.update({
            "organizations list": {"results": [{"id": ORG, "name": "Acme"}]},
            "projects list": {"results": []},
            "projects create": {"id": GROUP, "name": mc.GROUP_NAME},
            "clusters list": {"results": []},
            "clusters create": {"name": mc.CLUSTER_NAME},
            "clusters describe": {"stateName": "IDLE", "connectionStrings": {"standardSrv": "mongodb+srv://agentforge.abc12.mongodb.net"}},
            "dbusers describe": ValueError("not found"),
            "dbusers create": {"username": mc.DB_USERNAME},
            "dbusers update": {"username": mc.DB_USERNAME},
            "accessLists list": {"results": []},
            "accessLists create": {"results": []},
        })


class StatusTests(AtlasCase):
    def test_nothing_connected(self):
        self.signed_in = {}
        self.assertEqual(mc.status(), {"connected": False, "via": "", "account": "", "org": "", "cluster_ready": False,
                                       "cluster": ""})

    def test_the_atlas_cli_signed_in_is_a_connection_with_no_service_account(self):
        status = mc.status()
        self.assertEqual((status["connected"], status["via"], status["account"]), (True, "cli", "me@example.com"))
        self.assertFalse(mc.credentials_saved())

    def test_a_saved_service_account_wins_and_the_cli_is_not_even_asked(self):
        config.save_settings({"mongodb_client_id": "id", "mongodb_client_secret": "secret"})
        with mock.patch.object(cli_signin.SIGNINS, "available") as asked:
            status = mc.status()
        self.assertEqual((status["connected"], status["via"]), (True, "service_account"))
        asked.assert_not_called()

    def test_the_build_is_told_an_atlas_account_is_connected_either_way(self):
        self.assertTrue(mc.account_facts()["atlas_connected"])
        self.signed_in = {}
        self.assertFalse(mc.account_facts()["atlas_connected"])


class CliClusterTests(AtlasCase):
    def test_refuses_with_nobody_signed_in(self):
        self.signed_in = {}
        with self.assertRaisesRegex(ValueError, "Sign in to MongoDB Atlas"):
            mc.ensure_cluster()

    def test_makes_the_project_cluster_user_and_access_list_and_keeps_the_connection_string(self):
        self.project_and_cluster_ready()
        said: list[str] = []
        result = mc.ensure_cluster(said.append)
        self.assertEqual((result["connected"], result["via"], result["cluster_ready"]), (True, "cli", True))

        self.assertEqual(self.ran("projects create")[0][:2], ["projects", "create"])
        self.assertIn(mc.GROUP_NAME, self.ran("projects create")[0])
        create = self.ran("clusters create")[0]
        for pair in (["--provider", "AWS"], ["--region", "US_EAST_1"], ["--tier", "M0"], ["--projectId", GROUP]):
            self.assertEqual(create[create.index(pair[0]):create.index(pair[0]) + 2], pair)
        self.assertEqual(self.ran("accessLists create")[0][2], "0.0.0.0/0")
        # Every command carried -o json (parsed) and named its project; none relied on a default.
        for args in self.calls:
            self.assertEqual(args[-2:], ["-o", "json"])
        for key in ("clusters create", "clusters describe", "dbusers create", "accessLists create"):
            self.assertIn(GROUP, self.ran(key)[0], key)

        password = self.ran("dbusers create")[0][self.ran("dbusers create")[0].index("--password") + 1]
        self.assertGreaterEqual(len(password), 20)
        self.assertEqual(config.setting("deploy_mongodb_uri"),
                         f"mongodb+srv://{mc.DB_USERNAME}:{password}@agentforge.abc12.mongodb.net/app?retryWrites=true&w=majority")
        self.assertEqual((config.setting(mc.GROUP_ID_SETTING), config.setting(mc.CLUSTER_NAME_SETTING)), (GROUP, mc.CLUSTER_NAME))
        self.assertTrue(any("Creating the agentforge cluster" in line for line in said))

    def test_an_existing_project_and_cluster_are_used_not_duplicated(self):
        self.project_and_cluster_ready()
        self.answers["projects list"] = {"results": [{"id": "other", "name": "Personal"}, {"id": GROUP, "name": mc.GROUP_NAME}]}
        self.answers["clusters list"] = {"results": [{"name": "my-own-cluster"}]}
        mc.ensure_cluster()
        self.assertEqual(self.ran("projects create"), [])
        self.assertEqual(self.ran("clusters create"), [])
        self.assertEqual(self.ran("clusters describe")[0][2], "my-own-cluster")
        self.assertEqual(config.setting(mc.CLUSTER_NAME_SETTING), "my-own-cluster")

    def test_without_the_studios_own_project_the_first_one_is_used(self):
        self.project_and_cluster_ready()
        self.answers["projects list"] = {"results": [{"id": GROUP, "name": "Personal"}]}
        mc.ensure_cluster()
        self.assertEqual(self.ran("projects create"), [])

    def test_a_database_user_left_by_an_earlier_attempt_gets_a_known_password(self):
        self.project_and_cluster_ready()
        self.answers["dbusers describe"] = {"username": mc.DB_USERNAME}
        mc.ensure_cluster()
        self.assertEqual(self.ran("dbusers create"), [])
        update = self.ran("dbusers update")[0]
        password = update[update.index("--password") + 1]
        self.assertIn(f":{password}@", config.setting("deploy_mongodb_uri"))

    def test_an_open_access_list_is_left_as_it_is(self):
        self.project_and_cluster_ready()
        self.answers["accessLists list"] = {"results": [{"cidrBlock": "0.0.0.0/0"}]}
        mc.ensure_cluster()
        self.assertEqual(self.ran("accessLists create"), [])

    def test_a_second_call_does_nothing_more(self):
        self.project_and_cluster_ready()
        mc.ensure_cluster()
        before = len(self.calls)
        mc.ensure_cluster()
        self.assertEqual(len(self.calls), before)

    def test_the_cluster_is_waited_for_until_it_is_idle(self):
        self.project_and_cluster_ready()
        states = iter(["CREATING", "CREATING", "IDLE"])
        self.answers["clusters describe"] = lambda args: {
            "stateName": next(states), "connectionStrings": {"standardSrv": "mongodb+srv://c.mongodb.net"}}
        mc.ensure_cluster()
        self.assertEqual(len(self.ran("clusters describe")), 3)

    def test_a_cluster_that_never_comes_up_says_so(self):
        self.project_and_cluster_ready()
        self.answers["clusters describe"] = {"stateName": "CREATING"}
        with self.assertRaisesRegex(ValueError, "did not finish provisioning"):
            mc.ensure_cluster()
        self.assertFalse(config.setting("deploy_mongodb_uri"))

    def test_the_clis_own_message_is_what_the_person_sees(self):
        self.project_and_cluster_ready()
        self.answers["projects create"] = ValueError("You do not have permission to create projects in this organization")
        with self.assertRaisesRegex(ValueError, "do not have permission to create projects"):
            mc.ensure_cluster()

    def test_a_service_account_still_uses_the_rest_api_not_the_cli(self):
        config.save_settings({"mongodb_client_id": "id", "mongodb_client_secret": "secret"})
        with mock.patch.object(mc, "_token", return_value="t"), \
                mock.patch.object(mc, "_ensure_group", return_value=GROUP) as group, \
                mock.patch.object(mc, "_ensure_cluster", return_value="agentforge"), \
                mock.patch.object(mc, "_wait_idle", return_value={"connectionStrings": {"standardSrv": "mongodb+srv://c.mongodb.net"}}), \
                mock.patch.object(mc, "_ensure_db_user"), mock.patch.object(mc, "_ensure_access_list"):
            result = mc.ensure_cluster()
        group.assert_called_once()
        self.assertEqual(self.calls, [])
        self.assertEqual((result["via"], result["cluster_ready"]), ("service_account", True))
        self.assertTrue(config.setting("deploy_mongodb_uri").startswith("mongodb+srv://agentforge_app:"))


OTHER = "6f3322d28b4f6b59a6608ef4"


class ChooseClusterTests(AtlasCase):
    """The clusters an account already has are listed, and one of them is used; a new one is made only when asked for."""

    def two_projects(self):
        self.project_and_cluster_ready()
        by_project = {
            GROUP: [{"name": "shop-db", "stateName": "IDLE",
                     "providerSettings": {"instanceSizeName": "M0", "regionName": "US_EAST_1"}}],
            OTHER: [{"name": "blog-db", "stateName": "IDLE", "paused": True,
                     "replicationSpecs": [{"regionConfigs": [{"regionName": "EU_WEST_1",
                                                              "electableSpecs": {"instanceSize": "M10"}}]}]}],
        }
        self.answers.update({
            "projects list": {"results": [{"id": GROUP, "name": "Shop"}, {"id": OTHER, "name": "Blog"}]},
            "clusters list": lambda args: {"results": by_project[args[args.index("--projectId") + 1]]},
            "clusters describe": lambda args: {
                "stateName": "IDLE", "paused": args[args.index("--projectId") + 1] == OTHER and args[2] == "blog-db",
                "connectionStrings": {"standardSrv": f"mongodb+srv://{args[2]}.abc12.mongodb.net"}},
        })

    def test_every_cluster_of_every_project_is_listed_with_where_it_is_and_what_state_it_is_in(self):
        self.two_projects()
        listing = mc.list_clusters()
        rows = {row["name"]: row for row in listing["clusters"]}
        self.assertEqual(set(rows), {"shop-db", "blog-db"})
        self.assertEqual((rows["shop-db"]["project"], rows["shop-db"]["group_id"], rows["shop-db"]["tier"], rows["shop-db"]["region"], rows["shop-db"]["state"]),
                         ("Shop", GROUP, "M0", "US_EAST_1", "IDLE"))
        # the other API shape (replication specs) and a paused cluster
        self.assertEqual((rows["blog-db"]["tier"], rows["blog-db"]["region"], rows["blog-db"]["state"]), ("M10", "EU_WEST_1", "PAUSED"))
        self.assertFalse(listing["missing"])
        self.assertFalse(any(row["selected"] for row in listing["clusters"]))

    def test_the_cluster_in_use_is_marked_and_listed_first(self):
        self.two_projects()
        config.save_settings({mc.GROUP_ID_SETTING: OTHER, mc.CLUSTER_NAME_SETTING: "blog-db"})
        listing = mc.list_clusters()
        self.assertEqual([row["name"] for row in listing["clusters"]], ["blog-db", "shop-db"])
        self.assertEqual([row["selected"] for row in listing["clusters"]], [True, False])
        self.assertFalse(listing["missing"])

    def test_a_cluster_on_record_that_is_no_longer_in_the_account_is_said_to_be_missing(self):
        # What a deleted cluster leaves behind: "Cluster ready" for a host that no longer exists.
        self.two_projects()
        config.save_settings({mc.GROUP_ID_SETTING: GROUP, mc.CLUSTER_NAME_SETTING: "deleted-long-ago"})
        listing = mc.list_clusters()
        self.assertTrue(listing["missing"])
        self.assertEqual(listing["selected"], {"group_id": GROUP, "name": "deleted-long-ago"})

    def test_a_project_the_account_may_not_look_inside_is_left_out_and_the_rest_are_listed(self):
        self.two_projects()
        shop = self.answers["clusters list"]
        self.answers["clusters list"] = lambda args: (_ for _ in ()).throw(ValueError("forbidden")) \
            if OTHER in args else shop(args)
        self.assertEqual([row["name"] for row in mc.list_clusters()["clusters"]], ["shop-db"])

    def test_an_account_with_no_projects_has_no_clusters_to_choose(self):
        self.project_and_cluster_ready()
        self.assertEqual(mc.list_clusters()["clusters"], [])

    def test_listing_needs_somebody_signed_in(self):
        self.signed_in = {}
        with self.assertRaisesRegex(ValueError, "Sign in to MongoDB Atlas"):
            mc.list_clusters()

    def test_a_service_account_lists_them_through_the_rest_api(self):
        config.save_settings({"mongodb_client_id": "id", "mongodb_client_secret": "secret"})

        def api(method, path, body=None, token=""):
            if path == "/orgs":
                return {"results": [{"id": ORG}]}
            if path.startswith("/groups?orgId="):
                return {"results": [{"id": GROUP, "name": "Shop"}]}
            return {"results": [{"name": "shop-db", "stateName": "IDLE"}]}

        with mock.patch.object(mc, "_token", return_value="t"), mock.patch.object(mc, "_api", api):
            rows = mc.list_clusters()["clusters"]
        self.assertEqual([(row["project"], row["name"]) for row in rows], [("Shop", "shop-db")])
        self.assertEqual(self.calls, [])

    def test_the_chosen_cluster_gets_the_user_and_access_list_and_its_connection_string_is_kept(self):
        self.two_projects()
        said: list[str] = []
        result = mc.use_cluster(GROUP, "shop-db", said.append)
        self.assertEqual((result["cluster_ready"], result["cluster"]), (True, "shop-db"))
        # Nothing was made: the cluster, and its project, were already there.
        self.assertEqual(self.ran("projects create"), [])
        self.assertEqual(self.ran("clusters create"), [])
        for key in ("clusters describe", "dbusers create", "accessLists create"):
            self.assertIn(GROUP, self.ran(key)[0], key)
        password = self.ran("dbusers create")[0][self.ran("dbusers create")[0].index("--password") + 1]
        self.assertEqual(config.setting("deploy_mongodb_uri"),
                         f"mongodb+srv://{mc.DB_USERNAME}:{password}@shop-db.abc12.mongodb.net/app?retryWrites=true&w=majority")
        self.assertEqual((config.setting(mc.GROUP_ID_SETTING), config.setting(mc.CLUSTER_NAME_SETTING)), (GROUP, "shop-db"))

    def test_choosing_another_cluster_replaces_the_one_in_use(self):
        self.two_projects()
        mc.use_cluster(GROUP, "shop-db")
        self.answers["clusters describe"] = {"stateName": "IDLE", "connectionStrings": {"standardSrv": "mongodb+srv://blog-db.zz.mongodb.net"}}
        mc.use_cluster(OTHER, "blog-db")
        self.assertEqual((config.setting(mc.GROUP_ID_SETTING), config.setting(mc.CLUSTER_NAME_SETTING)), (OTHER, "blog-db"))
        self.assertIn("@blog-db.zz.mongodb.net/", config.setting("deploy_mongodb_uri"))

    def test_a_paused_cluster_is_refused_and_nothing_is_saved(self):
        self.two_projects()
        with self.assertRaisesRegex(ValueError, "paused"):
            mc.use_cluster(OTHER, "blog-db")
        self.assertFalse(config.setting("deploy_mongodb_uri"))
        self.assertEqual(self.ran("dbusers create"), [])
        self.assertEqual(self.ran("accessLists create"), [])

    def test_it_has_to_be_said_which_cluster_and_somebody_has_to_be_signed_in(self):
        with self.assertRaisesRegex(ValueError, "which cluster"):
            mc.use_cluster("", "shop-db")
        self.signed_in = {}
        with self.assertRaisesRegex(ValueError, "Sign in to MongoDB Atlas"):
            mc.use_cluster(GROUP, "shop-db")

    def test_a_service_account_uses_the_chosen_cluster_through_the_rest_api(self):
        config.save_settings({"mongodb_client_id": "id", "mongodb_client_secret": "secret"})
        with mock.patch.object(mc, "_token", return_value="t"), \
                mock.patch.object(mc, "_wait_idle", return_value={"connectionStrings": {"standardSrv": "mongodb+srv://c.mongodb.net"}}) as wait, \
                mock.patch.object(mc, "_ensure_db_user") as user, mock.patch.object(mc, "_ensure_access_list") as access:
            result = mc.use_cluster(GROUP, "shop-db")
        wait.assert_called_once()
        self.assertEqual(wait.call_args.args[1:3], (GROUP, "shop-db"))
        user.assert_called_once()
        access.assert_called_once()
        self.assertEqual((result["via"], result["cluster"]), ("service_account", "shop-db"))

    def test_a_new_cluster_is_made_when_asked_even_with_one_in_use_and_never_inside_somebody_elses_project(self):
        self.project_and_cluster_ready()
        config.save_settings({mc.GROUP_ID_SETTING: OTHER, mc.CLUSTER_NAME_SETTING: "blog-db"})
        # The account has a project and a cluster of its own, which the automatic choice would have reused.
        self.answers["projects list"] = {"results": [{"id": OTHER, "name": "Blog"}]}
        self.answers["clusters list"] = {"results": [{"name": "blog-db"}]}
        result = mc.ensure_cluster(create=True)
        self.assertEqual(len(self.ran("projects create")), 1)
        self.assertEqual(len(self.ran("clusters create")), 1)
        self.assertEqual((result["cluster"], config.setting(mc.GROUP_ID_SETTING)), (mc.CLUSTER_NAME, GROUP))

    def test_without_asking_for_a_new_one_a_cluster_in_use_is_left_alone(self):
        self.project_and_cluster_ready()
        config.save_settings({mc.GROUP_ID_SETTING: GROUP, mc.CLUSTER_NAME_SETTING: "shop-db"})
        mc.ensure_cluster()
        self.assertEqual(self.calls, [])

    def test_the_database_user_of_the_rest_api_gets_a_known_password_when_it_is_already_there(self):
        calls: list[tuple] = []

        def api(method, path, body=None, token=""):
            calls.append((method, path, body))
            return {}

        with mock.patch.object(mc, "_api", api):
            mc._ensure_db_user("t", GROUP, "known-password")
        self.assertEqual([c[0] for c in calls], ["GET", "PATCH"])
        self.assertEqual(calls[1][2], {"password": "known-password"})

        calls.clear()

        def missing(method, path, body=None, token=""):
            calls.append((method, path, body))
            if method == "GET":
                raise ValueError("no such user")
            return {}

        with mock.patch.object(mc, "_api", missing):
            mc._ensure_db_user("t", GROUP, "known-password")
        self.assertEqual([c[0] for c in calls], ["GET", "POST"])
        self.assertEqual(calls[1][2]["password"], "known-password")

    def test_the_two_routes_the_picker_uses(self):
        from server_modules import routes_deploy

        self.two_projects()
        listing = routes_deploy.dispatch("GET", "/mongodb/clusters")
        self.assertTrue(listing["ok"])
        self.assertEqual({row["name"] for row in listing["clusters"]}, {"shop-db", "blog-db"})
        used = routes_deploy.dispatch("POST", "/mongodb/cluster/use", {"group_id": GROUP, "name": "shop-db"})
        self.assertEqual((used["ok"], used["cluster"]), (True, "shop-db"))


class SeveralAccountsTests(AtlasCase):
    """Each account signed in through the Atlas CLI is a profile of its own: they are listed, switched between, and
    each keeps the cluster that was made for it."""

    def setUp(self):
        super().setUp()
        self.profiles = {"default": "me@example.com", "agentforge-2": "work@example.com"}
        self.logged_out: list[list[str]] = []
        self.answers["config list"] = lambda args: list(self.profiles)
        mc._seen_accounts[0] = 0.0
        patch = mock.patch.object(cli_signin, "atlas_identity", self.fake_identity)
        patch.start()
        self.addCleanup(patch.stop)

    def fake_identity(self, tool, profile=None):
        name = (profile if profile is not None else config.setting("mongodb_atlas_profile")) or "default"
        return {"account": self.profiles[name]} if name in self.profiles else None

    def fake_available(self, only="", fresh=False):
        who = self.fake_identity("atlas")            # the CLI answers for the profile in use
        return {"atlas": {"installed": True, "signed_in": bool(who), "identity": who}}

    def test_every_signed_in_profile_is_an_account_and_the_one_in_use_is_first(self):
        config.save_settings({"mongodb_atlas_profile": "agentforge-2"})
        rows = mc.cli_accounts(fresh=True)
        self.assertEqual([(r["id"], r["label"], r["active"]) for r in rows],
                         [("agentforge-2", "work@example.com", True), ("default", "me@example.com", False)])

    def test_a_profile_that_is_signed_out_is_not_offered(self):
        self.profiles.pop("agentforge-2")
        self.answers["config list"] = lambda args: ["default", "agentforge-2"]
        self.assertEqual([r["id"] for r in mc.cli_accounts(fresh=True)], ["default"])

    def test_the_status_lists_the_accounts_only_when_asked(self):
        self.assertNotIn("accounts", mc.status())
        self.assertEqual(len(mc.status(accounts=True)["accounts"]), 2)
        config.save_settings({"mongodb_client_id": "id", "mongodb_client_secret": "secret"})
        self.assertEqual(mc.status(accounts=True)["accounts"], [])        # a Service Account is the one account

    def test_every_cluster_command_runs_as_the_account_in_use(self):
        self.project_and_cluster_ready()
        config.save_settings({"mongodb_atlas_profile": "agentforge-2"})
        mc.ensure_cluster()
        for args in self.calls:
            self.assertEqual(args[-4:-2], ["-P", "agentforge-2"], args)
            self.assertEqual(args[-2:], ["-o", "json"])

    def test_the_default_profile_adds_no_profile_flag(self):
        self.project_and_cluster_ready()
        mc.ensure_cluster()
        self.assertTrue(all("-P" not in args for args in self.calls))

    def test_switching_puts_the_other_accounts_cluster_in_place_of_this_ones(self):
        self.project_and_cluster_ready()
        mc.ensure_cluster()                                              # a cluster for me@example.com
        first = config.setting("deploy_mongodb_uri")
        self.assertTrue(first)
        status = mc.switch_account("agentforge-2")
        self.assertEqual((status["account"], config.setting("mongodb_atlas_profile")), ("work@example.com", "agentforge-2"))
        self.assertFalse(config.setting("deploy_mongodb_uri"))           # not the other account's string
        self.assertFalse(status["cluster_ready"])

        self.project_and_cluster_ready()
        self.answers["clusters describe"] = {"stateName": "IDLE", "connectionStrings": {"standardSrv": "mongodb+srv://work.zzz.mongodb.net"}}
        mc.ensure_cluster()                                              # and one of its own
        second = config.setting("deploy_mongodb_uri")
        self.assertIn("work.zzz.mongodb.net", second)
        self.assertNotEqual(first, second)

        mc.switch_account("default")                                     # back: the first account's own record returns
        self.assertEqual(config.setting("deploy_mongodb_uri"), first)
        self.assertTrue(mc.status()["cluster_ready"])
        mc.switch_account("agentforge-2")
        self.assertEqual(config.setting("deploy_mongodb_uri"), second)

    def test_a_connection_string_typed_in_by_hand_stays_whichever_account_is_used(self):
        config.save_settings({"deploy_mongodb_uri": "mongodb+srv://me:pw@mine.mongodb.net/app"})
        mc.switch_account("agentforge-2")
        self.assertEqual(config.setting("deploy_mongodb_uri"), "mongodb+srv://me:pw@mine.mongodb.net/app")

    def test_the_clusters_kept_aside_never_reach_the_settings_the_studio_reads(self):
        from server_modules import httpd

        self.project_and_cluster_ready()
        mc.ensure_cluster()
        mc.switch_account("agentforge-2")
        shown = json.dumps(httpd.dispatch("GET", "/settings", {}, {}), default=str)
        self.assertNotIn("mongodb_clusters_credentials", shown)
        self.assertNotIn("agentforge_app:", shown)

    def test_switching_to_the_account_already_in_use_changes_nothing(self):
        self.project_and_cluster_ready()
        mc.ensure_cluster()
        before = config.setting("deploy_mongodb_uri")
        mc.switch_account("default")
        mc.switch_account("")
        self.assertEqual(config.setting("deploy_mongodb_uri"), before)

    def test_signing_out_an_account_runs_the_clis_logout_for_that_profile_and_forgets_its_cluster(self):
        self.project_and_cluster_ready()
        mc.ensure_cluster()
        mc.switch_account("agentforge-2")
        mc.switch_account("default")

        def logout(args):
            self.logged_out.append(args)
            return {}
        self.answers["auth logout"] = logout
        status = mc.remove_account("agentforge-2")
        self.assertEqual(self.logged_out, [["auth", "logout", "--force", "-P", "agentforge-2"]])
        self.assertEqual(status["via"], "cli")
        self.assertNotIn("agentforge-2", config.setting("mongodb_clusters_credentials") or {})

    def test_signing_out_the_account_in_use_takes_its_cluster_with_it(self):
        self.project_and_cluster_ready()
        mc.ensure_cluster()
        self.answers["auth logout"] = {}
        mc.remove_account("default")
        self.assertFalse(config.setting("deploy_mongodb_uri"))
        self.assertFalse(config.setting(mc.CLUSTER_NAME_SETTING))

    def test_a_logout_that_fails_says_why_and_changes_nothing(self):
        self.project_and_cluster_ready()
        mc.ensure_cluster()
        self.answers["auth logout"] = ValueError("not logged in")
        with self.assertRaisesRegex(ValueError, "not logged in"):
            mc.remove_account("default")
        self.assertTrue(config.setting("deploy_mongodb_uri"))


class RunningTheCliTests(AtlasCase):
    def test_json_after_a_notice_is_still_read(self):
        self.answers["orgs list"] = lambda args: None
        with mock.patch.object(cli_signin, "_run", lambda command, timeout=30: subprocess.CompletedProcess(
                command, 0, 'A new version is available\n{"results": [{"id": "1"}]}', "")):
            self.assertEqual(mc._rows(mc._atlas(["organizations", "list"])), [{"id": "1"}])

    def test_a_list_answer_without_results_is_read_too(self):
        self.assertEqual(mc._rows([{"name": "a"}, "junk"]), [{"name": "a"}])
        self.assertEqual(mc._rows({}), [])

    def test_a_missing_cli_says_so(self):
        with mock.patch.object(cli_signin, "_where", lambda name: ""), self.assertRaisesRegex(ValueError, "not installed"):
            mc._atlas(["organizations", "list"])


if __name__ == "__main__":
    unittest.main()
