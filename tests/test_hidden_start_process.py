"""A program an agent's command starts with Start-Process opens no window of its own on the person's screen.

Found live: every server an agent started to test an app (`Start-Process node ... next start`) opened a terminal tab titled
"next-server" on the person's desktop, again and again, for as long as the builds ran.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
for folder in (".", "src"):
    sys.path.insert(0, str(ROOT / folder))

from ollama_terminal import tools as tools_module  # noqa: E402
from ollama_terminal.tools import WorkspaceTools  # noqa: E402


@unittest.skipUnless(os.name == "nt", "the window is a Windows console")
class HiddenStartProcessTests(unittest.TestCase):
    def _run(self, command: str) -> str:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            tools = WorkspaceTools(Path(folder), client=None, approve=lambda _q: True)
            tools.permission = lambda _action: ""      # as in the Studio: a command it does not list is asked, and allowed here
            return tools.tool_run_command(command)

    def test_the_command_is_run_with_the_hiding_function_in_front(self):
        import subprocess as subprocess_module

        with patch.object(subprocess_module, "Popen") as popen:
            popen.return_value.poll.return_value = 0
            popen.return_value.wait.return_value = 0
            popen.return_value.stdout.readline.return_value = ""
            WorkspaceTools(Path("."), client=None, approve=lambda _q: True).tool_run_command("echo hi")
        shell_args = popen.call_args.args[0]
        self.assertTrue(shell_args[-1].startswith(tools_module.POWERSHELL_HIDE_START))
        self.assertTrue(shell_args[-1].endswith("echo hi"))

    def test_a_started_program_gets_a_hidden_window_by_default(self):
        answer = self._run("Get-Command Start-Process | ForEach-Object { 'kind=' + $_.CommandType }; "
                           "$p = Start-Process -FilePath cmd.exe -ArgumentList '/c','exit 0' -PassThru -Wait; "
                           "'exit=' + $p.ExitCode")
        self.assertIn("kind=Function", answer)
        self.assertIn("exit=0", answer)

    def test_a_server_started_with_its_output_redirected_still_runs_and_writes_its_log(self):
        # The command the agents write: a server started with its output in files, and stopped when the tests are done.
        answer = self._run("Write-Output begin; "
                           "$p = Start-Process -FilePath cmd.exe -ArgumentList '/c','echo served' -PassThru -Wait "
                           "-RedirectStandardOutput out.log -RedirectStandardError err.log; "
                           "'exit=' + $p.ExitCode + ' log=' + (Get-Content out.log -Raw).Trim()")
        self.assertIn("exit=0 log=served", answer)

    def test_no_new_window_still_works_with_it(self):
        # -NoNewWindow and -WindowStyle cannot be given together: the default must not be added to it.
        answer = self._run("Write-Output begin; "
                           "$p = Start-Process -FilePath cmd.exe -ArgumentList '/c','exit 4' -NoNewWindow -PassThru -Wait; "
                           "'exit=' + $p.ExitCode")
        self.assertIn("exit=4", answer)
        self.assertNotIn("cannot be specified at the same time", answer)

    def test_a_window_style_the_command_asks_for_is_kept(self):
        answer = self._run("Write-Output begin; "
                           "$p = Start-Process -FilePath cmd.exe -ArgumentList '/c','exit 5' -WindowStyle Minimized -PassThru -Wait; "
                           "'exit=' + $p.ExitCode")
        self.assertIn("exit=5", answer)
        self.assertNotIn("cannot be specified at the same time", answer)


if __name__ == "__main__":
    unittest.main()
