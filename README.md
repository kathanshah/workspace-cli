# gsuite

Read, write and create Google Sheets and Docs from the terminal, and let AI agents like
Claude Code do it for you. Built for the SPURGE Rentals team: each person signs in once with
their own `@spurge.rentals` Google account and stays signed in.

## Install (one line, about two minutes)

**Windows:** open **PowerShell** (Start menu, type "PowerShell") and paste:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://github.com/kathanshah/workspace-cli/releases/latest/download/install.ps1 | iex"
```

**Mac:** open **Terminal** and paste:

```sh
curl -LsSf https://github.com/kathanshah/workspace-cli/releases/latest/download/install.sh | sh
```

What happens:

1. It installs everything it needs. You do not need Python or anything else beforehand.
2. Your browser opens. Choose your **@spurge.rentals** account, **tick every box** and click
   **Continue**.
3. It checks everything and prints `All good.`
4. Close the window and open a new Claude Code session.

Running the same line again later is safe: it updates gsuite and keeps you signed in.

## Use it

In Claude Code, paste a Google Sheet or Doc link and say what you want:

> Read https://docs.google.com/spreadsheets/d/... and tell me which rentals end this month.
>
> Add these three rows to the Leads tab: ...
>
> Make a new sheet called "Laptop returns Nov" with these columns: ...

Claude reads without asking. Before it changes or creates anything, it shows you the change
and Claude Code asks for your approval.

You can also use it yourself:

```sh
gsuite read <sheet link> 'Leads!A1:F20'
gsuite find "debtors" --type sheet
gsuite create sheet "Laptop returns Nov"
gsuite --help
```

gsuite can open exactly what your account can open in the browser, nothing more. Your edits show
under your name in the file's version history. Its commands never delete or share files.

## If something goes wrong

Run this and send the output to Kathan:

```sh
gsuite doctor
```

| You see | Do this |
|---|---|
| `gsuite` is not recognised / command not found | Close and reopen the terminal or Claude Code |
| `Sign-in needed` | `gsuite login` |
| `Some permissions were not ticked` | `gsuite login`, and tick every box on Google's screen |
| `Not found: ... not shared with your account` | Ask the file's owner to share it with you |
| Google says the app is blocked, or sign-in timed out | You picked a personal account: `gsuite login` and pick your @spurge.rentals one |

To update: `gsuite update`. To remove from a computer: `gsuite logout`, then
`uv tool uninstall workspace-cli`. (That forgets the sign-in on that computer only.)

## For other AI agents

`gsuite guide` prints the commands and the rules agents must follow. To set up an agent other
than Claude Code, add this line to its instructions file: *"Before using Google Sheets or Docs,
run `gsuite guide` and follow it."*

## Maintainers

See [AGENTS.md](AGENTS.md) for how it is built, released and tested.
