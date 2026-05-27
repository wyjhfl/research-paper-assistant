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
    $OutputDir = Join-Path (Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "artifacts") "backups") "db"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

$backupFile = Join-Path $OutputDir "db_backup_$timestamp.sql"

Write-Host "Backing up PostgreSQL database..." -ForegroundColor Cyan

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $dockerExe compose exec -T postgres pg_dump -U postgres research_assistant > $backupFile 2>&1
$exitCode = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($exitCode -ne 0 -and $exitCode -ne $null) {
    Write-Host "ERROR: pg_dump failed (exit code: $exitCode)" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $backupFile) -or (Get-Item $backupFile).Length -eq 0) {
    Write-Host "ERROR: Backup file is empty or missing" -ForegroundColor Red
    exit 1
}

$sizeKB = [math]::Round((Get-Item $backupFile).Length / 1KB, 1)
Write-Host "Database backup completed: $backupFile ($sizeKB KB)" -ForegroundColor Green
Write-Output $backupFile
