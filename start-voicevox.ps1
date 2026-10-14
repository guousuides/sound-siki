# Launch VOICEVOX Engine in the background (Windows), for the train's announcements.
# Usage: .\start-voicevox.ps1
$port = 50021
$conn = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($conn) {
    Write-Host "VOICEVOX Engine is already running on port $port." -ForegroundColor Green
    exit 0
}

# Look for the engine bundled with a VOICEVOX install (winget, installer, or zip).
# Override with: $env:VOICEVOX_ENGINE = "C:\path\to\vv-engine\run.exe"
$runExe = $env:VOICEVOX_ENGINE
if (-not $runExe -or -not (Test-Path $runExe)) {
    $roots = @(
        "$env:LOCALAPPDATA\Programs\VOICEVOX",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages",
        "$env:ProgramFiles\VOICEVOX"
    ) | Where-Object { $_ -and (Test-Path $_) }
    $found = $roots | ForEach-Object {
        Get-ChildItem -Path $_ -Filter "run.exe" -Recurse -ErrorAction SilentlyContinue
    } | Where-Object { $_.FullName -like "*vv-engine*" } | Select-Object -First 1
    if (-not $found) {
        Write-Error "VOICEVOX Engine (vv-engine\run.exe) not found. Install VOICEVOX or set `$env:VOICEVOX_ENGINE."
        exit 1
    }
    $runExe = $found.FullName
}
$enginePath = Split-Path $runExe

Write-Host "Starting VOICEVOX Engine (DirectML/GPU)..." -ForegroundColor Cyan
Start-Process -FilePath $runExe -ArgumentList "--host 127.0.0.1 --port $port --use_gpu" -WorkingDirectory $enginePath -WindowStyle Hidden

$maxRetries = 20
$started = $false
for ($i = 0; $i -lt $maxRetries; $i++) {
    Start-Sleep -Milliseconds 500
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:$port/version" -TimeoutSec 1 -ErrorAction Stop
        $started = $true
        break
    } catch {}
}

if ($started) {
    Write-Host "VOICEVOX Engine is ready (version: $res)" -ForegroundColor Green
} else {
    Write-Warning "Timed out waiting for VOICEVOX Engine. It may still be initializing."
}
