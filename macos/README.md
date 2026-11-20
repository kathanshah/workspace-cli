# gsuite on macOS

For Macs with Apple Silicon (M1 and later) or Intel. Windows users: see [../windows](../windows/README.md).

## Install (one line, about two minutes)

1. Open **Terminal**: press Cmd+Space, type `Terminal`, press Enter.
2. Paste this line and press Enter:

   ```sh
   curl -LsSf https://github.com/kathanshah/workspace-cli/releases/latest/download/install.sh | sh
   ```

3. Your browser opens. Choose your **@spurge.rentals** account, **tick every box** and click
   **Continue**. Then go back to Terminal.
4. It checks everything and prints `All good.`
5. **Open a new Terminal window and restart Claude Code.** New windows pick up the `gsuite`
   command; windows that were already open do not.

Nothing needs installing beforehand, and no password or admin rights are needed: everything goes
into your own home folder. Running the same line again later is safe; it updates gsuite and keeps
you signed in.

## Where it lives on a Mac

| What | Folder |
|---|---|
| The `gsuite`, `gpy` and `kit` commands | `~/.local/bin/` (added to your PATH) |
| The program | `~/.local/share/uv/tools/workspace-cli/` |
| Its own Python 3.12 (shared with any other uv tools) | `~/.local/share/uv/python/` |
| The installer's private uv | `~/.local/share/gsuite/uv/` |
| kit's document engines (pandoc, Typst) | `~/.local/share/gsuite/tools/` |
| **Your sign-in** (treat it like a password; never share it) | `~/.config/gsuite/token.json` (readable only by you) |
| Claude Code skills (gsuite, kit) and approval rules | `~/.claude/skills/gsuite/`, `~/.claude/skills/kit/`, `~/.claude/settings.json` |

## Update, check, remove

- **Update:** `gsuite update`, or paste the install line again.
- **Check:** `gsuite doctor`. Send its output to Kathan if anything says `[!!]`.
- **Remove everything** (the program, your sign-in on this Mac, the Claude Code skill and rules):

  ```sh
  curl -LsSf https://github.com/kathanshah/workspace-cli/releases/latest/download/uninstall.sh | sh
  ```

## Problems seen on a Mac

| You see | Do this |
|---|---|
| `zsh: command not found: gsuite` | Open a new Terminal window. Still there? Run `~/.local/bin/gsuite doctor` and send the output. |
| `zsh: event not found` when typing a range | Use single quotes: `gsuite read <link> 'Leads!A1:F20'`. |
| `Local file ... cannot be written or read` | Close that file in Excel or Numbers and try again. |
| `... is not UTF-8 text` | In Excel use **Save As > CSV UTF-8 (Comma delimited)**. |
| Google says the app is blocked, or sign-in timed out | You picked a personal account. Run `gsuite login` and choose your @spurge.rentals one. |
| `Some permissions were not ticked` | Run `gsuite login` and tick every box on Google's screen. |
