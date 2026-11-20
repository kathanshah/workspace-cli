# Removes gsuite and kit from this PC: the programs, the sign-in, the Claude Code skills and rules,
# kit's document engines and the installer's private uv. Paste into PowerShell:
#
#   powershell -ExecutionPolicy ByPass -c "irm https://github.com/kathanshah/workspace-cli/releases/latest/download/uninstall.ps1 | iex"
#
# Google files are not touched. The Google approval itself stays on the account; remove it at
# https://myaccount.google.com/connections if wanted (that signs gsuite out on every computer).
# uv's shared download cache and Python are left in place: other uv tools may use them.
# Runs through `iex`: never `exit`.

$ErrorActionPreference = 'Continue'
$GsuiteData = Join-Path $env:LOCALAPPDATA 'gsuite'
$Uv = Join-Path $GsuiteData 'uv\uv.exe'
$Bin = Join-Path $env:USERPROFILE '.local\bin'
$gs = Join-Path $Bin 'gsuite.exe'
$Tool = Join-Path $env:APPDATA 'uv\data\tools\workspace-cli'

if (Test-Path $gs) {
  & $gs install-agent claude --remove
  & $gs logout
}
# The private uv removes the program cleanly; an install made before it existed (gsuite 1.0.0)
# is removed by hand.
if (Test-Path $Uv) {
  $env:UV_TOOL_BIN_DIR = $Bin
  & $Uv tool uninstall workspace-cli | Out-Null
}
foreach ($p in @($Tool, (Join-Path $Bin 'gsuite.exe'), (Join-Path $Bin 'gpy.exe'), (Join-Path $Bin 'kit.exe'), $GsuiteData, (Join-Path $env:APPDATA 'gsuite'))) {
  if (Test-Path $p) { Remove-Item -Recurse -Force $p -ErrorAction SilentlyContinue }
}

$left = @($gs, (Join-Path $Bin 'kit.exe'), $Tool, (Join-Path $env:APPDATA 'gsuite'), (Join-Path $env:USERPROFILE '.claude\skills\gsuite'), (Join-Path $env:USERPROFILE '.claude\skills\kit')) | Where-Object { Test-Path $_ }
if ($left) {
  Write-Host "`n==> Could not remove: $($left -join ', ')  (close every gsuite and Claude Code window, run this again, or send this to Kathan)" -ForegroundColor Red
} else {
  Write-Host "`n==> gsuite is removed from this PC." -ForegroundColor Cyan
}
