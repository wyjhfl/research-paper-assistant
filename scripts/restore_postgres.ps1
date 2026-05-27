param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile,
    [switch]$ConfirmRestore
)

$ErrorActionPreference = "Stop"

if (-not $ConfirmRestore) {
    Write-Host "ERROR: Restore requires -ConfirmRestore flag. This operation will overwrite the current database." -ForegroundColor Red
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File scripts/restore_postgres.ps1 -BackupFile <path> -ConfirmRestore" -ForegroundColor Yellow
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

Write-Host "WARNING: This will overwrite the current database!" -ForegroundColor Yellow
Write-Host "Restoring PostgreSQL from: $BackupFile" -ForegroundColor Cyan

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"

$dropOutput = docker compose exec -T postgres psql -U postgres -c "DROP DATABASE IF EXISTS research_assistant" 2>&1
$dropExit = $LASTEXITCODE

$createOutput = docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE research_assistant" 2>&1
$createExit = $LASTEXITCODE

$ErrorActionPreference = $prevEAP

if ($dropExit -ne 0 -or $createExit -ne 0) {
    Write-Host "ERROR: Failed to recreate database" -ForegroundColor Red
    exit 1
}

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"

$sqlContent = Get-Content $BackupFile -Raw
$sqlContent | docker compose exec -T postgres psql -U postgres -d research_assistant 2>&1
$restoreExit = $LASTEXITCODE

$ErrorActionPreference = $prevEAP

if ($restoreExit -ne 0) {
    Write-Host "ERROR: Database restore failed (exit code: $restoreExit)" -ForegroundColor Red
    exit 1
}

Write-Host "Database restore completed successfully." -ForegroundColor Green
