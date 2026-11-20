# gsuite on Windows

For Windows 10 and 11, on ordinary (x64) and ARM laptops. Mac users: see [../macos](../macos/README.md).

## Install (one line, about two minutes)

1. Open **PowerShell**: press the Windows key, type `PowerShell`, press Enter.
2. Paste this line and press Enter:

   ```powershell
   powershell -ExecutionPolicy ByPass -c "irm https://github.com/kathanshah/workspace-cli/releases/latest/download/install.ps1 | iex"
   ```

3. Your browser opens. Choose your **@spurge.rentals** account, **tick every box** and click
   **Continue**. Then go back to the PowerShell window.
4. It checks everything and prints `All good.`
5. **Close PowerShell and Claude Code, then open Claude Code again.** New windows pick up the
   `gsuite` command; windows that were already open do not.

Nothing needs installing beforehand, and no administrator rights are needed: everything goes into
your own user folders. Running the same line again later is safe; it updates gsuite and keeps you
signed in.

## Where it lives on Windows

| What | Folder |
|---|---|
| The `gsuite`, `gpy` and `kit` commands | `%USERPROFILE%\.local\bin\` (added to your PATH) |
| The program | `%APPDATA%\uv\data\tools\workspace-cli\` |
| Its own Python 3.12 (shared with any other uv tools) | `%APPDATA%\uv\data\python\` |
| The installer's private uv | `%LOCALAPPDATA%\gsuite\uv\` |
| kit's document engines (pandoc, Typst) | `%LOCALAPPDATA%\gsuite\tools\` |
| **Your sign-in** (treat it like a password; never share it) | `%APPDATA%\gsuite\token.json` |
| Claude Code skills (gsuite, kit) and approval rules | `%USERPROFILE%\.claude\skills\gsuite\`, `%USERPROFILE%\.claude\skills\kit\`, `%USERPROFILE%\.claude\settings.json` |

## Update, check, remove

- **Update:** `gsuite update` (it opens a new window to finish, because Windows cannot replace a
  running program), or paste the install line again.
- **Check:** `gsuite doctor`. Send its output to Kathan if anything says `[!!]`.
- **Remove everything** (the program, your sign-in on this PC, the Claude Code skill and rules):

  ```powershell
  powershell -ExecutionPolicy ByPass -c "irm https://github.com/kathanshah/workspace-cli/releases/latest/download/uninstall.ps1 | iex"
  ```

## Problems seen on Windows

| You see | Do this |
|---|---|
| `gsuite : The term 'gsuite' is not recognized` | Close **every** PowerShell and Claude Code window and open a new one. Still there? Run `& "$env:USERPROFILE\.local\bin\gsuite.exe" doctor` in PowerShell and send the output. |
| The install line fails straight away with a download or TLS error | Windows Update is far behind. Update Windows, or ask Kathan. |
| `Local file ... cannot be written or read (open in Excel?)` | Close that file in Excel and try again. |
| `... is not UTF-8 text` | In Excel use **Save As > CSV UTF-8 (Comma delimited)**. |
| Google says the app is blocked, or sign-in timed out | You picked a personal account. Run `gsuite login` and choose your @spurge.rentals one. |
| `Some permissions were not ticked` | Run `gsuite login` and tick every box on Google's screen. |

In Claude Code on Windows, commands may run in Git Bash or PowerShell; gsuite and its approval
rules work in both. In PowerShell, do not pipe text into gsuite (`"..." | gsuite write ... -`):
Windows PowerShell turns ₹ and Hindi into `?`. Save a UTF-8 file and pass its path instead.

## Testing a Windows install (pilot)

Right after installing, paste this in PowerShell and send the whole output to Kathan. It only
checks; it changes nothing:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/kathanshah/workspace-cli/main/windows/test-install.ps1 | iex"
```

Windows 10 on an ARM laptop cannot run kit's Word/PDF converter (pandoc ships for x64 only, and
only Windows 11 runs x64 programs on ARM). Everything else works; `kit convert` reports the
problem. Windows 11 on ARM is fine.
