"""The database panel and the terminal: what a project's databases can show, its rows masked, and its own output."""
from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import cli_monitor, cli_signin, config, database_rows, preview_runtime, store, supabase_connect  # noqa: E402

PROJECT = "prj_database_test"
LINKED = {"connected": True, "ref": "abcdefghijklmnopqrst", "name": "Shop", "url": "https://abcdefghijklmnopqrst.supabase.co"}


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name) / "app"
        self.workspace.mkdir()
        self.record = Path(self.temp.name) / "record"
        self.record.mkdir()
        self.stack = "nextjs-supabase"
        self.uri = ""
        self.linked = dict(LINKED)
        for patch in (mock.patch.object(config, "workspace_for", lambda project: self.workspace),
                      mock.patch.object(config, "record_dir", lambda project: self.record),
                      mock.patch.object(config, "SETTINGS_FILE", Path(self.temp.name) / "settings.json"),
                      mock.patch.object(store, "get", lambda project: {"id": project, "stack": self.stack}),
                      mock.patch.object(supabase_connect, "status", lambda project: self.linked),
                      mock.patch.object(cli_monitor, "mongodb_uri", lambda: self.uri)):
            patch.start()
            self.addCleanup(patch.stop)

    def read(self, job: str, timeout: float = 20.0) -> dict:
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
    def test_a_supabase_stack_is_offered_the_supabase_looks_only_with_its_reference_filled_in(self):
        listing = cli_monitor.catalogue(PROJECT, scope="database")
        sets = {item["set"] for item in listing["items"]}
        self.assertEqual(sets, {"supabase"})
        self.assertEqual(listing["context"]["supabase"]["ref"], LINKED["ref"])
        tables = next(item for item in listing["items"] if item["id"] == "tables")
        self.assertEqual(tables["scope"], "database")
        self.assertEqual(tables["display"], "supabase db query --linked -f tables.sql")   # the short form, not a path
        self.assertNotIn("argv", tables)

    def test_a_mongodb_stack_with_a_saved_connection_also_gets_the_mongodb_looks_and_its_database(self):
        self.stack, self.uri = "mern-microservices", "mongodb+srv://app:pa55word-long@cluster.example.net/shop?retryWrites=true"
        listing = cli_monitor.catalogue(PROJECT, scope="database")
        self.assertEqual({item["set"] for item in listing["items"]}, {"supabase", "mongodb"})
        self.assertEqual(listing["context"]["mongodb"], {"database": "shop"})
        self.assertNotIn("pa55word", str(listing))
        self.assertEqual(cli_monitor.mongodb_database("mongodb+srv://h.example.net/?x=1"), "test")

    def test_nothing_is_offered_before_any_database_exists(self):
        self.linked = {"connected": False}
        self.assertEqual(cli_monitor.catalogue(PROJECT, scope="database")["items"], [])
        with self.assertRaisesRegex(ValueError, "no database connected"):
            cli_monitor.MONITORS.start(PROJECT, "tables", scope="database")

    def test_a_file_placeholder_names_only_a_query_or_script_of_the_studios_own(self):
        self.assertTrue(cli_monitor._asset("file.tables").endswith("tables.sql"))
        self.assertTrue(cli_monitor._asset("script.mongo-inspect").endswith("mongo-inspect.mjs"))
        for bad in ("file.../settings", "file.nope", "file.Tables", "script.../../x"):
            self.assertIsNone(cli_monitor._asset(bad), bad)
        filled, why = cli_monitor._fill("{{file.nope}}", {})
        self.assertIsNone(filled)
        self.assertIn("file.nope", why)

    def test_every_query_the_catalogue_names_is_read_only(self):
        for path in cli_monitor.QUERIES.glob("*.sql"):
            text = path.read_text(encoding="utf-8").lower()
            for word in ("insert ", "update ", "delete ", "drop ", "alter ", "truncate ", "grant ", "create "):
                self.assertNotIn(word, text.replace("updated_at", "").replace("created_at", "").replace("created_last", ""),
                                 f"{path.name} contains {word.strip()}")


class EnvironmentTests(Base):
    def test_the_supabase_tool_gets_the_accounts_token_and_never_prints_it_or_the_projects_keys(self):
        stand_in = {"targets": {"supabase": ["test"]}, "sets": {"test": {"tool": "python", "title": "Supabase", "env": "supabase",
                    "commands": [{"id": "who", "group": "T", "label": "Who", "argv": [
                        "-c", "import os;print(os.environ['SUPABASE_ACCESS_TOKEN']);print('key anon-key-value-1234')"]}]}}}
        with mock.patch.object(cli_monitor, "_catalogue", lambda scope="deploy": stand_in), \
             mock.patch.object(cli_signin, "_where", lambda name: sys.executable if name == "python" else ""), \
             mock.patch.object(supabase_connect, "_env_with_token", lambda: {"SUPABASE_ACCESS_TOKEN": "sbp_0123456789abcdef"}), \
             mock.patch.object(supabase_connect, "record", lambda project: {"anon_key": "anon-key-value-1234"}):
            done = self.read(cli_monitor.MONITORS.start(PROJECT, "who", scope="database")["job"])
        self.assertEqual(done["lines"], ["<hidden>", "key <hidden>"])

    def test_the_mongodb_reader_gets_the_connection_string_in_its_environment_only(self):
        self.stack, self.uri = "vite-mongo", "mongodb+srv://app:pa55word-long@cluster.example.net/shop"
        env, hidden = cli_monitor._set_environment("mongodb", PROJECT)
        self.assertEqual(env["CHECK_URI"], self.uri)
        self.assertIn("pa55word-long", hidden)
        self.assertIn(self.uri, hidden)


class RowsTests(Base):
    def test_a_table_is_named_by_quoted_identifiers_only(self):
        sql = database_rows._supabase_sql("public", "orders")
        self.assertIn('from "public"."orders" limit 20', sql)
        for bad in ('orders"; drop table users; --', "orders limit 1", "1orders", "", "a" * 70):
            with self.assertRaises(ValueError, msg=bad):
                database_rows._supabase_sql("public", bad)
        with self.assertRaises(ValueError):
            database_rows._supabase_sql("public; select", "orders")

    def test_credential_fields_and_known_secrets_are_masked_everywhere_in_a_row(self):
        rows, masked = database_rows._masked_rows([
            {"email": "a@example.com", "password_hash": "$2b$10$abc", "profile": {"apiKey": "k-123", "note": "uses sbp_0123456789abcdef"},
             "reset_token": None, "tags": ["x"]},
        ], ["sbp_0123456789abcdef"])
        row = rows[0]
        self.assertEqual(row["password_hash"], "<masked>")
        self.assertEqual(row["profile"]["apiKey"], "<masked>")
        self.assertEqual(row["profile"]["note"], "uses <hidden>")
        self.assertIsNone(row["reset_token"])                 # nothing there to hide
        self.assertEqual(row["email"], "a@example.com")
        self.assertEqual(masked, ["apiKey", "password_hash"])

    def test_a_collection_name_is_checked_before_it_is_read(self):
        self.uri = "mongodb+srv://app:pa55word-long@cluster.example.net/shop"
        for bad in ("$where", "system.users", "", "x" * 130):
            with self.assertRaises(ValueError, msg=bad):
                database_rows.sample(PROJECT, {"source": "mongodb", "collection": bad})
        with self.assertRaises(ValueError):
            database_rows.sample(PROJECT, {"source": "mysql", "table": "x"})

    def test_the_tools_json_is_found_among_its_progress_lines(self):
        self.assertEqual(database_rows._json_in('Initialising login role...\n{"rows": [{"a": 1}]}\nA new version is available'),
                         {"rows": [{"a": 1}]})


class ShellTests(Base):
    def setUp(self):
        super().setUp()
        patch = mock.patch.object(cli_monitor, "_project_environment",
                                  lambda project: ({"APP_FLAG": "on-for-this-app", "DB_PASSWORD": "pa55word-long"}, ["pa55word-long"]))
        patch.start()
        self.addCleanup(patch.stop)

    def test_a_typed_command_runs_in_the_project_folder_with_the_apps_variables_masked(self):
        command = ("Write-Output $env:APP_FLAG; Write-Output $env:DB_PASSWORD; (Get-Location).Path" if os.name == "nt"
                   else 'echo "$APP_FLAG"; echo "$DB_PASSWORD"; pwd')
        started = cli_monitor.MONITORS.start_shell(PROJECT, command)
        self.assertEqual(started["display"], command)
        done = self.read(started["job"], 60)
        self.assertEqual(done["status"], "done", done["lines"])
        self.assertEqual(done["lines"][:2], ["on-for-this-app", "<hidden>"])
        self.assertEqual(Path(done["lines"][2]).resolve(), self.workspace.resolve())

    def test_commands_that_would_end_the_studio_or_harm_the_machine_are_refused(self):
        for bad in ("taskkill /F /IM node.exe", "Stop-Process -Name node", "pkill node", "rm -rf /", "sudo rm x", ""):
            with self.assertRaises(ValueError, msg=bad):
                cli_monitor.MONITORS.start_shell(PROJECT, bad)


class PreviewLogTests(Base):
    def setUp(self):
        super().setUp()
        for patch in (mock.patch.object(preview_runtime, "status", lambda project: {"status": "running", "url": "http://127.0.0.1:4100/",
                                                                                     "port": 4100, "detail": ""}),
                      mock.patch.object(preview_runtime, "_log_secrets", lambda project: ["s3cret-value-123"])):
            patch.start()
            self.addCleanup(patch.stop)
        self.log = self.record / "preview.log"

    def test_a_start_writes_its_line_into_the_log(self):
        with mock.patch.object(preview_runtime.subprocess, "Popen") as popen:
            preview_runtime._launch([sys.executable, str(self.workspace / "server.js")], self.workspace, {"PORT": "4100"}, self.log)
        popen.assert_called_once()
        text = self.log.read_text(encoding="utf-8")
        self.assertIn(preview_runtime.RUN_MARK, text)
        self.assertIn("server.js · PORT 4100", text)

    def test_the_terminal_reads_the_current_run_then_only_what_is_new_and_never_half_a_line(self):
        self.log.write_bytes(f"old run\n{preview_runtime.RUN_MARK}npm run dev · PORT 4100 ──\n\x1b[32mready\x1b[39m s3cret-value-123\npart".encode())
        first = preview_runtime.read_log(PROJECT, -1)
        self.assertTrue(first["text"].startswith(preview_runtime.RUN_MARK))
        self.assertNotIn("old run", first["text"])
        self.assertIn("\x1b[32mready\x1b[39m <hidden>", first["text"])      # colour kept, secret not
        self.assertNotIn("part", first["text"])                               # half a line waits
        self.assertEqual(first["cwd"], str(self.workspace))
        with self.log.open("ab") as handle:
            handle.write(b"ial line\nnext\n")
        second = preview_runtime.read_log(PROJECT, first["next"])
        self.assertEqual(second["text"], "partial line\nnext\n")
        self.assertEqual(preview_runtime.read_log(PROJECT, second["next"])["text"], "")
        replaced = preview_runtime.read_log(PROJECT, 10 ** 9)                  # a log that shrank starts over
        self.assertTrue(replaced["text"].startswith(preview_runtime.RUN_MARK))


if __name__ == "__main__":
    unittest.main()
