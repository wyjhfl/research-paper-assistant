param(
    [string]$OutputDir = ""
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

if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "ERROR: docker-compose.yml not found. Run from project root." -ForegroundColor Red
    exit 1
}

$timestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")

if (-not $OutputDir) {
    $OutputDir = Join-Path (Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "artifacts") "backups") "storage"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$backupFile = Join-Path $OutputDir "storage_backup_$timestamp.zip"

Write-Host "Backing up storage volume..." -ForegroundColor Cyan

$tempDir = Join-Path $env:TEMP "storage_backup_$timestamp"
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $dockerExe compose cp backend:/app/storage/. $tempDir 2>&1
$cpExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($cpExit -ne 0 -and $cpExit -ne $null) {
    $storageEmpty = & $dockerExe compose exec -T backend sh -c "ls -A /app/storage 2>/dev/null | wc -l" 2>&1
    $storageCount = ($storageEmpty | Select-Object -Last 1).ToString().Trim()
    if ($storageCount -eq "0") {
        Write-Host "Storage directory is empty, creating empty backup" -ForegroundColor Yellow
    } else {
        Write-Host "ERROR: Failed to copy storage from container (exit code: $cpExit)" -ForegroundColor Red
        if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
        exit 1
    }
}

Get-ChildItem $tempDir -Recurse -Include "*.log","__pycache__",".pytest_cache" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$items = Get-ChildItem $tempDir
if ($items.Count -eq 0) {
    New-Item -ItemType File -Path (Join-Path $tempDir ".empty") -Force | Out-Null
}

Compress-Archive -Path "$tempDir\*" -DestinationPath $backupFile -Force

if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }

if (-not (Test-Path $backupFile) -or (Get-Item $backupFile).Length -eq 0) {
    Write-Host "ERROR: Storage backup file is empty or missing" -ForegroundColor Red
    exit 1
}

$sizeKB = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
Write-Host "Storage backup completed: $backupFile ($sizeKB KB)" -ForegroundColor Green
Write-Output $backupFile
