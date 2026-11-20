#!/bin/sh
# gsuite installer for macOS (Apple Silicon and Intel). Paste into Terminal:
#
#   curl -LsSf https://github.com/kathanshah/workspace-cli/releases/latest/download/install.sh | sh
#
# Safe to run again: it updates gsuite, keeps the sign-in, and only asks to sign in if needed.
# Testing hooks: GSUITE_WHEEL=<path or URL> installs a local build; GSUITE_SKIP_LOGIN=1 skips sign-in.
# The Windows installer is windows/install.ps1; keep the two in step (see AGENTS.md).
set -eu

VERSION="1.1.0"
EXCLUDE_NEWER="2026-11-20T00:00:00Z"   # dependency snapshot (a past date): every install resolves the same versions
UV_VERSION="0.13.9"                     # the installer's own uv, kept private (see below)
REPO="kathanshah/workspace-cli"
WHEEL="${GSUITE_WHEEL:-https://github.com/$REPO/releases/download/v$VERSION/workspace_cli-$VERSION-py3-none-any.whl}"

UV_DIR="$HOME/.local/share/gsuite/uv"
UV="$UV_DIR/uv"
BIN="$HOME/.local/bin"
GS="$BIN/gsuite"
# Fixed locations, whatever XDG or uv settings this Mac has; and uv's own Python, never a Homebrew or
# system one that an update could remove.
export UV_TOOL_BIN_DIR="$BIN"
export UV_PYTHON_PREFERENCE=only-managed

say() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

# 1. A private, pinned uv. Any other uv on this Mac is never used, and nothing of it is changed:
#    UV_UNMANAGED_INSTALL installs into one folder, edits no PATH and writes no update record.
if [ "$("$UV" --version 2>/dev/null | cut -d' ' -f2)" != "$UV_VERSION" ]; then
  say "Preparing the installer (uv $UV_VERSION)"
  tmp="$(mktemp)"
  curl -fLsS "https://astral.sh/uv/$UV_VERSION/install.sh" -o "$tmp" \
    || { rm -f "$tmp"; fail "could not download the installer; check the internet connection and run this again"; }
  UV_UNMANAGED_INSTALL="$UV_DIR" sh "$tmp" >/dev/null 2>&1 || true
  rm -f "$tmp"
  [ -x "$UV" ] || fail "could not set up the installer in $UV_DIR; check the internet connection and run this again"
fi

# 2. gsuite itself, from the release wheel, with every dependency as a ready-built package.
say "Installing gsuite $VERSION"
"$UV" tool install --force --no-build --python 3.12 --exclude-newer "$EXCLUDE_NEWER" "$WHEEL" \
  || fail "could not install gsuite; check the internet connection and run this again"
[ -x "$GS" ] || fail "gsuite did not end up in $BIN; send this output to Kathan"
"$UV" tool update-shell >/dev/null 2>&1 || true   # ~/.local/bin on PATH for new Terminal windows
export PATH="$BIN:$PATH"                           # ...and for the rest of this script
"$GS" --version || fail "gsuite was installed but does not start; send this output to Kathan"

# 3. Claude Code: skill + approval rules. A problem here is reported (and by doctor); sign-in still goes ahead.
say "Setting up Claude Code"
"$GS" install-agent claude || true

# 4. Sign-in, unless this Mac is already signed in (exit 3 = not signed in; anything else is reported).
if [ -z "${GSUITE_SKIP_LOGIN:-}" ]; then
  status=0
  "$GS" whoami --quiet || status=$?
  if [ "$status" -eq 0 ]; then
    say "Already signed in as $("$GS" whoami)"
  elif [ "$status" -eq 3 ]; then
    say "Sign in with your @spurge.rentals Google account"
    "$GS" login || fail "sign-in did not finish; run: gsuite login"
  else
    say "Could not check the sign-in right now (no internet?). Run gsuite login later if gsuite asks."
  fi
  say "Checking everything"
  "$GS" doctor || true
fi

say "Done. Open a new Terminal window or Claude Code session, then paste a Google Sheet link and ask away."
