"""The Google operations behind each command. Prints results; raises on problems (cli.py maps them).

Reads and repeatable changes use api.run (retried); changes that must not happen twice (append,
append-doc, create, add-tab) use api.run_once.
"""
from __future__ import annotations

import csv
import io
import re
import sys
from pathlib import Path

from . import api
from .files import UserError, atomic_download, read_csv_arg, read_text_arg, write_csv

GOOGLE = "application/vnd.google-apps."
MIME = {"sheet": GOOGLE + "spreadsheet", "doc": GOOGLE + "document"}
SLIDES = GOOGLE + "presentation"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
EXPORT = {".xlsx": XLSX, ".csv": "text/csv", ".pdf": "application/pdf", ".docx": DOCX,
          ".md": "text/markdown", ".txt": "text/plain"}
# What each Google file type can be saved as (Drive's export formats that gsuite offers).
CAN_EXPORT = {MIME["sheet"]: [".xlsx", ".csv", ".pdf"], MIME["doc"]: [".docx", ".pdf", ".md", ".txt"],
              SLIDES: [".pdf"]}
KINDS = {MIME["sheet"]: "Google Sheet", MIME["doc"]: "Google Doc", SLIDES: "Google Slides",
         GOOGLE + "folder": "folder", GOOGLE + "form": "Google Form", XLSX: "Excel (.xlsx)",
         "application/vnd.ms-excel": "Excel (.xls)", "text/csv": "CSV", "application/pdf": "PDF",
         DOCX: "Word (.docx)"}
READ_LIMIT = 500  # rows printed by default, so one command cannot flood an agent's context
CELL_REF = re.compile(r"\$?[A-Za-z]{0,3}\$?\d*(:\$?[A-Za-z]{0,3}\$?\d*)?")


def kind_name(mime: str) -> str:
    return KINDS.get(mime) or (mime.rsplit(".", 1)[-1] if mime.startswith(GOOGLE) else mime.rsplit("/", 1)[-1])


def meta(fid: str) -> dict:
    return api.run(api.drive().files().get(fileId=fid, fields="id,name,mimeType", supportsAllDrives=True))


def wrong_type(m: dict, wanted: str) -> UserError:
    """The right advice for a file that is not the Google Sheet or Doc a command needs."""
    mime, name = m["mimeType"], m["name"]
    if mime == MIME["doc"] and wanted == "Sheet":
        return UserError(f"'{name}' is a Google Doc, not a Sheet: use `gsuite doc` to read it.")
    if mime == MIME["sheet"] and wanted == "Doc":
        return UserError(f"'{name}' is a Google Sheet, not a Doc: use `gsuite read` to read it.")
    if mime.startswith(GOOGLE):
        return UserError(f"'{name}' is a {kind_name(mime)}; gsuite works with Google Sheets and Docs"
                         + (", and can save this one as a PDF with `gsuite export`." if mime in CAN_EXPORT else "."))
    can = "read and export" if wanted == "Sheet" and mime in (XLSX, "text/csv") else "export"
    return UserError(f"'{name}' is an uploaded {kind_name(mime)} file, not a Google {wanted}. gsuite can {can} it; "
                     f"to change it, open it in Google Drive and use File > Save as Google "
                     f"{'Sheets' if wanted == 'Sheet' else 'Docs'}.")


def sheet_tabs(fid: str) -> list[dict]:
    res = api.run(api.sheets_api().spreadsheets().get(
        spreadsheetId=fid, fields="sheets.properties(sheetId,title,hidden)"))
    return [s["properties"] for s in res.get("sheets", [])]


def unquote(name: str) -> str:
    name = name.strip()
    if len(name) > 1 and name[0] == name[-1] == "'":
        return name[1:-1].replace("''", "'")
    return name


def resolve_range(link: str, fid: str, rng: str | None, note: bool = False) -> str:
    """The range to send to Google, always naming its tab, so nothing lands on a tab by accident.

    "'Tab'!A1" is used as given. A tab name (quoted or not, even "Q1" or "Nov") means that whole
    tab. Bare cells ("A1:F20") go to the tab the link points at (#gid=), else the first visible tab.
    """
    if rng and "!" in rng:
        return rng
    tabs = sheet_tabs(fid)
    titles = [t["title"] for t in tabs]
    if rng and unquote(rng) in titles:
        return api.quote_tab(unquote(rng))
    if rng and not CELL_REF.fullmatch(rng.strip()):
        if rng.strip().startswith("'"):
            raise UserError(f"No tab {unquote(rng)!r}. Tabs: {', '.join(titles)}")
        return rng  # a named range; Google resolves it (or says it does not exist)
    visible = [t["title"] for t in tabs if not t.get("hidden")] or titles
    gid = re.search(r"[#?&]gid=(\d+)", link)
    if gid:
        tab = next((t["title"] for t in tabs if str(t.get("sheetId")) == gid.group(1)), None)
        if tab is None:
            raise UserError("The link points at a tab that no longer exists. Name the tab in the range, "
                            f"e.g. \"'{visible[0]}'!A1\". Tabs: {', '.join(titles)}")
    else:
        tab = visible[0]
        if note:
            print(f"(no tab named: using the first tab, {tab!r})", file=sys.stderr)
    return api.quote_tab(tab) + (f"!{rng.strip()}" if rng else "")


def print_rows(rows: list, show_all: bool) -> None:
    if not show_all and len(rows) > READ_LIMIT:
        write_csv(rows[:READ_LIMIT])
        print(f"(showing the first {READ_LIMIT} of {len(rows)} rows; give a range, or add --all)", file=sys.stderr)
    else:
        write_csv(rows)


def find(query: str, kind: str | None, limit: int) -> None:
    def literal(word: str) -> str:  # Drive query strings escape \ and '
        return word.replace("\\", "\\\\").replace("'", "\\'")

    words = " and ".join(f"name contains '{literal(w)}'" for w in query.split())
    q = " and ".join(filter(None, [words, "trashed = false", f"mimeType = '{MIME[kind]}'" if kind else ""]))
    res = api.run(api.drive().files().list(
        q=q, pageSize=limit, orderBy="modifiedTime desc", includeItemsFromAllDrives=True,
        supportsAllDrives=True, corpora="allDrives",
        fields="files(id,name,mimeType,modifiedTime,webViewLink,owners(emailAddress))"))
    files = res.get("files", [])
    for x in files:
        owner = (x.get("owners") or [{}])[0].get("emailAddress", "shared drive")
        print(f"{x['modifiedTime'][:10]}  {kind_name(x['mimeType']):<14} {x['name']}  ({owner})\n"
              f"            {x.get('webViewLink', x['id'])}")
    if not files:
        print("No files found that you can open.", file=sys.stderr)


def tabs(fid: str) -> None:
    m = meta(fid)
    if m["mimeType"] != MIME["sheet"]:
        raise wrong_type(m, "Sheet")
    info = api.run(api.sheets_api().spreadsheets().get(
        spreadsheetId=fid, fields="properties.title,sheets.properties(title,hidden,gridProperties)"))
    print(info["properties"]["title"])
    for s in info["sheets"]:
        p = s["properties"]
        g = p["gridProperties"]
        print(f"  {p['title']}  ({g.get('rowCount')} rows x {g.get('columnCount')} cols)" + ("  [hidden]" if p.get("hidden") else ""))


def read(link: str, fid: str, rng: str | None, show_all: bool, formulas: bool) -> None:
    m = meta(fid)
    if m["mimeType"] != MIME["sheet"]:
        return read_uploaded(fid, m, rng, show_all)
    res = api.run(api.sheets_api().spreadsheets().values().get(
        spreadsheetId=fid, range=resolve_range(link, fid, rng),
        valueRenderOption="FORMULA" if formulas else "FORMATTED_VALUE"))
    print_rows(res.get("values", []), show_all)


def read_uploaded(fid: str, m: dict, rng: str | None, show_all: bool) -> None:
    """An uploaded .xlsx or .csv in Drive: download it and print it as CSV (read-only, whole tab)."""
    if m["mimeType"] not in (XLSX, "text/csv"):
        raise wrong_type(m, "Sheet")
    from kit.sheet import rows_from_bytes

    data = api.run(api.drive().files().get_media(fileId=fid, supportsAllDrives=True))
    tab = rng.split("!")[0] if rng and "!" in rng else (rng if rng and not CELL_REF.fullmatch(rng.strip()) else None)
    ext = ".csv" if m["mimeType"] == "text/csv" else ".xlsx"
    rows, _ = rows_from_bytes(data, ext, f"'{m['name']}'", tab if ext == ".xlsx" else None)
    if ext == ".xlsx" and rng and CELL_REF.fullmatch(rng.split("!")[-1].strip()):
        print("(uploaded Excel file: printing the whole tab; cell ranges work on Google Sheets only)", file=sys.stderr)
    print_rows(rows, show_all)


def write(link: str, fid: str, rng: str, csv_path: str, append: bool, raw: bool) -> None:
    body = {"values": read_csv_arg(csv_path)}  # check the local file before touching Google
    m = meta(fid)
    if m["mimeType"] != MIME["sheet"]:
        raise wrong_type(m, "Sheet")
    target = resolve_range(link, fid, rng, note=True)
    vals = api.sheets_api().spreadsheets().values()
    how = "RAW" if raw else "USER_ENTERED"
    if append:
        res = api.run_once(vals.append(spreadsheetId=fid, range=target, valueInputOption=how,
                                       insertDataOption="INSERT_ROWS", body=body))
        print(f"appended {res['updates'].get('updatedRows', 0)} rows at {res['updates'].get('updatedRange')}")
    else:  # overwriting the same cells twice gives the same result, so this one may be retried
        res = api.run(vals.update(spreadsheetId=fid, range=target, valueInputOption=how, body=body))
        print(f"updated {res.get('updatedCells', 0)} cells in {res.get('updatedRange')}")


def add_tab(fid: str, title: str) -> None:
    m = meta(fid)
    if m["mimeType"] != MIME["sheet"]:
        raise wrong_type(m, "Sheet")
    api.run_once(api.sheets_api().spreadsheets().batchUpdate(
        spreadsheetId=fid, body={"requests": [{"addSheet": {"properties": {"title": title}}}]}))
    print(f"added tab {title!r}")


def create(kind: str, title: str) -> None:
    f = api.run_once(api.drive().files().create(body={"name": title, "mimeType": MIME[kind]},
                                                fields="id,webViewLink", supportsAllDrives=True))
    print(f.get("webViewLink") or f["id"])


def doc(fid: str) -> None:
    m = meta(fid)
    if m["mimeType"] != MIME["doc"]:
        raise wrong_type(m, "Doc")
    # Drive's Markdown export keeps tables, which a plain walk of the Docs body would drop.
    data = api.run(api.drive().files().export(fileId=fid, mimeType=EXPORT[".md"]))
    text = data.decode("utf-8") if isinstance(data, bytes) else data
    # Images arrive inline as base64; megabytes of it would flood an agent's context.
    text = re.sub(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+", "image-omitted", text)
    print(text, end="")


def append_doc(fid: str, text_path: str) -> None:
    text = read_text_arg(text_path)
    if not text:
        raise UserError("Nothing to add: the text is empty.")
    m = meta(fid)
    if m["mimeType"] != MIME["doc"]:
        raise wrong_type(m, "Doc")
    api.run_once(api.docs().documents().batchUpdate(documentId=fid, body={"requests": [
        {"insertText": {"endOfSegmentLocation": {}, "text": text}}]}))
    print(f"added {len(text)} characters to the end of the doc")


def export(link: str, fid: str, out: str) -> None:
    from googleapiclient.http import MediaIoBaseDownload

    ext = Path(out).suffix.lower()
    m = meta(fid)
    mime, kind = m["mimeType"], kind_name(m["mimeType"])
    if mime == MIME["sheet"] and ext == ".csv":
        # Drive's CSV export is always the first tab; read the tab the link points at instead.
        rows = api.run(api.sheets_api().spreadsheets().values().get(
            spreadsheetId=fid, range=resolve_range(link, fid, None))).get("values", [])
        buf = io.StringIO()
        csv.writer(buf, lineterminator="\r\n").writerows(rows)
        # UTF-8 with a BOM, so Excel on Windows shows ₹ and Hindi text correctly.
        print(f"wrote {atomic_download(Path(out), lambda fh: fh.write(buf.getvalue().encode('utf-8-sig')))}")
        return
    if mime.startswith(GOOGLE):
        allowed = CAN_EXPORT.get(mime)
        if not allowed:
            raise UserError(f"'{m['name']}' is a {kind}; gsuite cannot save it as a file.")
        if ext not in allowed:
            raise UserError(f"A {kind} can be saved as {', '.join(allowed)}; not as {ext or '(no extension)'}.")
        req = api.drive().files().export_media(fileId=fid, mimeType=EXPORT[ext])
    else:  # an uploaded file (xlsx, pdf, ...): downloaded as it is, so it keeps its own extension
        own = Path(m["name"]).suffix.lower() or next((e for e, t in EXPORT.items() if t == mime), "")
        if own and ext != own:
            raise UserError(f"'{m['name']}' is an uploaded {own} file; save it as {own} (uploads are not converted).")
        req = api.drive().files().get_media(fileId=fid, supportsAllDrives=True)

    def fill(fh) -> None:
        dl, done = MediaIoBaseDownload(fh, req), False
        while not done:
            _, done = dl.next_chunk(num_retries=api.RETRIES)

    print(f"wrote {atomic_download(Path(out), fill)}")
