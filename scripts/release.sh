#!/bin/sh
# Release gsuite from this Mac. No GitHub Actions: everything is checked and built here, then
# published as a GitHub release with `gh`.
#
#   sh scripts/release.sh            # releases the version in pyproject.toml
#
# Stops before publishing if anything is off. Windows cannot be tested on a Mac: after a release,
# the pilot runs windows/test-install.ps1 on a Windows laptop (see windows/README.md).
set -eu
cd "$(dirname "$0")/.."

fail() { printf '\nRELEASE STOPPED: %s\n' "$1" >&2; exit 1; }
say() { printf '\n== %s\n' "$1"; }

v=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
d=$(grep -m1 '^exclude-newer' pyproject.toml | cut -d'"' -f2)
u=$(grep -m1 '^UV_VERSION=' macos/install.sh | cut -d'"' -f2)
WHEEL="dist/workspace_cli-$v-py3-none-any.whl"

say "Checking release v$v"
grep -q "^VERSION=\"$v\"" macos/install.sh || fail "macos/install.sh VERSION is not $v"
grep -q "^\$Version = '$v'" windows/install.ps1 || fail "windows/install.ps1 \$Version is not $v"
grep -q "^EXCLUDE_NEWER=\"$d\"" macos/install.sh || fail "macos/install.sh EXCLUDE_NEWER is not $d"
grep -q "^\$ExcludeNewer = '$d'" windows/install.ps1 || fail "windows/install.ps1 \$ExcludeNewer is not $d"
grep -q "^\$UvVersion = '$u'" windows/install.ps1 || fail "uv versions differ between the installers"
[ "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \> "$d" ] || fail "exclude-newer ($d) must be in the past"
test -s src/workspace_cli/client.json || fail "src/workspace_cli/client.json is missing (see AGENTS.md)"
[ -z "$(git status --porcelain)" ] || fail "commit everything first"
[ "$(git rev-parse --abbrev-ref HEAD)" = main ] || fail "release from main"
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || fail "push main first"
if gh release view "v$v" >/dev/null 2>&1; then fail "v$v is already released; bump the version"; fi

say "Tests"
uv run --locked -q pytest -q

say "Build"
rm -rf dist
uv build -q --wheel
unzip -l "$WHEEL" | grep -q workspace_cli/client.json || fail "the wheel does not carry the OAuth client"

say "macOS installer, end to end (throwaway home folder)"
sh macos/test-install.sh "$WHEEL"

say "Publishing v$v"
git tag -a "v$v" -m "v$v"
git push -q origin "v$v"
gh release create "v$v" --title "v$v" --generate-notes \
  "$WHEEL" windows/install.ps1 windows/uninstall.ps1 macos/install.sh macos/uninstall.sh

say "Checking what teammates now download"
curl -fsSL "https://github.com/kathanshah/workspace-cli/releases/latest/download/install.sh" | grep -q "^VERSION=\"$v\"" \
  || fail "releases/latest does not serve v$v yet"
curl -fsSL "https://github.com/kathanshah/workspace-cli/releases/latest/download/install.ps1" | grep -q "^\$Version = '$v'" \
  || fail "releases/latest does not serve the v$v Windows installer"
printf '\nReleased v%s. Next: the Windows pilot runs windows/test-install.ps1 after installing.\n' "$v"
