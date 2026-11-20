"""`kit sheet`: local spreadsheets (.xlsx, .xlsm, .xls, .csv, .tsv): read, convert, combine.

Also used by `gsuite read` for Excel and CSV files uploaded to Google Drive (rows_from_bytes).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import re
import sys
from pathlib import Path

from workspace_cli.files import UserError, write_csv

from .outputs import safe_name, save, source, target

READ_LIMIT = 500
SHEETS = (".xlsx", ".xlsm", ".xls", ".csv", ".tsv", ".txt")
BAD_TAB = re.compile(r"[\[\]:*?/\\]")
# A number Excel should store as a number: no leading zero (IDs, PIN codes), no "+" (phone
# numbers), at most 15 digits (Excel's precision; longer are account or card numbers).
NUMBER = re.compile(r"-?(0|[1-9]\d{0,14})(\.\d+)?")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    if isinstance(value, dt.datetime):
        return value.date().isoformat() if value.time() == dt.time(0) else value.isoformat(sep=" ")
    if isinstance(value, (dt.date, dt.time)):
        return value.isoformat()
    return str(value)


def decode(data: bytes, name: str) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        pass
    text = data.decode("utf-8-sig", errors="replace")
    bad = text.count("\ufffd")
    real_utf8 = any(ord(ch) > 127 and ch != "\ufffd" for ch in text)  # e.g. ₹ or Hindi decoded fine
    if real_utf8 and bad <= max(3, len(text) // 1000):
        # UTF-8 with a stray damaged byte or two: keep the ₹ and Hindi, mark the damage.
        print(f"({name} has {bad} damaged character(s), shown as \ufffd)", file=sys.stderr)
        return text
    # Excel's plain "CSV (Comma delimited)" on Windows: the ANSI code page. Readable, but ₹ and
    # Indian scripts were already lost when it was saved.
    print(f"({name} is not UTF-8; read it as Windows ANSI text. Save as 'CSV UTF-8' to keep ₹ and Hindi.)",
          file=sys.stderr)
    return data.decode("cp1252", errors="replace")


def _csv_rows(text: str, tsv: bool) -> list[list[str]]:
    if tsv:
        delim = "\t"
    else:
        try:
            delim = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
        except csv.Error:
            delim = ","
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delim))


def _unquote(tab: str) -> str:
    tab = tab.strip()
    return tab[1:-1].replace("''", "'") if len(tab) > 1 and tab[0] == tab[-1] == "'" else tab


def workbook_tabs(data: bytes, ext: str, name: str) -> list[tuple[str, bool]]:
    """(tab name, hidden) for each tab of an Excel file."""
    ext = _real_kind(data, ext)
    if ext == ".xls":
        book = _open_xls(data, name)
        return [(s.name, s.visibility != 0) for s in book.sheets()]
    if ext != ".xlsx":
        return [(Path(name).stem, False)]
    wb = _open_xlsx(data, name)
    return [(ws.title, ws.sheet_state != "visible") for ws in wb.worksheets]


def _open_xlsx(data: bytes, name: str):
    import zipfile

    import openpyxl

    try:
        return openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError) as e:
        raise UserError(f"Could not open {name} (password-protected or damaged?): {e}")
    except Exception as e:  # openpyxl's own InvalidFileException and friends
        if "openpyxl" in type(e).__module__:
            raise UserError(f"Could not open {name} (password-protected or damaged?): {e}")
        raise


def _open_xls(data: bytes, name: str):
    import xlrd

    try:
        return xlrd.open_workbook(file_contents=data)
    except Exception as e:
        raise UserError(f"Could not open {name} as an old-style .xls file: {e}")


def _real_kind(data: bytes, ext: str) -> str:
    """Bank and ERP portals often save a web page or plain text under an .xls name."""
    if ext in (".xls", ".xlsx", ".xlsm"):
        if data[:4] == b"PK\x03\x04":
            return ".xlsx"
        if data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            return ".xls"
        head = data[:2048].lstrip(b"\xef\xbb\xbf\xff\xfe \t\r\n").lower()
        if head.startswith((b"<", b"<\x00")) or b"<table" in data[:65536].lower():
            return ".html"
        return ".csv"  # tab- or comma-separated text
    return ext


def _html_rows(data: bytes, name: str) -> list[list[str]]:
    import pandas as pd

    try:
        frames = pd.read_html(io.StringIO(decode(data, name)), header=None, flavor="lxml")
    except ValueError:
        raise UserError(f"{name} is a web page saved with an Excel name, and it holds no table.")
    best = max(frames, key=lambda f: f.shape[0] * f.shape[1])
    print(f"({name} is really a web page saved as Excel; read its largest table)", file=sys.stderr)
    return [[_cell(None if pd.isna(v) else v) for v in row] for row in best.itertuples(index=False)]


def rows_from_bytes(data: bytes, ext: str, name: str, tab: str | None = None) -> tuple[list[list[str]], str]:
    """The rows of one tab (default: the first visible one), all as text; and the tab's name."""
    ext = _real_kind(data, ext.lower())
    if ext == ".html":
        rows = _html_rows(data, name)
        label = Path(name).stem
    elif ext in (".csv", ".tsv", ".txt"):
        rows = _csv_rows(decode(data, name), ext == ".tsv")
        label = Path(name).stem
    elif ext == ".xls":
        import xlrd

        book = _open_xls(data, name)
        names = book.sheet_names()
        sheet = _pick(names, [book.sheet_by_index(i).visibility != 0 for i in range(len(names))], tab, name)
        s = book.sheet_by_name(sheet)
        rows = []
        for r in range(s.nrows):
            row = []
            for c in range(s.ncols):
                cell = s.cell(r, c)
                if cell.ctype == xlrd.XL_CELL_DATE:
                    row.append(_cell(xlrd.xldate_as_datetime(cell.value, book.datemode)))
                elif cell.ctype == xlrd.XL_CELL_BOOLEAN:
                    row.append(_cell(bool(cell.value)))
                else:
                    row.append(_cell(cell.value))
            rows.append(row)
        label = sheet
    elif ext in (".xlsx", ".xlsm"):
        wb = _open_xlsx(data, name)
        names = [ws.title for ws in wb.worksheets]
        sheet = _pick(names, [ws.sheet_state != "visible" for ws in wb.worksheets], tab, name)
        ws = wb[sheet]
        ws.reset_dimensions()  # some exporters store a wrong size ("A1") for a full sheet
        rows = [[_cell(v) for v in row] for row in ws.iter_rows(values_only=True)]
        label = sheet
    else:
        raise UserError(f"{name} is not a spreadsheet kit reads ({', '.join(SHEETS)}).")
    while rows and not any(c.strip() for c in rows[-1]):
        rows.pop()
    width = max((len(r) for r in rows), default=0)
    # Trim columns that are empty in every row (Excel often reports a used range far past the data).
    while width and all(len(r) < width or not r[width - 1].strip() for r in rows):
        width -= 1
    return [r[:width] for r in rows], label


def _pick(names: list[str], hidden: list[bool], tab: str | None, file: str) -> str:
    if tab is not None:
        want = _unquote(tab)
        if want not in names:
            raise UserError(f"No tab {want!r} in {file}. Tabs: {', '.join(names)}")
        return want
    visible = [n for n, h in zip(names, hidden) if not h]
    return (visible or names)[0]


def load(path: Path, tab: str | None) -> tuple[list[list[str]], str]:
    return rows_from_bytes(path.read_bytes(), path.suffix, path.name, tab)


def tabs(path_arg: str) -> None:
    path = source(path_arg, *SHEETS)
    if path.suffix.lower() in (".csv", ".tsv", ".txt"):
        rows, _ = load(path, None)
        print(f"{path.name}: a single table ({len(rows)} rows)")
        return
    for name, hidden in workbook_tabs(path.read_bytes(), path.suffix.lower(), path.name):
        rows, _ = load(path, name if _real_kind(path.read_bytes()[:65536], path.suffix.lower()) in (".xls", ".xlsx") else None)
        cols = max((len(r) for r in rows), default=0)
        print(f"  {name}  ({len(rows)} rows x {cols} cols)" + ("  [hidden]" if hidden else ""))


def read(path_arg: str, tab: str | None, show_all: bool) -> None:
    path = source(path_arg, *SHEETS)
    rows, _ = load(path, tab)
    if not show_all and len(rows) > READ_LIMIT:
        write_csv(rows[:READ_LIMIT])
        print(f"(showing the first {READ_LIMIT} of {len(rows)} rows; add --all for every row)", file=sys.stderr)
    else:
        write_csv(rows)


def _typed(value: str):
    if NUMBER.fullmatch(value):
        return float(value) if "." in value else int(value)
    return value


def write_xlsx(tmp: Path, tables: list[tuple[str, list[list[str]]]], as_text: bool = False) -> None:
    """One tab per (name, rows). Text that starts with '=' stays text: never a formula."""
    import openpyxl
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE as ILLEGAL
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    used: set[str] = set()
    for name, rows in tables:
        title = BAD_TAB.sub(" ", name).strip()[:31] or "Sheet"
        base, n = title, 1
        while title.lower() in used:
            n += 1
            title = f"{base[:31 - len(str(n)) - 1]} {n}"
        used.add(title.lower())
        ws = wb.create_sheet(title)
        widths: dict[int, int] = {}
        for r, row in enumerate(rows, 1):
            for c, value in enumerate(row, 1):
                cell = ws.cell(row=r, column=c)
                value = ILLEGAL.sub("", value)  # control characters Excel refuses
                cell.value = value if as_text else _typed(value)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    cell.data_type = "s"
                elif isinstance(cell.value, float):
                    cell.number_format = "0." + "0" * len(value.split(".")[1])  # 12.50 stays 12.50
                widths[c] = max(widths.get(c, 0), len(value))
        for c, w in widths.items():
            ws.column_dimensions[get_column_letter(c)].width = min(60, max(8, w + 2))
    wb.save(tmp)


def write_rows(tmp: Path, rows: list[list[str]], tsv: bool = False) -> None:
    # UTF-8 with a BOM: Excel on Windows then shows ₹ and Hindi correctly when the file is opened.
    with open(tmp, "w", encoding="utf-8-sig", newline="") as fh:
        csv.writer(fh, delimiter="\t" if tsv else ",", lineterminator="\r\n").writerows(rows)


def convert(path_arg: str, out_arg: str, tab: str | None, all_tabs: bool, as_text: bool) -> None:
    path = source(path_arg, *SHEETS)
    ext_out = "." + out_arg.rsplit(".", 1)[-1].lower() if "." in out_arg else "." + out_arg.lower()
    if ext_out not in (".csv", ".tsv", ".xlsx"):
        raise UserError("kit sheet convert makes .csv, .tsv or .xlsx files.")
    out = target(path, out_arg, ext_out)
    ext_in = path.suffix.lower()
    if all_tabs and ext_in in (".xlsx", ".xlsm", ".xls"):
        names = [n for n, _ in workbook_tabs(path.read_bytes(), ext_in, path.name)]
        if ext_out == ".xlsx":
            raise UserError("--all-tabs is for saving each tab as its own .csv file.")
        for name in names:
            rows, _ = load(path, name)
            each = out.with_name(safe_name(f"{out.stem} - {name}") + ext_out)
            print(f"wrote {save(each, lambda tmp: write_rows(tmp, rows, ext_out == '.tsv'))} ({len(rows)} rows)")
        return
    rows, label = load(path, tab)
    if ext_out == ".xlsx":
        final = save(out, lambda tmp: write_xlsx(tmp, [(label, rows)], as_text))
    else:
        final = save(out, lambda tmp: write_rows(tmp, rows, ext_out == ".tsv"))
    print(f"wrote {final} ({len(rows)} rows)")


def combine(inputs: list[str], out_arg: str, stack: bool) -> None:
    paths = [source(p, *SHEETS) for p in inputs]
    if len(paths) < 2:
        raise UserError("Give at least two files to combine.")
    out = target(paths[0], out_arg, "xlsx")
    tables: list[tuple[str, list[list[str]]]] = []
    for p in paths:
        if _real_kind(p.read_bytes()[:65536], p.suffix.lower()) in (".xlsx", ".xls"):
            for name, hidden in workbook_tabs(p.read_bytes(), p.suffix.lower(), p.name):
                if hidden and stack:
                    continue  # hidden tabs (lookups, old data) do not belong in one combined table
                tables.append((f"{p.stem} - {name}", load(p, name)[0]))
        else:
            tables.append((p.stem, load(p, None)[0]))
    if stack:
        header = next((rows[0] for _, rows in tables if rows), [])
        merged = [header]
        for name, rows in tables:
            body = rows[1:] if rows and rows[0] == header else rows
            if rows and rows[0] != header:
                print(f"(note: {name} has different column headings; its rows were added as they are)",
                      file=sys.stderr)
            merged += body
        tables = [("Combined", merged)]
    if out.suffix.lower() == ".xlsx":
        final = save(out, lambda tmp: write_xlsx(tmp, tables))
        print(f"wrote {final} ({len(tables)} tab{'s' if len(tables) != 1 else ''})")
    elif out.suffix.lower() in (".csv", ".tsv") and stack:
        final = save(out, lambda tmp: write_rows(tmp, tables[0][1], out.suffix.lower() == ".tsv"))
        print(f"wrote {final} ({len(tables[0][1])} rows)")
    else:
        raise UserError("Combine into an .xlsx (one tab per input), or add --stack for one .csv table.")
