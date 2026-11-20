"""Local files: reading CSV/text the way Windows and Mac tools actually save it, and safe writes."""
from __future__ import annotations

import csv
import io
import os
import sys
import tempfile
from pathlib import Path


class UserError(Exception):
    """Bad input the person or agent can fix; printed as is, exit 1."""


def utf8_stdio() -> None:
    # Windows pipes default to a legacy code page: ₹ or a Hindi name would crash the output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def decode_text(data: bytes, source: str) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16, e.g. Windows PowerShell 5.1's `>`
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")  # -sig: tolerate the BOM Excel writes
    except UnicodeDecodeError:
        raise UserError(f"{source} is not UTF-8 text. In Excel use Save As > 'CSV UTF-8 (Comma delimited)'.")


def read_text_arg(path: str) -> str:
    if path == "-":
        return decode_text(sys.stdin.buffer.read(), "The input")
    return decode_text(Path(path).read_bytes(), path)


def read_csv_arg(path: str) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(read_text_arg(path), newline="")))
    while rows and not any(cell.strip() for cell in rows[-1]):
        rows.pop()  # a trailing blank line would otherwise write or append an empty row
    if not rows:
        raise UserError("Nothing to write: the CSV is empty.")
    return rows


def write_csv(rows) -> None:
    csv.writer(sys.stdout, lineterminator="\n").writerows(rows)


def atomic_download(out: Path, fill) -> Path:
    """Write via a temp file next to `out`; only a complete download replaces an existing file."""
    out = out.resolve()
    fd, tmp = tempfile.mkstemp(prefix=".gsuite-", suffix=out.suffix, dir=out.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fill(fh)
        os.replace(tmp, out)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    return out
