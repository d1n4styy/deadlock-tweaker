# Deadlock Tweaker — release automation
#
# FULL build (compiles new exe, ~2-3 min):
#   .\release.ps1 -Version "1.1.0" -Notes "What changed"
#
# QUICK patch (uploads main.py only, ~10 sec, no rebuild needed):
#   .\release.ps1 -Version "1.0.5" -Notes "Fix something" -Quick
#
param(
    [Parameter(Mandatory)][string]$Version,
    [Parameter(Mandatory)][string]$Notes,
    [switch]$Quick   # upload main.py as main_patch.py instead of rebuilding
)

$ErrorActionPreference = "Stop"
$root   = $PSScriptRoot
$thumb  = "B7327D504A41EAF8A0C7CC7AE7AC44E908679562"

$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH","User")

# -- 1. Bump APP_VERSION in main.py + source-build/main.py --------------------
foreach ($f in @("$root\main.py", "$root\source-build\main.py")) {
    $c = Get-Content $f -Raw
    $c = $c -replace 'APP_VERSION = "[^"]+"', "APP_VERSION = `"$Version`""
    Set-Content $f -Value $c -Encoding UTF8
}
Write-Host "[OK] APP_VERSION -> $Version"

# -- 2. Bump #define AppVersion in installer.iss ------------------------------
$iss = Get-Content "$root\installer.iss" -Raw
$iss = $iss -replace '#define AppVersion "[^"]+"', "#define AppVersion `"$Version`""
Set-Content "$root\installer.iss" -Value $iss -Encoding UTF8
Write-Host "[OK] installer.iss -> $Version"

# -- 3. Update release-feed.json ----------------------------------------------
$feed = @{
    repo            = "d1n4styy/deadlock-tweaker"
    version         = $Version
    notes           = $Notes
    latest_api_url  = "https://api.github.com/repos/d1n4styy/deadlock-tweaker/releases/latest"
    release_url     = "https://github.com/d1n4styy/deadlock-tweaker/releases/tag/v$Version"
    download_url    = "https://github.com/d1n4styy/deadlock-tweaker/releases/download/v$Version/DeadlockTweaker.exe"
    preferred_asset = "DeadlockTweaker.exe"
} | ConvertTo-Json -Depth 3
Set-Content "$root\release-feed.json"              -Value $feed -Encoding UTF8
Set-Content "$root\source-build\release-feed.json" -Value $feed -Encoding UTF8
Write-Host "[OK] release-feed.json updated"

# -- 4. Git commit + tag + push -----------------------------------------------
Set-Location $root
git add -A -- main.py "source-build\main.py" release-feed.json "source-build\release-feed.json" installer.iss release.ps1
$mode = if ($Quick) { "quick" } else { "release" }
git commit -m "${mode}: v${Version} - ${Notes}"
git tag "v$Version"
# git push may write to stderr even on success; ignore the exit code
git push origin main 2>&1 | Out-Null
git push origin "v$Version" 2>&1 | Out-Null
Write-Host "[OK] Pushed v$Version"

if ($Quick) {
    # -- QUICK MODE: upload main.py as main_patch.py (~200 KB) ----------------
    Write-Host ""
    Write-Host "QUICK: No PyInstaller rebuild - uploading patch only" -ForegroundColor Cyan

    $patchTemp = "$root\installer-output\main_patch.py"
    Copy-Item "$root\main.py" $patchTemp -Force
    $kb = [math]::Round((Get-Item $patchTemp).Length / 1KB, 1)

    gh release create "v$Version" $patchTemp `
        --title "Deadlock Tweaker v$Version" `
        --notes $Notes `
        --repo d1n4styy/deadlock-tweaker

    Write-Host ("[OK] Release v" + $Version + " created with main_patch.py (" + $kb + " KB)") -ForegroundColor Green
    Remove-Item $patchTemp -ErrorAction SilentlyContinue

} else {
    # -- FULL MODE: build exe -> sign -> upload --------------------------------
    Write-Host ""
    Write-Host "FULL: Building exe with PyInstaller..." -ForegroundColor Cyan

    Set-Location $root
    python -m PyInstaller "Deadlock Opti v1.0.spec" --noconfirm
    $exePath = "$root\dist\DeadlockTweaker.exe"
    if (-not (Test-Path $exePath)) { throw "Build output not found: $exePath" }
    $mb = [math]::Round((Get-Item $exePath).Length / 1MB, 1)
    Write-Host ("[OK] Build complete (" + $mb + " MB)")

    # Sign
    $cert = Get-Item "Cert:\CurrentUser\My\$thumb"
    $sig  = Set-AuthenticodeSignature -FilePath $exePath -Certificate $cert
    if ($sig.Status -ne "Valid") {
        Write-Warning ("Signing status: " + $sig.Status)
    } else {
        Write-Host "[OK] Signed"
    }

    # Create GitHub release + upload
    gh release create "v$Version" $exePath `
        --title "Deadlock Tweaker v$Version" `
        --notes $Notes `
        --repo d1n4styy/deadlock-tweaker

    Write-Host ("[OK] Release v" + $Version + " created with DeadlockTweaker.exe (" + $mb + " MB)") -ForegroundColor Green
}

Write-Host ""
Write-Host "DONE  https://github.com/d1n4styy/deadlock-tweaker/releases/tag/v$Version" -ForegroundColor Green
