# gsuite and kit installer for Windows 10/11 (x64 and ARM). Paste into PowerShell (or Command Prompt, or Win+R):
#
#   powershell -ExecutionPolicy ByPass -c "irm https://github.com/kathanshah/workspace-cli/releases/latest/download/install.ps1 | iex"
#
# Safe to run again: it updates gsuite, keeps the sign-in, and only asks to sign in if needed.
# Testing hooks: GSUITE_WHEEL=<path or URL> installs a local build; GSUITE_SKIP_LOGIN=1 skips sign-in.
# The macOS installer is macos/install.sh; keep the two in step (see AGENTS.md).
#
# Notes for editors: this runs through `iex` in the person's own window, so never call `exit` (it
# would close the window); stop with `throw`. Native commands are checked with $LASTEXITCODE, and
# their stderr is never redirected: Windows PowerShell 5.1 turns redirected stderr into errors.
# Paths are built with Join-Path from environment variables, never parsed from command output
# (5.1 decodes captured output in the console code page, which garbles non-ASCII user names).

$ErrorActionPreference = 'Continue'
$Version = '1.2.0'
$ExcludeNewer = '2026-11-20T00:00:00Z'   # dependency snapshot (a past date): every install resolves the same versions
$UvVersion = '0.13.9'                    # the installer's own uv, kept private (see below)
$Repo = 'kathanshah/workspace-cli'
$Wheel = if ($env:GSUITE_WHEEL) { $env:GSUITE_WHEEL } else {
  "https://github.com/$Repo/releases/download/v$Version/workspace_cli-$Version-py3-none-any.whl" }

$UvDir = Join-Path $env:LOCALAPPDATA 'gsuite\uv'
$Uv = Join-Path $UvDir 'uv.exe'
$Bin = Join-Path $env:USERPROFILE '.local\bin'
$gs = Join-Path $Bin 'gsuite.exe'
# Fixed locations, whatever XDG or uv settings this PC has; and uv's own Python, never a system
# one that an update could remove.
$env:UV_TOOL_BIN_DIR = $Bin
$env:UV_PYTHON_PREFERENCE = 'only-managed'
# Older Windows 10 builds do not offer TLS 1.2 by default, and GitHub requires it.
[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

function Say($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }

# 1. A private, pinned uv. Any other uv on this PC is never used, and nothing of it is changed:
#    UV_UNMANAGED_INSTALL installs into one folder, edits no PATH and writes no update record.
$have = if (Test-Path $Uv) { "$(& $Uv --version)".Split(' ')[1] } else { '' }
if ($have -ne $UvVersion) {
  Say "Preparing the installer (uv $UvVersion)"
  $script = Join-Path $env:TEMP "gsuite-uv-installer-$PID.ps1"
  try {
    Invoke-WebRequest "https://astral.sh/uv/$UvVersion/install.ps1" -OutFile $script -UseBasicParsing -ErrorAction Stop
  } catch {
    throw 'Could not download the installer. Check the internet connection and run this again.'
  }
  # uv's own installer runs in a separate PowerShell (it calls `exit` on failure, which would close
  # this window) and reads its folder from the environment it inherits.
  $env:UV_UNMANAGED_INSTALL = $UvDir
  powershell -NoProfile -ExecutionPolicy Bypass -File $script | Out-Null
  Remove-Item Env:UV_UNMANAGED_INSTALL
  Remove-Item $script -ErrorAction SilentlyContinue
  if (-not (Test-Path $Uv)) { throw "Could not set up the installer in $UvDir. Check the internet connection and run this again." }
}

# 2. gsuite itself, from the release wheel, with every dependency as a ready-built package.
Say "Installing gsuite $Version"
& $Uv tool install --force --no-build --python 3.12 --exclude-newer $ExcludeNewer $Wheel
if ($LASTEXITCODE -ne 0) { throw 'Could not install gsuite. Check the internet connection and run this again.' }
if (-not (Test-Path $gs)) { throw "gsuite did not end up in $Bin. Send this output to Kathan." }
& $Uv tool update-shell | Out-Null   # %USERPROFILE%\.local\bin on the user PATH for new windows
$env:Path = "$Bin;$env:Path"         # ...and for the rest of this script
& $gs --version
if ($LASTEXITCODE -ne 0) { throw 'gsuite was installed but does not start. Send this output to Kathan.' }

# 3. Claude Code: skills + approval rules. A problem here is reported (and by doctor); sign-in still goes ahead.
Say 'Setting up Claude Code'
& $gs install-agent claude

# 4. kit's document engines (pandoc, Typst; about 60 MB, once). If this fails, kit retries on first use.
Say 'Setting up kit (documents, PDFs, spreadsheets, web)'
& (Join-Path $Bin 'kit.exe') setup
if ($LASTEXITCODE -ne 0) { Say "Could not download kit's document tools now; kit will try again when first used." }

# 5. Sign-in, unless this PC is already signed in (exit 3 = not signed in; anything else is reported).
if (-not $env:GSUITE_SKIP_LOGIN) {
  & $gs whoami --quiet
  $status = $LASTEXITCODE
  if ($status -eq 0) {
    Say "Already signed in as $(& $gs whoami)"
  } elseif ($status -eq 3) {
    Say 'Sign in with your @spurge.rentals Google account'
    & $gs login
    if ($LASTEXITCODE -ne 0) { throw 'Sign-in did not finish. Run: gsuite login' }
  } else {
    Say 'Could not check the sign-in right now (no internet?). Run gsuite login later if gsuite asks.'
  }
  Say 'Checking everything'
  & $gs doctor
}

Say 'Done. Close this window, open a new Claude Code session, then paste a Google Sheet link and ask away.'
