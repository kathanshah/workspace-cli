# Checks a gsuite install on a Windows PC: every piece the installer sets up, from PowerShell and
# Git Bash. Run it on the pilot laptop right after the install line (no GitHub Actions involved):
#
#   powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/kathanshah/workspace-cli/main/windows/test-install.ps1 | iex"
#
# It changes nothing. Send the whole output to Kathan. Runs through `iex`: never `exit`.

$ErrorActionPreference = 'Continue'
$failed = 0
function Check($ok, $what) {
  if ($ok) { Write-Host "  ok   $what" } else { Write-Host "  FAIL $what" -ForegroundColor Red; $script:failed++ }
}
$bin = Join-Path $env:USERPROFILE '.local\bin'
$gs = Join-Path $bin 'gsuite.exe'
$gpy = Join-Path $bin 'gpy.exe'

Write-Host "== $([Environment]::OSVersion.VersionString), $env:PROCESSOR_ARCHITECTURE, PowerShell $($PSVersionTable.PSVersion)"
Check (Test-Path (Join-Path $env:LOCALAPPDATA 'gsuite\uv\uv.exe')) 'private uv installed'
Check (Test-Path $gs) 'gsuite.exe installed'
Check (([Environment]::GetEnvironmentVariable('Path', 'User')) -like '*\.local\bin*') 'user PATH contains .local\bin'
Check ($null -ne (Get-Command gsuite -ErrorAction SilentlyContinue)) 'gsuite found by name in this window'
$v = & $gs --version; Check ($v -like 'gsuite *') "gsuite --version ($v)"
Check ((& $gs guide | Out-String) -match 'Rules for AI agents') 'gsuite guide'
$out = & $gpy -c "import sys, gworkspace, pandas; print('₹ राम', sys.version.split()[0])" | Out-String
Check ($out -match '3\.12') "gpy runs Python 3.12 with ₹/Hindi output ($($out.Trim()))"
Check (Test-Path (Join-Path $env:USERPROFILE '.claude\skills\gsuite\SKILL.md')) 'Claude Code skill'
$settings = Join-Path $env:USERPROFILE '.claude\settings.json'
Check ((Test-Path $settings) -and (Select-String -Quiet 'PowerShell\(gsuite write' $settings)) 'Claude Code approval rules'
& $gs whoami
Check ($LASTEXITCODE -eq 0) 'signed in (exit 0)'

$kit = Join-Path $bin 'kit.exe'
Check (Test-Path (Join-Path $env:USERPROFILE '.claude\skills\kit\SKILL.md')) 'Claude Code kit skill'
Check (Test-Path (Join-Path $env:LOCALAPPDATA 'gsuite\tools\pandoc-3.14\pandoc.exe')) 'kit: pandoc downloaded'
Check (Test-Path (Join-Path $env:LOCALAPPDATA 'gsuite\tools\typst-0.15.1\typst.exe')) 'kit: Typst downloaded'
$work = Join-Path $env:TEMP "kit-check-$PID"
New-Item -ItemType Directory -Force $work | Out-Null
[IO.File]::WriteAllText((Join-Path $work 'q.md'), "# Quote $([char]0x0930)$([char]0x093E)$([char]0x092E)`n`n| Item | Price |`n|---|--:|`n| Laptop | $([char]0x20B9)12,500 |`n", (New-Object Text.UTF8Encoding $false))
& $kit convert (Join-Path $work 'q.md') pdf
Check ($LASTEXITCODE -eq 0) 'kit: Markdown to PDF'
$prevEnc = [Console]::OutputEncoding
[Console]::OutputEncoding = [Text.Encoding]::UTF8   # read kit's UTF-8 output as UTF-8
$text = & $kit pdf text (Join-Path $work 'q.pdf') | Out-String
[Console]::OutputEncoding = $prevEnc
Check ($text -match 'Laptop' -and $text.Contains([string][char]0x20B9) -and $text.Contains([string][char]0x0930)) 'kit: PDF text read back with ₹ and Hindi'
& $kit convert (Join-Path $work 'q.md') docx
Check ($LASTEXITCODE -eq 0) 'kit: Markdown to Word'
Remove-Item -Recurse -Force $work -ErrorAction SilentlyContinue

$bash = Join-Path $env:ProgramFiles 'Git\bin\bash.exe'
if (Test-Path $bash) {
  & $bash -lc 'gsuite --version && gpy -c "print(chr(8377))" && kit --version'
  Check ($LASTEXITCODE -eq 0) 'gsuite, gpy and kit work from Git Bash (as Claude Code runs them)'
} else {
  Write-Host '  --   Git Bash not installed (Claude Code will use PowerShell; skipped)'
}

& $gs doctor
if ($failed) { Write-Host "`n$failed check(s) failed." -ForegroundColor Red } else { Write-Host "`nWindows install: all checks passed." -ForegroundColor Green }
