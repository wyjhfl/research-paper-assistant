param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"

$dockerExe = "docker"
$dockerPath = Get-Command docker -ErrorAction SilentlyContinue
if (-not $dockerPath) {
    $dockerExe = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
    if (-not (Test-Path $dockerExe)) {
        Write-Host "ERROR: docker not found in PATH or default location" -ForegroundColor Red
        exit 1
    }
}

if (-not $ConfirmRestore) {
    Write-Host "ERROR: Restore requires -ConfirmRestore flag. This operation will overwrite current storage." -ForegroundColor Red
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File scripts/restore_storage.ps1 -BackupFile <path> -ConfirmRestore" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $BackupFile)) {
    Write-Host "ERROR: Backup file not found: $BackupFile" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "ERROR: docker-compose.yml not found. Run from project root." -ForegroundColor Red
    exit 1
}

Write-Host "WARNING: This will overwrite current storage content!" -ForegroundColor Yellow
Write-Host "Restoring storage from: $BackupFile" -ForegroundColor Cyan

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$tempDir = Join-Path $env:TEMP "storage_restore_$timestamp"
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

Expand-Archive -Path $BackupFile -DestinationPath $tempDir -Force

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"

& $dockerExe compose exec -T backend sh -c "find /app/storage -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +" 2>&1
$cleanExit = $LASTEXITCODE

if ($cleanExit -ne 0 -and $cleanExit -ne $null) {
    $ErrorActionPreference = $prevEAP
    Write-Host "ERROR: Storage cleanup failed (exit code: $cleanExit). Aborting restore." -ForegroundColor Red
    if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
    exit 1
}

Get-ChildItem $tempDir | ForEach-Object {
    & $dockerExe compose cp $_.FullName "backend:/app/storage/" 2>&1
}

$cpExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $dockerExe compose exec -T backend test -d /app/storage 2>&1
$verifyExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($verifyExit -ne 0) {
    Write-Host "ERROR: /app/storage directory does not exist after restore" -ForegroundColor Red
    exit 1
}

if ($cpExit -ne 0 -and $cpExit -ne $null) {
    Write-Host "ERROR: Failed to restore storage to container" -ForegroundColor Red
    exit 1
}

Write-Host "Storage restore completed successfully." -ForegroundColor Green
