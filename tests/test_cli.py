import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from ollama_terminal.cli import main


class FakeClient:
    def __init__(self, host=None, headers=None):
        self.host = host

    def show(self, model):
        return SimpleNamespace(modelinfo={"test.context_length": 8192})

    def list(self):
        return SimpleNamespace(models=[SimpleNamespace(model="gpt-oss:20b-cloud", name=None),
                                       SimpleNamespace(model="qwen3", name=None)])

    def close(self):
        pass


class FakeMessage:
    def __init__(self, content, calls=None):
        self.content = content
        self.tool_calls = calls or []

    def model_dump(self, exclude_none=True):
        data = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            data["tool_calls"] = [{"function": {"name": call.function.name,
                                                  "arguments": call.function.arguments}}
                                  for call in self.tool_calls]
        return data


class CliTests(unittest.TestCase):
    def test_slash_model_and_plan_commands(self):
        module = ModuleType("ollama")
        module.Client = FakeClient
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(sys.modules, {"ollama": module}), \
                 patch.dict(os.environ, {"OLLAMA_API_KEY": "test"}), \
                 patch("builtins.input", side_effect=["/models", "/model qwen3", "/plan",
                                                     "/act", "/cloud", "/exit"]), \
                 contextlib.redirect_stdout(output):
                status = main(["--workspace", directory])
        self.assertEqual(status, 0)
        text = output.getvalue()
        self.assertIn("gpt-oss:20b-cloud", text)
        self.assertIn("Model: qwen3", text)
        self.assertIn("Mode: plan", text)
        self.assertIn("No plan to approve", text)
        self.assertIn("Backend: https://ollama.com", text)

    def test_yes_approves_plan_and_writes_project_file(self):
        module = ModuleType("ollama")
        class PlanningClient(FakeClient):
            calls = 0

            def chat(self, **kwargs):
                PlanningClient.calls += 1
                if PlanningClient.calls == 1:
                    return SimpleNamespace(message=FakeMessage("1. Create the file. 2. Verify it."))
                if PlanningClient.calls == 2:
                    call = SimpleNamespace(function=SimpleNamespace(
                        name="write_file", arguments={"path": "done.txt", "content": "done"}))
                    return SimpleNamespace(message=FakeMessage("", [call]))
                if PlanningClient.calls == 3:
                    return SimpleNamespace(message=FakeMessage("Done. <TASK_COMPLETE>"))
                if PlanningClient.calls == 4:
                    call = SimpleNamespace(function=SimpleNamespace(
                        name="read_file", arguments={"path": "done.txt"}))
                    return SimpleNamespace(message=FakeMessage("", [call]))
                return SimpleNamespace(message=FakeMessage("Verified. <PLAN_VERIFIED>"))

        module.Client = PlanningClient
        output = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(sys.modules, {"ollama": module}), contextlib.redirect_stdout(output):
                status = main(["--yes", "--workspace", directory, "Create a file"])
            self.assertEqual(Path(directory, "done.txt").read_text(), "done")
        self.assertEqual(status, 0)
        self.assertIn("Plan status: complete", output.getvalue())


if __name__ == "__main__":
    unittest.main()
