# gsuite

Read, write and create Google Sheets and Docs from the terminal, and let AI agents like
Claude Code do it for you. Built for the SPURGE Rentals team: each person signs in once with
their own `@spurge.rentals` Google account and stays signed in.

## Install: pick your computer

| Computer | Guide | One line to paste |
|---|---|---|
| **Windows** 10/11 (x64 or ARM) | [windows/README.md](windows/README.md) | in PowerShell: `powershell -ExecutionPolicy ByPass -c "irm https://github.com/kathanshah/workspace-cli/releases/latest/download/install.ps1 \| iex"` |
| **Mac** (Apple Silicon or Intel) | [macos/README.md](macos/README.md) | in Terminal: `curl -LsSf https://github.com/kathanshah/workspace-cli/releases/latest/download/install.sh \| sh` |

When the browser opens, choose your **@spurge.rentals** account, **tick every box** and click
**Continue**. Then open a new Claude Code session. Each guide covers where things are stored,
updating, removing, and the problems seen on that system.

## Use it

In Claude Code, paste a Google Sheet or Doc link and say what you want:

> Read https://docs.google.com/spreadsheets/d/... and tell me which rentals end this month.
>
> Add these three rows to the Leads tab: ...
>
> Make a new sheet called "Laptop returns Nov" with these columns: ...

Claude reads without asking. Before it changes, creates or saves anything, it shows you the change
and Claude Code asks for your approval.

You can also use it yourself (`gsuite --help` lists everything):

```sh
gsuite read <sheet link> 'Leads!A1:F20'
gsuite find "debtors" --type sheet
gsuite create sheet "Laptop returns Nov"
```

gsuite can open exactly what your account can open in the browser, nothing more. Your edits show
under your name in the file's version history. Its commands never delete or share files.
Uploaded Excel or CSV files in Drive can be read and exported, but only Google Sheets and Docs
can be changed.

If anything goes wrong, run `gsuite doctor` and send the output to Kathan.

## For other AI agents

`gsuite guide` prints the commands and the rules agents must follow. To set up an agent other
than Claude Code, add this line to its instructions file: *"Before using Google Sheets or Docs,
run `gsuite guide` and follow it."*

## Maintainers

See [AGENTS.md](AGENTS.md) for the layout, the Windows/macOS split, testing and releasing.
