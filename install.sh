#!/bin/sh
# gsuite installer for macOS (and Linux). Paste into Terminal:
#
#   curl -LsSf https://github.com/kathanshah/workspace-cli/releases/latest/download/install.sh | sh
#
# Safe to run again: it updates gsuite, keeps the sign-in, and only asks to sign in if needed.
# Testing hooks: GSUITE_WHEEL=<path or URL> installs a local build; GSUITE_SKIP_LOGIN=1 skips sign-in.
set -eu

VERSION="1.0.0"
EXCLUDE_NEWER="2026-11-21T00:00:00Z"   # dependency snapshot: every install resolves the same versions
REPO="kathanshah/workspace-cli"
WHEEL="${GSUITE_WHEEL:-https://github.com/$REPO/releases/download/v$VERSION/workspace_cli-$VERSION-py3-none-any.whl}"

say() { printf '\n==> %s\n' "$1"; }
fail() { printf '\nERROR: %s\n' "$1" >&2; exit 1; }

export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  say "Installing uv (the Python tool installer)"
  curl -LsSf https://astral.sh/uv/0.13.9/install.sh | sh || fail "could not install uv; check the internet connection"
  export PATH="$HOME/.local/bin:$PATH"
fi

say "Installing gsuite $VERSION"
uv tool install --force --no-build --python 3.12 --exclude-newer "$EXCLUDE_NEWER" "$WHEEL" \
  || fail "could not install gsuite; check the internet connection and run this again"
uv tool update-shell >/dev/null 2>&1 || true
GS="$(uv tool dir --bin)/gsuite"
"$GS" --version

say "Setting up Claude Code"
"$GS" install-agent claude || true   # a problem here is reported, and by doctor; sign-in still goes ahead

if [ -z "${GSUITE_SKIP_LOGIN:-}" ]; then
  if "$GS" whoami --quiet; then
    say "Already signed in as $("$GS" whoami)"
  else
    say "Sign in with your @spurge.rentals Google account"
    "$GS" login || fail "sign-in did not finish; run: gsuite login"
  fi
  say "Checking everything"
  "$GS" doctor || true
fi

say "Done. Open a new terminal or Claude Code session, then paste a Google Sheet link and ask away."
