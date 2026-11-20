# gsuite guide

`gsuite` reads and writes Google Sheets and Docs as the person signed in on this computer
(`gsuite whoami`). It can open exactly what that person can open in their browser, nothing more.
Edits appear under their name in the file's version history.

## Rules for AI agents (read before the first command)

1. **Open only what the person gave you.** Work on the links or file names they shared or named.
   Do not search, browse or summarise their Drive on your own initiative. `gsuite find` is for
   locating a file they named.
2. **Show before you write.** `write`, `append`, `append-doc`, `add-tab` and `create` change live
   files that colleagues use, and land immediately. Before running one, show the person the exact
   cells or text and the file it goes to, and wait for a clear yes. Read the target range first,
   so they see what will be overwritten. Never write a large range or a whole tab blind.
3. **No ID documents.** If a file holds Aadhaar, PAN, KYC scans, cheques, bank details or similar,
   stop and ask before reading further. Do not copy such data anywhere.
4. **Keep data where it is.** Do not paste sheet contents into other files, messages or tools
   unless the person asks for exactly that.
5. **Sign-in problems are the person's to fix.** On exit code 3 ("Sign-in needed"), tell them a
   browser window is about to open, then run `gsuite login` with a command timeout of at least
   5 minutes (it waits for their approval). Never try to work around the login, read token
   files, or use another account.

## Commands

| Command | What it does |
|---|---|
| `gsuite read <sheet> ["'Tab'!A1:F50"]` | Cells as CSV (first tab if no range) |
| `gsuite tabs <sheet>` | Tab names and sizes |
| `gsuite find "<words>" [--type sheet\|doc]` | Find files by name; prints links |
| `gsuite doc <doc>` | A Doc as Markdown, tables included |
| `gsuite write <sheet> "'Tab'!A2" rows.csv` | Overwrite cells from a CSV file (`-` = stdin) |
| `gsuite append <sheet> "'Tab'!A:F" rows.csv` | Add rows after the existing table |
| `gsuite add-tab <sheet> "<title>"` | Add a tab |
| `gsuite create sheet\|doc "<title>"` | New file in the person's Drive; prints its link |
| `gsuite append-doc <doc> text.txt` | Add text at the end of a Doc |
| `gsuite export <file> out.xlsx` | Save a local copy (.xlsx .csv .pdf .docx .md .txt); asks first, never overwrites a file on failure |
| `gsuite whoami` / `doctor` / `login` | Who is signed in / check setup / sign in |

`<sheet>` and `<doc>` are a full docs.google.com link or a file id.

- **Ranges:** always quote them, and quote tab names that contain spaces inside the range:
  `"'Sales 2026'!A1:F50"`. A whole tab is `"'Sales 2026'"`. Without a tab name, a link that
  ends in `#gid=...` uses that tab, and any other link uses the first tab: name the tab for writes.
- **CSV in:** UTF-8; the first row is written like any other row (include headers only if you
  mean to). Values are entered as if typed, so `=SUM(A1:A5)` becomes a formula and `5000` a number.
  Write amounts as plain numbers: `₹5,000` stays text, and formulas on it show `#VALUE!`.
  Leave currency to the column's number format.
- **Large or complex work:** write a short Python script and run it with `gpy script.py`.
  `from gworkspace import sheet` gives a signed-in gspread spreadsheet;
  `from gspread_dataframe import get_as_dataframe, set_with_dataframe` moves data to and from pandas.
  Put scripts in a temporary folder, not in the person's project.

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | Done | |
| 1 | Bad input or local file problem (missing, open in Excel, not UTF-8, empty CSV) | Read the message; fix the command or file |
| 3 | Sign-in needed | Run `gsuite login`; the person approves in the browser |
| 4 | Google refused (not shared, view-only, wrong range, API issue) | Read the message; ask the person for access or a correct link |
| 5 | No internet, or a passing Google problem | Retry in a minute |

If something else looks wrong, run `gsuite doctor` and show the person its output.
