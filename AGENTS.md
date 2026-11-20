# Working on gsuite

Guide for anyone (person or agent) changing this repository. Users read [README.md](README.md);
agents that *use* gsuite read `gsuite guide` (`src/workspace_cli/guide.md`).

## Layout

| Path | What |
|---|---|
| `src/workspace_cli/cli.py` | Commands, exit codes, friendly Google errors |
| `src/workspace_cli/auth.py` | Sign-in, token storage, domain check |
| `src/workspace_cli/api.py` | Signed-in API clients with retries |
| `src/workspace_cli/agents.py` | `install-agent claude`: skill + permission rules |
| `src/workspace_cli/doctor.py` | `doctor` and `update` |
| `src/workspace_cli/guide.md` | The one source of agent rules (`gsuite guide`) |
| `src/workspace_cli/client.json` | The OAuth Desktop client (see below); git-ignored, added at build time |
| `src/gworkspace/` | Import shim for `gpy` scripts: `from gworkspace import sheet` |
| `install.sh`, `install.ps1` | One-line installers, attached to each release; they install the release wheel with a pinned uv |

## The sign-in client

`client.json` is the Desktop OAuth client `team-gsuite` in Google Cloud project
`spurge-rentals-seo`. The app is **Internal** to the spurge.rentals Workspace (only its accounts
can sign in, and logins do not expire after 7 days) and is marked **Trusted** under Admin console,
Security, API controls. A Desktop client's secret cannot be kept secret, since every installed
copy carries it; access comes from each person's own login, not from this file.

It is kept out of git (secret scanners flag it, and GitHub push protection blocks it) and lives
in the repository secret `GSUITE_CLIENT_JSON`; CI writes it into `src/workspace_cli/client.json`
before building, so every release wheel carries it. For local work, put the JSON at that path.

To replace it (for example if Google disables it): create a new Desktop client or add a secret to
`team-gsuite` in the console, run `gh secret set GSUITE_CLIENT_JSON < client.json`, release, and
have everyone run `gsuite update` or the install line. Existing logins made with the old client then need `gsuite login`.

Scopes are in `auth.SCOPES`. Adding one makes every saved login report "needs one more
permission" until the person runs `gsuite login`, so add scopes rarely and say so in the release.

## Rules that keep it stable

- Dependencies are pinned exactly in `pyproject.toml`, and the installers pass `--exclude-newer`
  so transitive dependencies resolve the same for everyone. Change both deliberately.
- Windows: stdout is forced to UTF-8 and CSV uses `\n` line endings (tests cover both). The
  PowerShell installer runs through `iex`: never `exit`, never redirect a native command's stderr.
- Writes are never auto-approved: `agents.WRITE_CMDS` become Claude Code `ask` rules. A new
  command that changes data goes in that list.
- Exit codes are part of the contract with agents (see `guide.md`): 3 sign-in, 4 Google refused,
  5 network.

## Test and release

```sh
uv run pytest                      # offline tests
uv build --wheel                   # dist/workspace_cli-<version>-py3-none-any.whl
GSUITE_WHEEL=dist/<wheel> sh install.sh   # try the installer against a local build
```

CI (`.github/workflows/ci.yml`) runs the tests, then the real installer on fresh Windows x64,
Windows ARM, Apple Silicon and Intel Mac machines (no uv preinstalled), for every push.

Release: bump `version` in `pyproject.toml` and `VERSION` in both installers (CI fails if they
differ), and keep `exclude-newer` / `EXCLUDE_NEWER` equal; push; once CI is green, push the tag
`v<version>`. The release workflow reruns CI, then publishes the wheel **and both installers** as
release assets. Users and `gsuite update` fetch installers from `releases/latest/download/`, which
moves only when a release is fully published, so pushing to `main` never breaks an install.

Installs use `--no-build`: every dependency must come as a ready-built wheel for all four machine
types (`required-environments` in `pyproject.toml` enforces this for the lockfile). If a bump
breaks that, CI's fresh-install job fails rather than a teammate's install.
