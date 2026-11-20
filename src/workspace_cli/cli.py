"""gsuite: Google Sheets and Docs from the terminal. Run `gsuite guide` for the full guide.

Setup and help
  gsuite login                     sign in once in the browser (your own @spurge.rentals account)
  gsuite whoami                    show who this computer is signed in as
  gsuite doctor                    check everything and say how to fix what is wrong
  gsuite guide                     how to use gsuite, and the rules for AI agents
  gsuite update                    install the latest version
  gsuite logout                    forget the sign-in on this computer

Sheets
  gsuite find  "<words>" [--type sheet|doc]   find files by name
  gsuite tabs  <sheet>                        list tabs with sizes
  gsuite read  <sheet> [range]                print cells as CSV (default: first tab)
  gsuite write <sheet> <range> <file.csv|->   overwrite cells, starting at range
  gsuite append <sheet> <range> <file.csv|->  add rows after the table in range
  gsuite add-tab <sheet> "<title>"            add a tab
  gsuite create sheet|doc "<title>"           create a new file in your Drive; prints its link

Docs
  gsuite doc <doc>                            print a Doc as Markdown (tables included)
  gsuite append-doc <doc> <file.txt|->        add text at the end of a Doc

Files
  gsuite export <sheet|doc> <out.xlsx|.csv|.pdf|.docx|.md|.txt>   save a local copy

<sheet> and <doc> are a docs.google.com link or a file id. A link that points at a tab (#gid=...)
selects that tab when the range names none. Quote ranges: "'Sales 2026'!A1:F50".
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import tempfile
from pathlib import Path

from . import __version__
from .auth import DOMAIN, SignInNeeded

MIME = {"sheet": "application/vnd.google-apps.spreadsheet", "doc": "application/vnd.google-apps.document"}
EXPORT = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".md": "text/markdown",
    ".txt": "text/plain",
}

# Exit codes an agent can act on.
EXIT_FAIL, EXIT_SIGNIN, EXIT_GOOGLE, EXIT_NETWORK = 1, 3, 4, 5
LOCAL_FILE_ERRORS = (FileNotFoundError, PermissionError, IsADirectoryError, NotADirectoryError, FileExistsError)


class UserError(Exception):
    """Bad input the person or agent can fix; printed as is, exit 1."""


def utf8_stdio() -> None:
    # Windows consoles default to a legacy code page: ₹ or a Hindi name would crash the output.
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
    return list(csv.reader(io.StringIO(read_text_arg(path), newline="")))


def write_csv(rows) -> None:
    csv.writer(sys.stdout, lineterminator="\n").writerows(rows)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gsuite", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"gsuite {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")
    lg = sub.add_parser("login"); lg.add_argument("--account", help=f"email to preselect (must be @{DOMAIN})")
    wh = sub.add_parser("whoami"); wh.add_argument("--quiet", action="store_true", help="print nothing; exit 0 if signed in, 3 if not")
    for name in ("logout", "doctor", "guide", "update"):
        sub.add_parser(name)
    ia = sub.add_parser("install-agent"); ia.add_argument("agent", choices=["claude"])
    f = sub.add_parser("find"); f.add_argument("query"); f.add_argument("--type", choices=MIME); f.add_argument("--limit", type=int, default=20)
    t = sub.add_parser("tabs"); t.add_argument("id")
    r = sub.add_parser("read"); r.add_argument("id"); r.add_argument("range", nargs="?")
    for name in ("write", "append"):
        w = sub.add_parser(name); w.add_argument("id"); w.add_argument("range"); w.add_argument("csv")
    at = sub.add_parser("add-tab"); at.add_argument("id"); at.add_argument("title")
    c = sub.add_parser("create"); c.add_argument("kind", choices=MIME); c.add_argument("title")
    d = sub.add_parser("doc"); d.add_argument("id")
    ad = sub.add_parser("append-doc"); ad.add_argument("id"); ad.add_argument("text")
    e = sub.add_parser("export"); e.add_argument("id"); e.add_argument("out")
    return p


def run_command(a) -> int:
    from . import api, auth

    if a.cmd == "login":
        print(f"Signed in as {auth.login(a.account)}")
        return 0
    if a.cmd == "logout":
        print("Signed out on this computer." if auth.logout() else "This computer was not signed in.")
        return 0
    if a.cmd == "whoami":
        user = api.run(api.drive().about().get(fields="user(emailAddress,displayName)"))["user"]
        if not a.quiet:
            print(f"{user['emailAddress']} - {user['displayName']}")
        return 0
    if a.cmd == "doctor":
        from .doctor import doctor
        return doctor()
    if a.cmd == "guide":
        from .agents import guide_text
        print(guide_text())
        return 0
    if a.cmd == "install-agent":
        from .agents import install_claude
        return install_claude()
    if a.cmd == "update":
        from .doctor import update
        return update()

    fid = api.file_id(a.id) if hasattr(a, "id") else None

    def tab_range(rng: str | None) -> str | None:
        """Apply the tab a pasted link points at (#gid=N) when the range names no tab."""
        m = re.search(r"[#?&]gid=(\d+)", a.id)
        # Only a bare cell reference (A1, A1:F20, A:F, 2:5) lacks a tab; "'Leads'" already names one.
        if not m or (rng and not re.fullmatch(r"\$?[A-Za-z]{0,3}\$?\d*(:\$?[A-Za-z]{0,3}\$?\d*)?", rng.strip())):
            return rng
        meta = api.run(api.sheets_api().spreadsheets().get(spreadsheetId=fid, fields="sheets.properties(sheetId,title)"))
        title = next((s["properties"]["title"] for s in meta["sheets"] if str(s["properties"]["sheetId"]) == m.group(1)), None)
        if title is None:
            return rng
        return api.quote_tab(title) + (f"!{rng}" if rng else "")
    if a.cmd == "find":
        words = " and ".join(f"name contains '{w.replace(chr(39), '')}'" for w in a.query.split())
        q = " and ".join(filter(None, [words, "trashed = false", f"mimeType = '{MIME[a.type]}'" if a.type else ""]))
        res = api.run(api.drive().files().list(
            q=q, pageSize=a.limit, orderBy="modifiedTime desc", includeItemsFromAllDrives=True,
            supportsAllDrives=True, corpora="allDrives",
            fields="files(id,name,mimeType,modifiedTime,webViewLink,owners(emailAddress))"))
        files = res.get("files", [])
        for x in files:
            kind = x["mimeType"].rsplit(".", 1)[-1]
            owner = (x.get("owners") or [{}])[0].get("emailAddress", "shared drive")
            print(f"{x['modifiedTime'][:10]}  {kind:<12} {x['name']}  ({owner})\n            {x.get('webViewLink', x['id'])}")
        if not files:
            print("No files found that you can open.", file=sys.stderr)
    elif a.cmd == "tabs":
        meta = api.run(api.sheets_api().spreadsheets().get(
            spreadsheetId=fid, fields="properties.title,sheets.properties(title,gridProperties)"))
        print(meta["properties"]["title"])
        for s in meta["sheets"]:
            g = s["properties"]["gridProperties"]
            print(f"  {s['properties']['title']}  ({g.get('rowCount')} rows x {g.get('columnCount')} cols)")
    elif a.cmd == "read":
        sheets = api.sheets_api().spreadsheets()
        rng = tab_range(a.range) or api.quote_tab(api.run(sheets.get(
            spreadsheetId=fid, fields="sheets.properties.title"))["sheets"][0]["properties"]["title"])
        write_csv(api.run(sheets.values().get(spreadsheetId=fid, range=rng)).get("values", []))
    elif a.cmd in ("write", "append"):
        body = {"values": read_csv_arg(a.csv)}  # check the local file before touching Google
        if not body["values"]:
            print("Nothing to write: the CSV is empty.", file=sys.stderr)
            return EXIT_FAIL
        a.range = tab_range(a.range)
        vals = api.sheets_api().spreadsheets().values()
        if a.cmd == "write":
            res = api.run(vals.update(spreadsheetId=fid, range=a.range, valueInputOption="USER_ENTERED", body=body))
            print(f"updated {res.get('updatedCells', 0)} cells in {res.get('updatedRange')}")
        else:
            res = api.run(vals.append(spreadsheetId=fid, range=a.range, valueInputOption="USER_ENTERED",
                                      insertDataOption="INSERT_ROWS", body=body))
            print(f"appended {res['updates'].get('updatedRows', 0)} rows at {res['updates'].get('updatedRange')}")
    elif a.cmd == "add-tab":
        api.run(api.sheets_api().spreadsheets().batchUpdate(
            spreadsheetId=fid, body={"requests": [{"addSheet": {"properties": {"title": a.title}}}]}))
        print(f"added tab {a.title!r}")
    elif a.cmd == "create":
        f = api.run(api.drive().files().create(body={"name": a.title, "mimeType": MIME[a.kind]},
                                               fields="id,webViewLink", supportsAllDrives=True))
        print(f.get("webViewLink") or f["id"])
    elif a.cmd == "doc":
        # Drive's Markdown export keeps tables, which a plain walk of the Docs body would drop.
        data = api.run(api.drive().files().export(fileId=fid, mimeType=EXPORT[".md"]))
        text = data.decode("utf-8") if isinstance(data, bytes) else data
        # Images arrive inline as base64; megabytes of it would flood an agent's context.
        text = re.sub(r"data:image/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=\s]+", "image-omitted", text)
        print(text, end="")
    elif a.cmd == "append-doc":
        text = read_text_arg(a.text)
        if not text:
            print("Nothing to add: the text is empty.", file=sys.stderr)
            return EXIT_FAIL
        api.run(api.docs().documents().batchUpdate(documentId=fid, body={"requests": [
            {"insertText": {"endOfSegmentLocation": {}, "text": text}}]}))
        print(f"added {len(text)} characters to the end of the doc")
    elif a.cmd == "export":
        from googleapiclient.http import MediaIoBaseDownload

        ext = Path(a.out).suffix.lower()
        if ext not in EXPORT:
            print(f"Unsupported extension {ext}; use one of {', '.join(EXPORT)}", file=sys.stderr)
            return EXIT_FAIL
        out = Path(a.out).resolve()
        req = api.drive().files().export_media(fileId=fid, mimeType=EXPORT[ext])
        fd, tmp = tempfile.mkstemp(prefix=".gsuite-", suffix=ext, dir=out.parent)
        try:
            with os.fdopen(fd, "wb") as fh:
                dl, done = MediaIoBaseDownload(fh, req), False
                while not done:
                    _, done = dl.next_chunk(num_retries=api.RETRIES)
            os.replace(tmp, out)  # only a complete download replaces an existing file
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        print(f"wrote {out}")
    return 0


def explain_http_error(err) -> str:
    status = getattr(err.resp, "status", 0)
    detail = getattr(err, "reason", "") or str(err)
    if status == 404:
        return "Not found: the link is wrong, or the file is not shared with your account."
    if status == 403 and ("has not been used" in detail or "is disabled" in detail):
        return f"A Google API is switched off for this app. Tell the gsuite owner: {detail}"
    if status == 403:
        return f"Google refused: your account cannot do this on this file (view-only?). {detail}"
    if status == 400:
        return f"Google rejected the request (check the range or the tab name): {detail}"
    if status == 429:
        return "Google rate limit reached even after retries. Wait a minute and try again."
    return f"Google error {status}: {detail}"


def main(argv: list[str] | None = None) -> None:
    utf8_stdio()
    a = parser().parse_args(argv)
    quiet = getattr(a, "quiet", False)

    def err(text: str) -> None:
        if not quiet:
            print(text, file=sys.stderr)

    try:
        code = run_command(a)
    except SignInNeeded as e:
        err(f"Sign-in needed: {e}. Run: gsuite login")
        code = EXIT_SIGNIN
    except UserError as e:
        err(str(e))
        code = EXIT_FAIL
    except LOCAL_FILE_ERRORS as e:
        if not e.filename:  # e.g. a firewall-blocked connection on Windows: not a file problem
            err(f"Cannot reach Google right now. Check the internet connection and try again in a minute. ({e})")
            code = EXIT_NETWORK
        else:
            reason = {PermissionError: "cannot be written or read (open in Excel? close it and retry)",
                      FileNotFoundError: "does not exist", FileExistsError: "already exists"}.get(type(e), "is not usable")
            err(f"Local file {e.filename} {reason}.")
            code = EXIT_FAIL
    except KeyboardInterrupt:
        code = 130
    except Exception as e:
        from google.auth.exceptions import GoogleAuthError
        from googleapiclient.errors import HttpError

        if isinstance(e, HttpError):
            err(explain_http_error(e))
            code = EXIT_GOOGLE
        elif isinstance(e, (OSError, GoogleAuthError)) or type(e).__name__ == "ServerNotFoundError":
            err(f"Cannot reach Google right now. Check the internet connection and try again in a minute. ({e})")
            code = EXIT_NETWORK
        else:
            raise
    sys.exit(code)
