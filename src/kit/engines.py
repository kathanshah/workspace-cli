"""pandoc and Typst, the document engines behind `kit convert`.

Neither has a ready-built Python package for every staff laptop (no Windows-on-ARM wheels), so
kit downloads the official release for this computer once, checks its SHA-256 against the value
pinned here, and keeps it in gsuite's private folder. The installer runs `kit setup`; if that was
skipped, the first conversion downloads them. Windows on ARM runs pandoc's x64 build through
Windows' built-in emulation; Typst has a native ARM build.

To update: change the versions and every hash (from each GitHub release's asset list), release.
"""
from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from workspace_cli.files import UserError
from workspace_cli.platforms import current

PANDOC = "3.14"
TYPST = "0.15.1"
_P = f"https://github.com/jgm/pandoc/releases/download/{PANDOC}/pandoc-{PANDOC}-"
_T = f"https://github.com/typst/typst/releases/download/v{TYPST}/typst-"
DOWNLOADS = {
    ("pandoc", "mac-arm64"): (_P + "arm64-macOS.zip", "58d6593884fec9d4424b641b92503c316d9c36decb2891ff8d73ae74dd3b6304"),
    ("pandoc", "mac-x64"): (_P + "x86_64-macOS.zip", "891708579061e7b1c1a6ce0df30ebb3cb2b6d0ca045ed3c8554ab830c1e0c270"),
    ("pandoc", "win-x64"): (_P + "windows-x86_64.zip", "0144b96e8c7b023fd382ec5ef5bdc475e873f1019d6fa72502492df2c9a94a3b"),
    ("pandoc", "win-arm64"): (_P + "windows-x86_64.zip", "0144b96e8c7b023fd382ec5ef5bdc475e873f1019d6fa72502492df2c9a94a3b"),
    ("typst", "mac-arm64"): (_T + "aarch64-apple-darwin.tar.xz", "48f62ed034aa3a7978309579ac6ca00045e2ef0da73114e8af27cfd8e74dc05a"),
    ("typst", "mac-x64"): (_T + "x86_64-apple-darwin.tar.xz", "7f9fdd9584866245de9a79e0add8f9236fae6f40a8a45e2c4771ccc14db4e0fa"),
    ("typst", "win-x64"): (_T + "x86_64-pc-windows-msvc.zip", "19ce3551153c2fe7ee9fa2f95208310c8f4d3209fedb699e0333faf8913f6736"),
    ("typst", "win-arm64"): (_T + "aarch64-pc-windows-msvc.zip", "4ab28e1b71ec3184d38d580ab797f499b6770d952b6b19167be5cea5c2662e14"),
}
VERSIONS = {"pandoc": PANDOC, "typst": TYPST}


class DownloadFailed(Exception):
    """The engine could not be downloaded (network); cli maps it to exit 5."""


def machine() -> str:
    arch = platform.machine().lower()
    arm = arch in ("arm64", "aarch64")
    if sys.platform == "darwin":
        return "mac-arm64" if arm else "mac-x64"
    if sys.platform == "win32":
        return "win-arm64" if arm else "win-x64"
    raise UserError("kit's document engines are set up for Windows and macOS only.")


def tools_dir() -> Path:
    return Path(os.environ.get("KIT_TOOLS") or current.data_dir() / "tools")


def exe_path(name: str) -> Path:
    return tools_dir() / f"{name}-{VERSIONS[name]}" / (name + (".exe" if sys.platform == "win32" else ""))


def ready(name: str) -> bool:
    return exe_path(name).is_file()


def _download(url: str, sha256: str) -> bytes:
    import requests

    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        raise DownloadFailed(f"could not download {url}: {e}") from e
    if hashlib.sha256(r.content).hexdigest() != sha256:
        raise DownloadFailed(f"the download of {url} was damaged or changed (checksum mismatch); try again")
    return r.content


def _member(data: bytes, url: str, name: str) -> bytes:
    """The engine's own program file from the release archive, wherever it sits inside."""
    want = {name, name + ".exe"}
    if url.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if Path(info.filename).name in want and not info.is_dir():
                    return z.read(info)
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as t:
            for info in t.getmembers():
                if Path(info.name).name in want and info.isfile():
                    return t.extractfile(info).read()
    raise DownloadFailed(f"{name} was not found inside {url}")


def install(name: str, quiet: bool = False) -> Path:
    exe = exe_path(name)
    if exe.is_file():
        return exe
    url, sha = DOWNLOADS[(name, machine())]
    if not quiet:
        print(f"Downloading {name} {VERSIONS[name]} (one time)...", file=sys.stderr)
    blob = _member(_download(url, sha), url, name)
    exe.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=exe.parent, prefix=".download-")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(blob)
        os.chmod(tmp, os.stat(tmp).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        if not exe.is_file():  # another kit may have finished first (and Windows cannot replace a running .exe)
            try:
                os.replace(tmp, exe)
            except PermissionError:
                if not exe.is_file():
                    raise
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    for old in tools_dir().glob(f"{name}-*"):  # earlier versions
        if old != exe.parent and old.is_dir():
            shutil.rmtree(old, ignore_errors=True)
    return exe


def setup() -> int:
    for name in VERSIONS:
        was = ready(name)
        install(name)
        print(f"{name} {VERSIONS[name]} {'ready' if was else 'installed'}: {exe_path(name)}")
    return 0
