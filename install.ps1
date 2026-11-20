# gsuite installer for Windows. Paste into PowerShell (or Command Prompt, or Win+R):
#
#   powershell -ExecutionPolicy ByPass -c "irm https://github.com/kathanshah/workspace-cli/releases/latest/download/install.ps1 | iex"
#
# Safe to run again: it updates gsuite, keeps the sign-in, and only asks to sign in if needed.
# Testing hooks: GSUITE_WHEEL=<path or URL> installs a local build; GSUITE_SKIP_LOGIN=1 skips sign-in.
#
# Notes for editors: this runs through `iex`, so never call `exit` (it would close the person's
# window); stop with `throw`. Native commands are checked with $LASTEXITCODE, and their stderr is
# never redirected: Windows PowerShell 5.1 turns redirected stderr into terminating errors.

$ErrorActionPreference = 'Continue'
$Version = '1.0.0'
$ExcludeNewer = '2026-11-21T00:00:00Z'   # dependency snapshot: every install resolves the same versions
$Repo = 'kathanshah/workspace-cli'
$Wheel = if ($env:GSUITE_WHEEL) { $env:GSUITE_WHEEL } else {
  "https://github.com/$Repo/releases/download/v$Version/workspace_cli-$Version-py3-none-any.whl" }

function Say($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

$bin = Join-Path $env:USERPROFILE '.local\bin'
$env:Path = "$bin;$env:Path"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Say 'Installing uv (the Python tool installer)'
  $uvInstaller = Invoke-RestMethod https://astral.sh/uv/0.13.9/install.ps1 -ErrorAction Stop
  Invoke-Expression $uvInstaller
  $env:Path = "$bin;$env:Path"
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Could not install uv. Check the internet connection and run this again.' }
}

Say "Installing gsuite $Version"
uv tool install --force --no-build --python 3.12 --exclude-newer $ExcludeNewer $Wheel
if ($LASTEXITCODE -ne 0) { throw 'Could not install gsuite. Check the internet connection and run this again.' }
uv tool update-shell | Out-Null
$gs = Join-Path (uv tool dir --bin) 'gsuite.exe'
& $gs --version

Say 'Setting up Claude Code'
& $gs install-agent claude

if (-not $env:GSUITE_SKIP_LOGIN) {
  & $gs whoami --quiet
  if ($LASTEXITCODE -eq 0) {
    Say "Already signed in as $(& $gs whoami)"
  } else {
    Say 'Sign in with your @spurge.rentals Google account'
    & $gs login
    if ($LASTEXITCODE -ne 0) { throw 'Sign-in did not finish. Run: gsuite login' }
  }
  Say 'Checking everything'
  & $gs doctor
}

Say 'Done. Close this window, open a new Claude Code session, then paste a Google Sheet link and ask away.'
