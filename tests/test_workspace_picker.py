"""Platform behavior for the native project-folder picker."""
from __future__ import annotations

import subprocess
import unittest
from types import SimpleNamespace
from unittest import mock

from server_modules import workspace_picker


class WorkspacePickerTests(unittest.TestCase):
    def test_macos_uses_osascript_and_validates_the_selection(self):
        completed = SimpleNamespace(returncode=0, stdout="/Users/example/New Project/\n", stderr="")
        with mock.patch.object(workspace_picker.os, "name", "posix"), \
             mock.patch.object(workspace_picker.sys, "platform", "darwin"), \
             mock.patch.object(workspace_picker.subprocess, "run", return_value=completed) as run, \
             mock.patch.object(workspace_picker.config, "validate_workspace_choice",
                               return_value="/Users/example/New Project") as validate:
            selected = workspace_picker.choose_folder()

        self.assertEqual(selected, "/Users/example/New Project")
        self.assertEqual(run.call_args.args[0][:2], ["osascript", "-e"])
        validate.assert_called_once_with("/Users/example/New Project/")

    def test_macos_cancel_is_a_normal_empty_selection(self):
        completed = SimpleNamespace(returncode=0, stdout="", stderr="")
        with mock.patch.object(workspace_picker.os, "name", "posix"), \
             mock.patch.object(workspace_picker.sys, "platform", "darwin"), \
             mock.patch.object(workspace_picker.subprocess, "run", return_value=completed):
            self.assertEqual(workspace_picker.choose_folder(), "")

    def test_macos_picker_failure_is_named_clearly(self):
        with mock.patch.object(workspace_picker.os, "name", "posix"), \
             mock.patch.object(workspace_picker.sys, "platform", "darwin"), \
             mock.patch.object(workspace_picker.subprocess, "run",
                               side_effect=OSError("missing")):
            with self.assertRaisesRegex(ValueError, "macOS could not open"):
                workspace_picker.choose_folder()

    def test_timeout_remains_a_platform_neutral_error(self):
        with mock.patch.object(workspace_picker.os, "name", "posix"), \
             mock.patch.object(workspace_picker.sys, "platform", "darwin"), \
             mock.patch.object(workspace_picker.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("osascript", 600)):
            with self.assertRaisesRegex(ValueError, "took too long"):
                workspace_picker.choose_folder()


if __name__ == "__main__":
    unittest.main()
