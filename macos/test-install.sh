#!/bin/sh
# Full local test of the macOS installer, in a throwaway home folder (nothing real is touched):
# install, install again over it, check every piece, uninstall, check nothing is left.
#
#   sh macos/test-install.sh dist/workspace_cli-<version>-py3-none-any.whl
#
# Needs no sign-in: it checks that gsuite reports "not signed in" (exit 3) instead of crashing.
set -eu

WHEEL="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
HERE="$(cd "$(dirname "$0")" && pwd)"
FAKE="$(mktemp -d)"
trap 'rm -rf "$FAKE"' EXIT
# A brand-new Mac's environment: ~/.local/bin is not on PATH until the installer adds it.
fresh() { env -i HOME="$FAKE" SHELL=/bin/zsh TERM="${TERM:-xterm}" PATH="/usr/bin:/bin:/usr/sbin:/sbin" "$@"; }
# A new Terminal window after installing: the PATH line the installer wrote is in effect.
run() { env -i HOME="$FAKE" SHELL=/bin/zsh TERM="${TERM:-xterm}" PATH="$FAKE/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin" "$@"; }
check() { if "$@"; then printf '  ok   %s\n' "$*"; else printf '  FAIL %s\n' "$*"; exit 1; fi; }

for n in 1 2; do
  echo "== install run $n"
  fresh GSUITE_WHEEL="$WHEEL" GSUITE_SKIP_LOGIN=1 sh "$HERE/install.sh" >"$FAKE/install-$n.log" 2>&1 \
    || { cat "$FAKE/install-$n.log"; echo "FAIL: install run $n"; exit 1; }
done
grep -q "Preparing the installer" "$FAKE/install-1.log"
! grep -q "Preparing the installer" "$FAKE/install-2.log"   # the second run reuses the private uv

echo "== checks"
check test -x "$FAKE/.local/share/gsuite/uv/uv"
check test -x "$FAKE/.local/bin/gsuite"
check grep -q '.local/bin' "$FAKE/.zshenv"
check run sh -c 'gsuite --version | grep -q "^gsuite "'
check run sh -c 'gsuite guide | grep -q "Rules for AI agents"'
check run sh -c 'gpy -c "import sys, gworkspace, pandas; print(\"₹ राम\", sys.version)" | grep -q "₹ राम 3.12"'
check run sh -c 'gpy -c "import sys; print(sys.base_prefix)" | grep -q "/.local/share/uv/python/"'   # uv-managed Python
check test -f "$FAKE/.claude/skills/gsuite/SKILL.md"
check grep -q 'Bash(gsuite write \*)' "$FAKE/.claude/settings.json"
check run sh -c 'gsuite whoami; test $? -eq 3'
check test -f "$FAKE/.claude/skills/kit/SKILL.md"
check grep -q 'Bash(kit convert \*)' "$FAKE/.claude/settings.json"
check test -x "$FAKE/.local/share/gsuite/tools/pandoc-3.14/pandoc"
check test -x "$FAKE/.local/share/gsuite/tools/typst-0.15.1/typst"
mkdir -p "$FAKE/work" && printf '# Quote — राम\n\n| Item | Price |\n|---|--:|\n| Laptop | ₹12,500 |\n' > "$FAKE/work/q.md"
printf 'Phone,Amount\n+919876543210,12.50\n' > "$FAKE/work/a.csv"
check run sh -c 'cd "$HOME/work" && kit convert q.md pdf && kit convert q.md docx'
check run sh -c 'kit pdf text "$HOME/work/q.pdf" | grep -q "₹12,500"'
check run sh -c 'kit pdf tables "$HOME/work/q.pdf" | grep -q "Laptop"'
check run sh -c 'cd "$HOME/work" && kit sheet convert a.csv xlsx && kit sheet read a.xlsx | grep -q "+919876543210,12.5"'
check run sh -c 'gsuite doctor | grep -q "\[ok\] gsuite is on PATH"'
check run sh -c 'ls "$HOME"/.config/uv/uv-receipt.json 2>/dev/null; test ! -e "$HOME/.config/uv/uv-receipt.json"'   # private uv leaves no receipt

echo "== uninstall"
fresh sh "$HERE/uninstall.sh" >/dev/null 2>&1
for p in .local/bin/gsuite .local/bin/kit .local/share/gsuite .config/gsuite .claude/skills/gsuite .claude/skills/kit .local/share/uv/tools/workspace-cli; do
  check test ! -e "$FAKE/$p"
done
check sh -c "! grep -q -e gsuite -e kit '$FAKE/.claude/settings.json'"
echo "macOS installer: all checks passed."
