#!/bin/sh
# Removes gsuite and kit from this Mac: the programs, the sign-in, the Claude Code skills and rules,
# kit's document engines and the installer's private uv. Paste into Terminal:
#
#   curl -LsSf https://github.com/kathanshah/workspace-cli/releases/latest/download/uninstall.sh | sh
#
# Google files are not touched. The Google approval itself stays on the account; remove it at
# https://myaccount.google.com/connections if wanted (that signs gsuite out on every computer).
# uv's shared download cache and Python are left in place: other uv tools may use them.
set -u

UV="$HOME/.local/share/gsuite/uv/uv"
BIN="$HOME/.local/bin"
TOOL="$HOME/.local/share/uv/tools/workspace-cli"

say() { printf '\n==> %s\n' "$1"; }

if [ -x "$BIN/gsuite" ]; then
  "$BIN/gsuite" install-agent claude --remove || true
  "$BIN/gsuite" logout || true
fi
# The private uv removes the program cleanly; an install made before it existed (gsuite 1.0.0)
# is removed by hand.
if [ -x "$UV" ]; then
  UV_TOOL_BIN_DIR="$BIN" "$UV" tool uninstall workspace-cli >/dev/null 2>&1 || true
fi
rm -rf "$TOOL"
rm -f "$BIN/gsuite" "$BIN/gpy" "$BIN/kit"
rm -rf "$HOME/.local/share/gsuite" "$HOME/.config/gsuite"

left=""
for p in "$BIN/gsuite" "$BIN/kit" "$TOOL" "$HOME/.config/gsuite" "$HOME/.claude/skills/gsuite" "$HOME/.claude/skills/kit"; do
  [ -e "$p" ] && left="$left $p"
done
if [ -n "$left" ]; then
  say "Could not remove:$left  (send this to Kathan)"
  exit 1
fi
say "gsuite is removed from this Mac."
