"""The native folder dialog used before creating a local project."""
from __future__ import annotations

import os
import subprocess
import sys

from . import config


_FOLDER_DIALOG = r"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Choose an empty folder for this new AgentForge project'
$dialog.ShowNewFolderButton = $true
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
  [Console]::Out.Write($dialog.SelectedPath)
}
"""

_MAC_FOLDER_DIALOG = r"""
try
  set chosenFolder to choose folder with prompt "Choose an empty folder for this new AgentForge project"
  POSIX path of chosenFolder
on error number -128
  return ""
end try
"""


def choose_folder() -> str:
    """Open the operating system's folder chooser and return a safe empty folder or ``""``.

    A cancellation is normal and intentionally returns an empty value. The
    fixed picker programs have no customer-supplied shell content; their sole
    job is presenting the native folder browser on this local machine.
    """
    if os.name == "nt":
        command = ["powershell.exe", "-NoProfile", "-STA", "-Command", _FOLDER_DIALOG]
        platform_name = "Windows"
    elif sys.platform == "darwin":
        command = ["osascript", "-e", _MAC_FOLDER_DIALOG]
        platform_name = "macOS"
    else:
        raise ValueError("choosing a local folder is available in the Windows and macOS desktop apps")
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise ValueError(f"{platform_name} could not open the folder chooser") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("the folder chooser took too long; try again") from exc
    if completed.returncode:
        raise ValueError(f"{platform_name} could not open the folder chooser")
    selected = completed.stdout.strip()
    return str(config.validate_workspace_choice(selected)) if selected else ""
