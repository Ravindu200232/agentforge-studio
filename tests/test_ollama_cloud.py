"""ollama.com with just an API key: no Ollama app on the computer, the key saved once, and a real Test."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import config, httpd, ollama_cloud  # noqa: E402

REAL_BUILT_IN_ENGINE = config.built_in_engine           # before Base patches it away
KEY = "ollama-key-0123456789abcdef"
LISTED = ["deepseek-v4.1-flash", "gpt-oss:20b", "gpt-oss:120b", "deepseek-v4-pro:0813"]


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patch = mock.patch.object(config, "SETTINGS_FILE", Path(self.temp.name) / "settings.json")
        patch.start()
        self.addCleanup(patch.stop)
        ollama_cloud._cache.clear()  # noqa: SLF001
        # These are about a key saved on this computer: no built-in engine (engine.json) in the way.
        patch = mock.patch.object(config, "built_in_engine", return_value={})
        patch.start()
        self.addCleanup(patch.stop)


class NamesTests(Base):
    def test_the_ollama_apps_names_and_ollama_coms_names_map_both_ways(self):
        self.assertEqual(ollama_cloud.studio_name("deepseek-v4.1-flash"), "deepseek-v4.1-flash:cloud")
        self.assertEqual(ollama_cloud.studio_name("gpt-oss:120b"), "gpt-oss:120b-cloud")
        self.assertEqual(ollama_cloud.remote_name("deepseek-v4.1-flash:cloud", LISTED), "deepseek-v4.1-flash")
        self.assertEqual(ollama_cloud.remote_name("gpt-oss:120b-cloud", LISTED), "gpt-oss:120b")
        # A bare name ollama.com only serves tagged is matched to its one tag.
        self.assertEqual(ollama_cloud.remote_name("deepseek-v4-pro:cloud", LISTED), "deepseek-v4-pro:0813")
        self.assertEqual(ollama_cloud.remote_name("llama3.1:8b", LISTED), "llama3.1:8b")

    def test_the_client_sends_ollama_com_its_own_names(self):
        inner = mock.Mock()
        client = ollama_cloud._Names(inner)  # noqa: SLF001
        client.chat(model="gpt-oss:20b-cloud", messages=[])
        self.assertEqual(inner.chat.call_args.kwargs["model"], "gpt-oss:20b")
        client.web_search(query="x")                       # straight to ollama.com, which takes the key
        inner.web_search.assert_called_once_with(query="x", max_results=3)
        client.list()                                      # anything else passes straight through
        inner.list.assert_called_once_with()


class EngineTests(Base):
    def test_a_saved_key_makes_ollama_com_the_engine_unless_local_is_chosen(self):
        self.assertEqual(config.engine(), "local")
        config.save_settings({"ollama_api_key": KEY})
        self.assertEqual(config.engine(), "cloud")
        self.assertTrue(config.settings()["cloud"])
        config.save_settings({"engine": "local"})
        self.assertEqual(config.engine(), "local")
        self.assertFalse(config.settings()["cloud"])

    def test_a_stale_saved_cloud_flag_never_wins_over_the_key(self):
        config._write(config.SETTINGS_FILE, {"cloud": True, "model": "x:cloud"})  # noqa: SLF001
        self.assertFalse(config.settings()["cloud"])       # no key: there is no ollama.com to reach

    def test_saving_settings_never_stores_cloud_and_refuses_an_unknown_engine(self):
        with mock.patch.object(httpd, "models", return_value={"cloud": [], "ollama_ready": False, "engine": "cloud",
                                                                "cloud_enabled": True}), \
             mock.patch.object(httpd, "mongo", return_value={}):
            answer = httpd.write_settings({"ollama_api_key": KEY, "cloud": False, "engine": "cloud"})
            with self.assertRaises(ValueError):
                httpd.write_settings({"engine": "somewhere"})
        stored = json.loads(config.SETTINGS_FILE.read_text(encoding="utf-8"))
        self.assertNotIn("cloud", stored)
        self.assertEqual(answer["ollama_api_key"], "****")
        self.assertNotIn(KEY, json.dumps(answer))


class ModelsTests(Base):
    def test_with_only_a_key_the_model_list_is_ollama_coms(self):
        config.save_settings({"ollama_api_key": KEY})
        no_app = mock.Mock(side_effect=ConnectionError("no Ollama app here"))
        with mock.patch.object(httpd.ollama, "Client", return_value=SimpleNamespace(list=no_app)), \
             mock.patch.object(ollama_cloud, "remote_names", return_value=LISTED):
            answer = httpd.models({})
        self.assertFalse(answer["ollama_ready"])
        self.assertEqual(answer["engine"], "cloud")
        self.assertEqual([m["id"] for m in answer["cloud"]],
                         ["deepseek-v4.1-flash:cloud", "gpt-oss:20b-cloud", "gpt-oss:120b-cloud", "deepseek-v4-pro:0813-cloud"])


ENGINE = {"url": "https://engine.example.workers.dev", "token": "app-token-0123456789"}


class BuiltInEngineTests(Base):
    """AgentForge's own engine server holds the ollama.com key: the app only has its address and a token."""

    def engine(self):
        return mock.patch.object(config, "built_in_engine", return_value=ENGINE)

    def test_the_built_in_engine_is_used_unless_this_computer_chose_its_own(self):
        with self.engine():
            self.assertEqual(config.engine(), "built-in")
            self.assertTrue(config.settings()["cloud"])
            config.save_settings({"ollama_api_key": KEY})
            self.assertEqual(config.engine(), "built-in")          # a key alone does not replace it
            config.save_settings({"engine": "cloud"})
            self.assertEqual(config.engine(), "cloud")             # a development setup's own key, chosen
            config.save_settings({"engine": "local"})
            self.assertEqual(config.engine(), "local")

    def test_engine_json_gives_the_address_and_token(self):
        folder = Path(self.temp.name)
        (folder / "engine.json").write_text(json.dumps({"url": "https://e.example/", "token": "t"}), encoding="utf-8")
        with mock.patch.object(config, "ENGINE_FILE", folder / "engine.json"), \
             mock.patch.dict("os.environ", {"AGENTFORGE_ENGINE_URL": "", "AGENTFORGE_ENGINE_TOKEN": ""}):
            self.assertEqual(REAL_BUILT_IN_ENGINE(), {"url": "https://e.example", "token": "t"})
            (folder / "engine.json").write_text(json.dumps({"url": "", "token": "t"}), encoding="utf-8")
            self.assertEqual(REAL_BUILT_IN_ENGINE(), {})           # no address yet: not configured

    def test_requests_go_to_the_engine_with_the_app_token_never_a_key(self):
        config.save_settings({"ollama_api_key": KEY})
        with self.engine(), mock.patch.object(ollama_cloud, "remote_names", return_value=LISTED),              mock.patch.object(ollama_cloud.ollama, "Client") as made:
            client = ollama_cloud.for_engine(config.settings())
        self.assertEqual(made.call_args.kwargs["host"], ENGINE["url"])
        self.assertEqual(made.call_args.kwargs["headers"], {"Authorization": f"Bearer {ENGINE['token']}"})
        self.assertNotIn(KEY, json.dumps(made.call_args.kwargs))
        client.web_search(query="best layouts", max_results=2)     # the engine's own address, not ollama.com
        path = made.return_value._request.call_args.args[2]
        self.assertEqual(path, "/api/web_search")
        client.web_fetch(url="https://example.com")
        self.assertEqual(made.return_value._request.call_args.args[2], "/api/web_fetch")

    def test_the_model_list_is_the_engines_and_nothing_local(self):
        no_app = mock.Mock(side_effect=AssertionError("the Ollama app here is not asked"))
        with self.engine(), mock.patch.object(httpd.ollama, "Client", return_value=SimpleNamespace(list=no_app)),              mock.patch.object(ollama_cloud, "remote_names", return_value=LISTED) as names:
            answer = httpd.models({})
        self.assertEqual(answer["engine"], "built-in")
        self.assertEqual(answer["local_models"], [])
        self.assertEqual(names.call_args.kwargs, {"host": ENGINE["url"], "token": ENGINE["token"]})
        self.assertIn("gpt-oss:120b-cloud", [m["id"] for m in answer["cloud"]])

    def test_settings_never_show_the_engine_token(self):
        with self.engine(), mock.patch.object(ollama_cloud, "remote_names", return_value=LISTED),              mock.patch.object(httpd, "mongo", return_value={}):
            shown = json.dumps(httpd.read_settings({}))
        self.assertNotIn(ENGINE["token"], shown)


class TestButtonTests(Base):
    def _post(self, status):
        return mock.patch.object(ollama_cloud.httpx, "post", return_value=SimpleNamespace(status_code=status))

    def test_a_good_key_a_wrong_key_and_a_busy_key_each_say_so(self):
        with mock.patch.object(ollama_cloud, "remote_names", return_value=LISTED):
            with self._post(200) as post:
                good = httpd.ollama_test({"key": KEY})
            with self._post(401):
                wrong = httpd.ollama_test({"key": "nope"})
            with self._post(429):
                busy = httpd.ollama_test({"key": KEY})
        self.assertTrue(good["ok"])
        self.assertIn("4 cloud models", good["message"])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], f"Bearer {KEY}")
        self.assertEqual(post.call_args.kwargs["json"]["model"], "gpt-oss:20b")   # the smallest, for one token
        self.assertFalse(wrong["ok"])
        self.assertIn("refused", wrong["message"])
        self.assertTrue(busy["ok"])
        self.assertNotIn(KEY, json.dumps([good, wrong, busy]))

    def test_with_nothing_typed_the_saved_key_is_tried(self):
        config.save_settings({"ollama_api_key": KEY})
        with mock.patch.object(ollama_cloud, "remote_names", return_value=LISTED), self._post(200) as post:
            answer = httpd.ollama_test({"key": ""})
        self.assertEqual(answer["checked"], "saved")
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], f"Bearer {KEY}")

    def test_no_key_at_all_is_said_plainly(self):
        self.assertFalse(httpd.ollama_test({"key": ""})["ok"])


if __name__ == "__main__":
    unittest.main()
