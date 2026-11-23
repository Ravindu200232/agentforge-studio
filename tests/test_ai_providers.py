"""The model catalogue, multimodal chat and tool results share the same provider IDs."""
from __future__ import annotations

import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import httpx
import ollama

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src", "srs-agent", "builder-agent", "prototype-agent", "qa-agent", "deploy-agent"):
    sys.path.insert(0, str(ROOT / folder))

from server_modules import ai_providers, config, httpd, llm_tools, vision  # noqa: E402
from server_modules.session import _transient  # noqa: E402
from ollama_terminal.tools import tools_unsupported  # noqa: E402


DEPLOY_MODEL = "deploy/zai-org/glm-5.3-flash"
PNG_PREFIX = b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0d"


class ModelCatalogTests(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(config, "SETTINGS_FILE", Path(temporary) / "settings.json"))
        self.enterContext(mock.patch.object(config, "built_in_engine", return_value={}))
        self.enterContext(mock.patch.object(httpd, "mongo", return_value={}))
        self.enterContext(mock.patch.object(httpd.ollama, "Client", return_value=SimpleNamespace(
            list=lambda: SimpleNamespace(models=[SimpleNamespace(model="llava:latest")]))))

    def test_deploy_discovery_is_grouped_with_local_models_and_vision(self):
        def provider_models(request):
            self.assertEqual(request.url.path, "/api/v1/models")
            self.assertEqual(request.headers["Authorization"], "Bearer fake-deploy-secret")
            return httpx.Response(200, json={"data": [{"id": "zai-org/glm-5.3-flash"}, {"id": "org/new-model"}]})

        http_client = httpx.Client(transport=httpx.MockTransport(provider_models),
                                   headers={"Authorization": "Bearer fake-deploy-secret"})
        with mock.patch.object(ai_providers, "_catalogs", {}), \
             mock.patch.object(ai_providers.httpx, "Client", return_value=http_client), \
             mock.patch.object(vision, "capabilities", return_value={"capabilities": {}, "pending": 0}):
            result = httpd.write_settings({"deploy_api_key": "fake-deploy-secret"})
            catalog = httpd.models({})
            self.assertEqual(catalog["local"], ["llava:latest"])
            self.assertEqual([row["id"] for row in catalog["cloud"]], [DEPLOY_MODEL, "deploy/org/new-model"])
            self.assertTrue(result["ai_providers"]["deploy"]["configured"])
            self.assertNotIn("fake-deploy-secret", json.dumps(result))
            self.assertEqual(httpd.model_capabilities({})["capabilities"], {DEPLOY_MODEL: {"vision": True}})
            self.assertIs(vision.supports(DEPLOY_MODEL), True)

    def test_other_keys_survive_edits_and_custom_key_does_not_follow_a_new_url(self):
        with mock.patch.object(ai_providers, "catalogs", return_value=([], {})):
            original = {"openai_api_key": "fake-openai-secret", "anthropic_api_key": "fake-claude-secret",
                        "deepseek_api_key": "fake-deepseek-secret", "custom_api_key": "fake-custom-secret",
                        "custom_api_url": "https://provider.example/v1"}
            first = httpd.write_settings(original)
            second = httpd.write_settings({"openai_api_key": "****", "deepseek_api_key": "",
                                           "custom_api_url": "https://other.example/v1"})
        self.assertTrue(first["ai_providers"]["custom"]["saved"])
        self.assertTrue(second["ai_providers"]["openai"]["saved"])
        self.assertTrue(second["ai_providers"]["anthropic"]["saved"])
        self.assertFalse(second["ai_providers"]["deepseek"]["saved"])
        self.assertFalse(second["ai_providers"]["custom"]["saved"])
        for secret in (value for key, value in original.items() if key.endswith("_key")):
            self.assertNotIn(secret, json.dumps([first, second]))


class HostedChatTests(unittest.TestCase):
    def test_deploy_deadline_uses_the_normal_retry_policy(self):
        client = ai_providers.HostedClient("deploy", {**config.DEFAULTS, "deploy_api_key": "test-key"})
        self.addCleanup(client._http.close)
        response = httpx.Response(400, json={"error": {"message": "request deadline exceeded"}})
        with self.assertRaises(ollama.ResponseError) as caught:
            client._check(response)
        self.assertTrue(_transient(caught.exception))

    def test_tool_validation_error_does_not_mean_tools_are_unsupported(self):
        rejected = ollama.ResponseError("Assistant tool call arguments failed validation", 400)
        unsupported = ollama.ResponseError("The model does not support tool calling", 400)
        self.assertFalse(tools_unsupported(rejected))
        self.assertTrue(tools_unsupported(unsupported))

    def test_deploy_streams_tool_calls_and_replays_the_id_after_a_picture(self):
        requests = []

        def stream(*packets):
            return httpx.Response(200, text="".join(f"data: {json.dumps(packet)}\n\n" for packet in packets)
                                  + "data: [DONE]\n\n", headers={"Content-Type": "text/event-stream"})

        def provider_chat(request):
            self.assertEqual(request.url.path, "/api/v1/chat/completions")
            self.assertEqual(request.headers["Authorization"], "Bearer test-key")
            payload = json.loads(request.content)
            requests.append(payload)
            self.assertEqual(payload["model"], "zai-org/glm-5.3-flash")
            self.assertEqual(payload["reasoning_effort"], "low")
            if len(requests) == 1:
                return stream(
                    {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "call_provider",
                        "function": {"name": "read_file", "arguments": '{"path":'}}]}}]},
                    {"choices": [{"delta": {"tool_calls": [{"index": 0,
                        "function": {"arguments": '"index.html"}'}}]}, "finish_reason": "tool_calls"}]},
                )
            sent = payload["messages"]
            self.assertEqual(sent[1]["content"], [
                {"type": "text", "text": "Describe the attached image."},
                {"type": "image_url", "image_url": {
                    "url": "data:image/png;base64," + base64.b64encode(PNG_PREFIX).decode()}},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4A=="}}])
            self.assertEqual(sent[2]["tool_calls"][0]["id"], "call_provider")
            self.assertEqual(sent[3], {"role": "tool", "tool_call_id": "call_provider", "content": "File content"})
            return stream({"choices": [{"delta": {"content": "The square is blue."}, "finish_reason": "stop"}]},
                          {"choices": [], "usage": {"prompt_tokens": 15, "completion_tokens": 4}})

        messages = [{"role": "system", "content": "Review the UI."},
                    {"role": "user", "content": "Describe the attached image.",
                     "images": [PNG_PREFIX, "/9j/4A=="]}]
        with httpx.Client(transport=httpx.MockTransport(provider_chat),
                          headers={"Authorization": "Bearer test-key"}) as client:
            router = ai_providers.Client({**config.DEFAULTS, "deploy_api_key": "test-key"})
            hosted = ai_providers.HostedClient("deploy", router.saved)
            hosted._http.close()
            hosted._http = client
            with mock.patch.object(ai_providers, "HostedClient", return_value=hosted):
                usage = []
                tool = mock.Mock(project="")
                tool.call.return_value = "File content"
                reply = llm_tools.run_chat(router.chat, {"model": DEPLOY_MODEL, "messages": messages, "stream": True},
                                           tool, on_usage=usage.append)
        self.assertEqual(reply.content, "The square is blue.")
        self.assertEqual(usage[-1].prompt_eval_count, 15)
        tool.call.assert_called_once_with("read_file", {"path": "index.html"})
        self.assertIn("images", messages[1])
