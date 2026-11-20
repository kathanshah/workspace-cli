"""Agent setup. `gsuite guide` is the single source of rules; each agent's setup only points at it.

Claude Code: a user skill that tells Claude to read the guide, plus permission rules so reading
commands run without a prompt and the plain form of every changing command (`gsuite write ...`)
always asks, in every permission mode. Other forms (a full path, `sh -c`) match no allow rule, so
they prompt in normal modes; nothing here can stop them in bypass mode. Rules are added for both
the Bash and the PowerShell tool, because Claude Code on Windows can run either.
"""
from __future__ import annotations

import json
import os
import shutil
from importlib import resources
from pathlib import Path

from .auth import DOMAIN

# `export` writes a local file of the agent's choosing, so it asks like the commands that change Google files.
READ_CMDS = ["read", "tabs", "find", "doc", "whoami", "doctor", "guide", "--version"]
WRITE_CMDS = ["write", "append", "append-doc", "add-tab", "create", "export", "login", "logout", "update"]

SKILL = """---
name: gsuite
description: Read, write and create Google Sheets and Google Docs with the gsuite command, as the signed-in @{domain} user. Use whenever the user shares a docs.google.com link, names a Google Sheet or Doc, or asks to read, update, create or export one.
---

# Google Sheets and Docs (gsuite)

Before the first gsuite command in a conversation, run `gsuite guide` and follow its rules.
They are short: open only the files the user gave you, show every change and get a clear yes
before writing, and stop if a file holds ID documents (Aadhaar, PAN, KYC, cheques).

If a command exits with code 3, run `gsuite login` and ask the user to approve in the browser.
If anything else looks broken, run `gsuite doctor` and show the user its output.
"""


def guide_text() -> str:
    return resources.files("workspace_cli").joinpath("guide.md").read_text(encoding="utf-8")


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def rules() -> tuple[list[str], list[str]]:
    allow, ask = [], []
    for tool in ("Bash", "PowerShell"):
        allow += [f"{tool}(gsuite {c} *)" for c in READ_CMDS]
        ask += [f"{tool}(gsuite {c} *)" for c in WRITE_CMDS] + [f"{tool}(gpy *)"]
    return allow, ask


class SettingsError(Exception):
    pass


def merge_settings(path: Path) -> str:
    """Add gsuite's rules to a Claude Code settings.json, keeping everything already there."""
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig") or "{}")
            if not isinstance(data, dict):
                raise ValueError
        except ValueError:
            raise SettingsError(f"left {path} unchanged: it is not valid JSON. Fix it, then run "
                                "`gsuite install-agent claude` again.")
        backup = path.with_name(path.name + ".before-gsuite")
        if not backup.exists():
            shutil.copy2(path, backup)
    else:
        data = {}
    perms = data.setdefault("permissions", {})
    allow, ask = rules()
    added = 0
    # Drop gsuite auto-approvals an older version added that this version no longer gives.
    stale = [r for r in perms.get("allow", []) if r.startswith(("Bash(gsuite ", "PowerShell(gsuite ",
                                                                  "Bash(gpy", "PowerShell(gpy")) and r not in allow]
    for rule in stale:
        perms["allow"].remove(rule)
        added += 1
    for key, wanted in (("allow", allow), ("ask", ask)):
        current = perms.setdefault(key, [])
        for rule in wanted:
            if rule not in current:
                current.append(rule)
                added += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".gsuite.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return f"{added} permission rules updated in {path}" if added else f"permission rules already in {path}"


def install_claude() -> int:
    base = claude_dir()
    skill = base / "skills" / "gsuite" / "SKILL.md"
    skill.parent.mkdir(parents=True, exist_ok=True)
    skill.write_text(SKILL.format(domain=DOMAIN), encoding="utf-8")
    print(f"Claude Code: skill written to {skill}")
    try:
        print(f"Claude Code: {merge_settings(base / 'settings.json')}")
    except SettingsError as e:
        print(f"Claude Code: PROBLEM: {e}")
        return 1
    return 0


def claude_rules_ok() -> bool:
    try:
        data = json.loads((claude_dir() / "settings.json").read_text(encoding="utf-8-sig"))
        return "Bash(gsuite write *)" in data["permissions"]["ask"]
    except Exception:
        return False
