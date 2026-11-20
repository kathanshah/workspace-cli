"""Windows 10/11 (x64 and ARM). Installer: windows/install.ps1."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .. import REPO

NAME = "Windows"
INSTALLER_URL = f"https://github.com/{REPO}/releases/latest/download/install.ps1"
INSTALL_LINE = f'powershell -ExecutionPolicy ByPass -c "irm {INSTALLER_URL} | iex"'
# The installer keeps its own pinned uv here, so a different uv on the PC never matters.
UV = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "gsuite" / "uv" / "uv.exe"


def config_dir() -> Path:
    # %APPDATA% is per user and readable only by that Windows account.
    return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / "gsuite"


def secure_dir(path: Path) -> None:
    pass  # the user profile's own permissions already restrict it to this Windows account


def secure_file(path: Path) -> None:
    pass


def path_fix() -> str:
    return f"close and reopen PowerShell or Claude Code; if it persists run: & '{UV}' tool update-shell"


def update() -> int:
    # A running gsuite.exe cannot replace itself on Windows, so the installer runs in a new window,
    # which stays open to show the result (or the error) until Enter is pressed.
    cmd = (f"Start-Sleep 2; try {{ irm {INSTALLER_URL} | iex }} catch {{ Write-Host $_ -ForegroundColor Red }} "
           "finally { Read-Host 'Press Enter to close' }")
    subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                     creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    print("Updating gsuite in a new window. Your sign-in is kept.")
    return 0


def data_dir() -> Path:
    """gsuite's private program files (its uv, kit's document engines); removed by the uninstaller."""
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "gsuite"
