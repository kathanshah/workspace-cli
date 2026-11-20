"""macOS (Apple Silicon and Intel). Installer: macos/install.sh. Also serves Linux."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .. import REPO

NAME = "macOS"
INSTALLER_URL = f"https://github.com/{REPO}/releases/latest/download/install.sh"
INSTALL_LINE = f"curl -LsSf {INSTALLER_URL} | sh"
# The installer keeps its own pinned uv here, so a different uv on the Mac never matters.
UV = Path.home() / ".local" / "share" / "gsuite" / "uv" / "uv"


def config_dir() -> Path:
    return Path.home() / ".config" / "gsuite"


def secure_dir(path: Path) -> None:
    os.chmod(path, 0o700)


def secure_file(path: Path) -> None:
    os.chmod(path, 0o600)


def path_fix() -> str:
    return f"open a new Terminal window; if it persists run: {UV} tool update-shell"


def update() -> int:
    # Replacing the running program is fine on macOS, so the installer runs right here.
    return subprocess.call(["sh", "-c", INSTALL_LINE])
