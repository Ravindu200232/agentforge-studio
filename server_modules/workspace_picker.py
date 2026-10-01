"""The native Windows folder dialog used before creating a local project."""
from __future__ import annotations

import os
import subprocess

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


def choose_folder() -> str:
    """Open Explorer's folder chooser and return a safe empty folder or ``""``.

    A cancellation is normal and intentionally returns an empty value. The
    fixed PowerShell program has no customer-supplied shell content; its sole
    job is presenting Windows' own folder browser on this local machine.
    """
    if os.name != "nt":
        raise ValueError("choosing a local folder is available in the Windows desktop app")
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", _FOLDER_DIALOG],
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise ValueError("Windows could not open the folder chooser") from exc
    except subprocess.TimeoutExpired as exc:
        raise ValueError("the folder chooser took too long; try again") from exc
    if completed.returncode:
        raise ValueError("Windows could not open the folder chooser")
    selected = completed.stdout.strip()
    return str(config.validate_workspace_choice(selected)) if selected else ""
