# Deadlock Tweaker — release helper
# Usage: .\release.ps1 -Version "1.1.0" -Notes "What was fixed/added"
param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$Notes
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

# ── 1. Update version.json ───────────────────────────────────────────────────
$versionFile = Join-Path $root "version.json"
$json = @{
    version      = $Version
    notes        = $Notes
    download_url = "https://github.com/d1n4styy/deadlock-tweaker/releases/download/v$Version/DeadlockTweaker.exe"
} | ConvertTo-Json -Depth 2
Set-Content -Path $versionFile -Value $json -Encoding UTF8
Write-Host "✓ version.json updated to $Version"

# ── 2. Update APP_VERSION in main.py ─────────────────────────────────────────
$mainFile = Join-Path $root "main.py"
$content  = Get-Content $mainFile -Raw
$updated  = $content -replace 'APP_VERSION = "[^"]+"', "APP_VERSION = `"$Version`""
Set-Content -Path $mainFile -Value $updated -Encoding UTF8
Write-Host "✓ main.py APP_VERSION updated to $Version"

# ── 3. Git commit + tag + push ───────────────────────────────────────────────
Set-Location $root
git add version.json main.py
git commit -m "release: v$Version — $Notes"
git tag "v$Version"
git push origin main
git push origin "v$Version"
Write-Host "✓ Pushed v$Version to GitHub"
Write-Host ""
Write-Host "Next step: go to https://github.com/d1n4styy/deadlock-tweaker/releases/new"
Write-Host "           select tag v$Version and upload DeadlockTweaker.exe"
