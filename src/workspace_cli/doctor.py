"""`gsuite doctor` checks the whole chain and prints a plain fix for each problem; `gsuite update`."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess

from . import INSTALL_PS1, INSTALL_SH, REPO, __version__

OK, BAD, INFO = "[ok]", "[!!]", "[--]"


def latest_version() -> str | None:
    import requests

    try:
        r = requests.get(f"https://api.github.com/repos/{REPO}/releases/latest", timeout=10)
        return r.json()["tag_name"].lstrip("v") if r.ok else None
    except Exception:
        return None


def doctor() -> int:
    from googleapiclient.errors import HttpError

    from . import api, auth
    from .agents import claude_dir, claude_rules_ok

    problems = 0

    def line(mark: str, text: str, fix: str = "") -> None:
        nonlocal problems
        problems += mark == BAD
        print(f"{mark} {text}" + (f"\n     fix: {fix}" if fix else ""))

    line(INFO, f"gsuite {__version__}, Python {platform.python_version()}, {platform.system()} {platform.machine()}")
    newest = latest_version()
    if newest and newest != __version__:
        line(BAD, f"a newer gsuite is available ({newest})", "gsuite update")
    elif newest:
        line(OK, "gsuite is up to date")
    else:
        line(INFO, "could not check for updates right now (skipped)")

    if shutil.which("gsuite"):
        line(OK, "gsuite is on PATH")
    else:
        line(BAD, "gsuite is not on PATH in this terminal",
             "close and reopen the terminal (or Claude Code); if it persists run: uv tool update-shell")

    signed_in = False
    try:
        auth.creds()
        signed_in = True
    except auth.SignInNeeded as e:
        line(BAD, f"not signed in: {e}", "gsuite login")
    except Exception as e:
        line(BAD, f"cannot refresh the sign-in: {e}", "check the internet connection, then gsuite login")

    if signed_in:
        try:
            user = api.run(api.drive().about().get(fields="user(emailAddress)"))["user"]["emailAddress"]
            if user.lower().endswith("@" + auth.DOMAIN):
                line(OK, f"signed in as {user}")
            else:
                line(BAD, f"signed in as {user}, not an @{auth.DOMAIN} account", "gsuite logout, then gsuite login")
        except Exception as e:
            line(BAD, f"Google Drive is not reachable: {e}", "check the internet connection")
        # A made-up file id must come back 404 (API on, login accepted); anything else is a problem.
        probes = {"Sheets": lambda: api.sheets_api().spreadsheets().get(spreadsheetId="gsuite-doctor-probe-0000000000"),
                  "Docs": lambda: api.docs().documents().get(documentId="gsuite-doctor-probe-0000000000")}
        for name, probe in probes.items():
            try:
                probe().execute()
                line(OK, f"{name} API reachable")
            except HttpError as e:
                if e.resp.status in (400, 404):
                    line(OK, f"{name} API reachable")
                else:
                    line(BAD, f"{name} API problem: {e.resp.status} {getattr(e, 'reason', '')}",
                         "send this output to the gsuite owner")
            except Exception as e:
                line(BAD, f"{name} API not reachable: {e}", "check the internet connection")

    skill = claude_dir() / "skills" / "gsuite" / "SKILL.md"
    if skill.exists() and claude_rules_ok():
        line(OK, "Claude Code skill and approval rules installed")
    elif skill.exists():
        line(BAD, "Claude Code approval rules for gsuite are missing", "gsuite install-agent claude")
    elif claude_dir().exists():
        line(BAD, "Claude Code is set up here but the gsuite skill is missing", "gsuite install-agent claude")
    else:
        line(INFO, "Claude Code not found on this computer (skipped)")

    print("\nAll good." if not problems else f"\n{problems} problem(s) found. Run each fix above, then gsuite doctor again.")
    return 1 if problems else 0


def update() -> int:
    newest = latest_version()
    if newest == __version__:
        print(f"gsuite {__version__} is already the latest.")
        return 0
    if os.name == "nt":
        # A running gsuite.exe cannot replace itself on Windows, so the installer runs in a new window.
        cmd = (f"Start-Sleep 2; try {{ irm {INSTALL_PS1} | iex }} catch {{ Write-Host $_ -ForegroundColor Red }} "
               "finally { Read-Host 'Press Enter to close' }")
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd],
                         creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
        print("Updating gsuite in a new window. Your sign-in is kept.")
        return 0
    return subprocess.call(["sh", "-c", f"curl -LsSf {INSTALL_SH} | sh"])
