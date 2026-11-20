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
  gsuite read  <sheet> [range] [--formulas] [--all]
                                              print cells as CSV (first 500 rows unless --all)
  gsuite write <sheet> <range> <file.csv|-> [--raw]
                                              overwrite cells, starting at range
  gsuite append <sheet> <range> <file.csv|-> [--raw]
                                              add rows after the table in range
  gsuite add-tab <sheet> "<title>"            add a tab
  gsuite create sheet|doc "<title>"           create a new file in your Drive; prints its link

Docs
  gsuite doc <doc>                            print a Doc as Markdown (tables included)
  gsuite append-doc <doc> <file.txt|->        add text at the end of a Doc

Files
  gsuite export <file> <out.xlsx|.csv|.pdf|.docx|.md|.txt>   save a local copy

<sheet> and <doc> are a docs.google.com link or a file id. A link that points at a tab (#gid=...)
selects that tab when the range names none. Quote ranges: "'Sales 2026'!A1:F50".
--raw stores values exactly as given (keeps +91 phone numbers, leading zeros and IDs as text).
Uploaded Excel/CSV files in Drive can be read and exported, not written.
"""
from __future__ import annotations

import argparse
import sys

from . import __version__
from .auth import DOMAIN, SignInNeeded
from .files import UserError, utf8_stdio
from .ops import EXPORT, MIME

# Exit codes an agent can act on (see guide.md). 2 is argparse's "wrong command or options".
EXIT_FAIL, EXIT_SIGNIN, EXIT_GOOGLE, EXIT_NETWORK, EXIT_UNSURE = 1, 3, 4, 5, 6
LOCAL_FILE_ERRORS = (FileNotFoundError, PermissionError, IsADirectoryError, NotADirectoryError, FileExistsError)
NETWORK = "Cannot reach Google right now. Check the internet connection and try again in a minute."


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gsuite", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version=f"gsuite {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="<command>")
    lg = sub.add_parser("login"); lg.add_argument("--account", help=f"email to preselect (must be @{DOMAIN})")
    wh = sub.add_parser("whoami"); wh.add_argument("--quiet", action="store_true", help="print nothing; exit 0 if signed in")
    for name in ("logout", "doctor", "guide", "update"):
        sub.add_parser(name)
    ia = sub.add_parser("install-agent"); ia.add_argument("agent", choices=["claude"])
    ia.add_argument("--remove", action="store_true", help="remove the skill and gsuite's permission rules")
    f = sub.add_parser("find"); f.add_argument("query"); f.add_argument("--type", choices=MIME)
    f.add_argument("--limit", type=int, default=20)
    t = sub.add_parser("tabs"); t.add_argument("id")
    r = sub.add_parser("read"); r.add_argument("id"); r.add_argument("range", nargs="?")
    r.add_argument("--formulas", action="store_true", help="show formulas instead of their results")
    r.add_argument("--all", action="store_true", help="print every row (default: first 500)")
    for name in ("write", "append"):
        w = sub.add_parser(name); w.add_argument("id"); w.add_argument("range"); w.add_argument("csv")
        w.add_argument("--raw", action="store_true", help="store values exactly as given, no formulas or number parsing")
    at = sub.add_parser("add-tab"); at.add_argument("id"); at.add_argument("title")
    c = sub.add_parser("create"); c.add_argument("kind", choices=MIME); c.add_argument("title")
    d = sub.add_parser("doc"); d.add_argument("id")
    ad = sub.add_parser("append-doc"); ad.add_argument("id"); ad.add_argument("text")
    e = sub.add_parser("export"); e.add_argument("id"); e.add_argument("out", help=f"one of {', '.join(EXPORT)}")
    return p


def run_command(a) -> int:
    from . import api, auth, ops

    if a.cmd == "login":
        print(f"Signed in as {auth.login(a.account)}")
    elif a.cmd == "logout":
        print("Signed out on this computer." if auth.logout() else "This computer was not signed in.")
    elif a.cmd == "whoami":
        user = api.run(api.drive().about().get(fields="user(emailAddress,displayName)"))["user"]
        if not a.quiet:
            print(f"{user['emailAddress']} - {user['displayName']}")
    elif a.cmd == "doctor":
        from .doctor import doctor
        return doctor()
    elif a.cmd == "guide":
        from .agents import guide_text
        print(guide_text())
    elif a.cmd == "install-agent":
        from .agents import install_claude, remove_claude
        return remove_claude() if a.remove else install_claude()
    elif a.cmd == "update":
        from .doctor import update
        return update()
    elif a.cmd == "find":
        ops.find(a.query, a.type, a.limit)
    elif a.cmd == "create":
        ops.create(a.kind, a.title)
    else:
        fid = api.file_id(a.id)
        if a.cmd == "tabs":
            ops.tabs(fid)
        elif a.cmd == "read":
            ops.read(a.id, fid, a.range, a.all, a.formulas)
        elif a.cmd in ("write", "append"):
            ops.write(a.id, fid, a.range, a.csv, a.cmd == "append", a.raw)
        elif a.cmd == "add-tab":
            ops.add_tab(fid, a.title)
        elif a.cmd == "doc":
            ops.doc(fid)
        elif a.cmd == "append-doc":
            ops.append_doc(fid, a.text)
        elif a.cmd == "export":
            ops.export(a.id, fid, a.out)
    return 0


def explain_http_error(err) -> str:
    status = getattr(err.resp, "status", 0)
    detail = getattr(err, "reason", "") or str(err)
    if status == 404:
        return "Not found: the link is wrong, or the file is not shared with your account."
    if "not supported for this document" in detail:
        return "This is an uploaded Excel or Office file, not a Google Sheet or Doc. gsuite can read and export it only."
    if status == 403 and ("has not been used" in detail or "is disabled" in detail):
        return f"A Google API is switched off for this app. Tell the gsuite owner: {detail}"
    if status == 403:
        return f"Google refused: your account cannot do this on this file (view-only?). {detail}"
    if status == 400:
        return f"Google rejected the request (check the range or the tab name): {detail}"
    if status == 429:
        return "Google's rate limit was still reached after several retries. Wait a minute and try again."
    if status >= 500:
        return f"Google had a problem ({status}). Try again in a minute."
    return f"Google error {status}: {detail}"


def api_maybe_applied():
    from .api import MaybeApplied
    return MaybeApplied


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
    except api_maybe_applied() as e:
        err(f"Not sure the change went through: {e}. Google may or may not have applied it. "
            "Check the file before trying again, so nothing is added twice.")
        code = EXIT_UNSURE
    except LOCAL_FILE_ERRORS as e:
        name = e.filename2 or e.filename  # os.replace(tmp, out): the file the person named is filename2
        if not name:  # e.g. a firewall-blocked connection on Windows: not a file problem
            err(f"{NETWORK} ({e})")
            code = EXIT_NETWORK
        else:
            reason = {PermissionError: "cannot be written or read (open in Excel? close it and retry)",
                      FileNotFoundError: "does not exist", FileExistsError: "already exists"}.get(type(e), "is not usable")
            err(f"Local file {name} {reason}.")
            code = EXIT_FAIL
    except KeyboardInterrupt:
        code = 130
    except Exception as e:
        from google.auth.exceptions import GoogleAuthError
        from googleapiclient.errors import HttpError

        if isinstance(e, HttpError):
            err(explain_http_error(e))
            status = getattr(e.resp, "status", 0)
            code = EXIT_NETWORK if status >= 500 or status == 429 else EXIT_GOOGLE
        elif isinstance(e, (OSError, GoogleAuthError)) or type(e).__name__ in ("ServerNotFoundError", "TimeoutError"):
            err(f"{NETWORK} ({e})")
            code = EXIT_NETWORK
        else:
            raise
    sys.exit(code)
