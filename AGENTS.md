# Working on gsuite

Guide for anyone (person or agent) changing this repository. Users read [README.md](README.md);
agents that *use* gsuite read `gsuite guide` (`src/workspace_cli/guide.md`).

## Layout

Windows and macOS are kept apart in two places: the installers, test scripts and user guides
(`windows/`, `macos/`), and the code that differs by OS (`src/workspace_cli/platforms/`).
Everything else is shared and never checks the OS.

| Path | What |
|---|---|
| `windows/` | `install.ps1`, `uninstall.ps1`, `test-install.ps1` (pilot check), `README.md` (Windows user guide) |
| `macos/` | `install.sh`, `uninstall.sh`, `test-install.sh` (local end-to-end test), `README.md` (macOS user guide; also works on Linux) |
| `scripts/release.sh` | Local release: checks, tests, build, macOS install test, tag, GitHub release |
| `src/workspace_cli/platforms/windows.py`, `macos.py` | Per-OS paths, file permissions, PATH fix hint, `update` |
| `src/workspace_cli/cli.py` | Command line, exit codes, friendly Google errors |
| `src/workspace_cli/ops.py` | The Google operations behind each command |
| `src/workspace_cli/files.py` | Local files: CSV/text decoding (UTF-8, Excel BOM, PowerShell UTF-16), safe writes |
| `src/workspace_cli/auth.py` | Sign-in, token storage, domain check |
| `src/workspace_cli/api.py` | Signed-in API clients with retries |
| `src/workspace_cli/agents.py` | `install-agent claude [--remove]`: skill + permission rules |
| `src/workspace_cli/doctor.py` | `doctor` and `update` |
| `src/workspace_cli/guide.md` | The one source of agent rules (`gsuite guide`) |
| `src/workspace_cli/client.json` | The OAuth Desktop client (see below); git-ignored, added at build time |
| `src/gworkspace/` | Import shim for `gpy` scripts: `from gworkspace import sheet` |

## How an install works (both OSes)

1. The installer puts its **own pinned uv** in a private folder (`~/.local/share/gsuite/uv/`,
   `%LOCALAPPDATA%\gsuite\uv\`) with `UV_UNMANAGED_INSTALL`: no PATH edits and no update
   record, so any other uv on the machine is neither used nor changed. On Windows, uv's own
   installer runs in a child PowerShell (it calls `exit` on failure, which would close the window).
2. That uv installs the release wheel as a uv tool on **uv-managed Python 3.12**
   (`UV_PYTHON_PREFERENCE=only-managed`), with `--no-build` and `--exclude-newer`, into the fixed
   bin folder `~/.local/bin` (`UV_TOOL_BIN_DIR`); `uv tool update-shell` puts it on the user PATH
   for new windows, and the installer adds it to its own PATH so the closing `doctor` finds it.
3. `gsuite install-agent claude` writes the skill and rules; then sign-in (skipped if signed in);
   then `gsuite doctor`.

## The sign-in client

`client.json` is the Desktop OAuth client `team-gsuite` in Google Cloud project
`spurge-rentals-seo`. The app is **Internal** to the spurge.rentals Workspace (only its accounts
can sign in, and logins do not expire after 7 days) and is marked **Trusted** under Admin console,
Security, API controls. A Desktop client's secret cannot be kept secret, since every installed
copy carries it; access comes from each person's own login, not from this file.

It is kept out of git (secret scanners flag it, and GitHub push protection blocks it). The release
is built on the owner's Mac from the local, git-ignored `src/workspace_cli/client.json` (original
download: `~/.config/google-access-team/`), so every release wheel carries it.

To replace it (for example if Google disables it): create a new Desktop client or add a secret to
`team-gsuite` in the console, put the JSON at `src/workspace_cli/client.json`, release, and
have everyone run `gsuite update` or the install line. Existing logins made with the old client then need `gsuite login`.

Scopes are in `auth.SCOPES`. Adding one makes every saved login report "needs one more
permission" until the person runs `gsuite login`, so add scopes rarely and say so in the release.

## Rules that keep it stable

- Dependencies are pinned exactly in `pyproject.toml`, and the installers pass `--exclude-newer`
  so transitive dependencies resolve the same for everyone. Change both deliberately.
- **Keep the two installers in step.** Same steps, same order, same messages; the release script
  refuses if `VERSION`, `EXCLUDE_NEWER` or `UV_VERSION` differ between them or from `pyproject.toml`.
- Windows: stdout is forced to UTF-8 and CSV uses `\n` line endings (tests cover both). The
  PowerShell installers run through `iex`: never `exit`, never redirect a native command's stderr.
- OS-specific behaviour goes in `platforms/windows.py` and `platforms/macos.py` (same names in
  both); shared code calls `platforms.current` and never tests `os.name`.
- Writes are never auto-approved: `agents.WRITE_CMDS` become Claude Code `ask` rules. A new
  command that changes data goes in that list.
- Exit codes are part of the contract with agents (see `guide.md`): 1 input, 2 usage, 3 sign-in,
  4 Google refused, 5 network or passing problem, 6 change may or may not have been applied.
- Changes that must not happen twice (append, append-doc, create, add-tab) go through
  `api.run_once`, which retries only a 429; reads and cell overwrites use `api.run` (retried).
- Every range sent to Google names its tab (`ops.resolve_range`); never let Google pick one.

## Test and release (all local; no GitHub Actions)

The owner does not want GitHub Actions for this repo: nothing runs on push, and there are no
workflow files. Everything is tested and released from a Mac:

```sh
uv run pytest                                          # offline tests (both OSes' logic)
uv build --wheel                                       # needs src/workspace_cli/client.json
sh macos/test-install.sh dist/workspace_cli-<v>-py3-none-any.whl
                                                       # real macOS install x2, checks, uninstall,
                                                       # in a throwaway home folder
sh scripts/release.sh                                  # all of the above, then tag + GitHub release
```

Release: bump `version` in `pyproject.toml` and `VERSION`/`$Version` in both installers; keep
`exclude-newer`, `EXCLUDE_NEWER` and `$ExcludeNewer` equal and **in the past** (a future date lets
new dependency versions in between installs); commit and push `main`; run `scripts/release.sh`.
It refuses to publish if the installers disagree, the tree is dirty or unpushed, the tests or the
macOS install test fail, or the version is already released. It publishes the wheel and
`install.ps1`, `uninstall.ps1`, `install.sh`, `uninstall.sh` as release assets. Users and
`gsuite update` fetch installers from `releases/latest/download/`, which moves only when a release
is published, so pushing to `main` never changes what anyone installs.

**Windows is not tested by the release script** (a Mac cannot run Windows). After each release,
one Windows user installs it and runs `windows/test-install.ps1` (see `windows/README.md`), which
checks every piece from PowerShell and Git Bash and prints a pass/fail list. Release to the rest of
the team after that passes.

Installs use `--no-build`: every dependency must come as a ready-built wheel for Windows x64/ARM
and macOS Apple Silicon/Intel (`required-environments` in `pyproject.toml` enforces this when
`uv lock` runs). The release script builds from the local `src/workspace_cli/client.json`.
