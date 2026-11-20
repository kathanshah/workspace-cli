"""Everything that differs between Windows and macOS lives in one of two files:

    platforms/windows.py   Windows 10/11, x64 and ARM (PowerShell installer)
    platforms/macos.py     macOS, Apple Silicon and Intel (sh installer); also used on Linux

Each exposes the same names: NAME, INSTALLER_URL, INSTALL_LINE, UV, config_dir(), secure_dir(),
secure_file(), path_fix(), update(). The rest of gsuite calls `current` and never checks the OS.
"""
import sys

if sys.platform == "win32":
    from . import windows as current
else:
    from . import macos as current

__all__ = ["current"]
