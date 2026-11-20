"""Where kit writes. One rule: never overwrite a file that is already there.

`report.pdf` taken -> `report (1).pdf`, then `report (2).pdf`. Every file is written to a temp file
in the same folder first and then published under a name that is checked atomically to be free,
so neither a crash nor two kit commands running at once can replace someone's file.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time
from pathlib import Path

from workspace_cli.files import UserError

BAD_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    """A file name Windows and macOS both accept (tab names and web titles can hold anything)."""
    return BAD_NAME.sub("_", name).strip(" .") or "file"


def free_name(path: Path) -> Path:
    if not path.exists():
        return path
    n = 1
    while True:
        candidate = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def check_folder(folder: Path) -> Path:
    """Outputs go to ordinary folders: never into hidden ones (.claude, .ssh, .config, ...),
    where a file could change how programs or AI agents behave."""
    folder = folder.expanduser().resolve()
    if any(part.startswith(".") and part not in (".", "..") for part in folder.parts):
        raise UserError(f"kit does not write into hidden folders ({folder}). Choose an ordinary folder.")
    if not folder.is_dir():
        raise UserError(f"Folder {folder} does not exist.")
    return folder


def target(src: Path, out: str | None, ext: str) -> Path:
    """The output path for `src`: `out` as given, or just an extension ("pdf", ".pdf") meaning
    "next to the input, same name", or nothing meaning the same with `ext`."""
    if out is None or out.lstrip(".").lower() == ext.lstrip(".").lower() and "/" not in out and "\\" not in out:
        path = src.with_suffix("." + ext.lstrip("."))
    else:
        path = Path(out).expanduser()
        if path.suffix == "":
            raise UserError(f"Give the output a file extension, e.g. {path.name}.{ext.lstrip('.')}")
    check_folder(path.parent if str(path.parent) else Path("."))
    return path


def _publish(tmp: str, path: Path) -> Path:
    """Give the finished temp file its name without ever replacing an existing file."""
    for _ in range(1000):
        final = free_name(path)
        for attempt in range(6):
            try:
                if sys.platform == "win32":
                    os.rename(tmp, final)  # refuses (FileExistsError) if the name was taken meanwhile
                else:
                    try:
                        os.link(tmp, final)  # atomic, and refuses an existing name
                        os.unlink(tmp)
                    except FileExistsError:
                        raise
                    except OSError:  # file systems without hard links (exFAT, some network drives)
                        if final.exists():
                            raise FileExistsError(final)
                        os.replace(tmp, final)
                return final
            except FileExistsError:
                break  # someone took the name: pick the next free one
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.3)  # antivirus or OneDrive looking at the new file; it lets go quickly
    raise UserError(f"Could not find a free file name next to {path}.")


def save(path: Path, write) -> Path:
    """Write via `write(temp_path)`; returns the final (never pre-existing) path."""
    path = path.expanduser().resolve()
    check_folder(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=".kit-", suffix=path.suffix, dir=path.parent)
    os.close(fd)
    try:
        write(Path(tmp))
        return _publish(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def source(path: str, *exts: str) -> Path:
    p = Path(path).expanduser()
    if not p.exists():
        raise UserError(f"File {path} does not exist.")
    if p.is_dir():
        raise UserError(f"{path} is a folder, not a file.")
    if exts and p.suffix.lower() not in exts:
        raise UserError(f"{p.name} is not one of {', '.join(exts)}.")
    return p
