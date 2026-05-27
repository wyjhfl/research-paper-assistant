param(
    [Parameter(Mandatory=$true)]
    [string]$ManifestPath,
    [switch]$ConfirmRestore,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $DryRun -and -not $ConfirmRestore) {
    Write-Host "ERROR: Restore requires -ConfirmRestore flag. This operation will overwrite current data." -ForegroundColor Red
    Write-Host "Usage: powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath <path> -ConfirmRestore" -ForegroundColor Yellow
    Write-Host "  DryRun: powershell -ExecutionPolicy Bypass -File scripts/restore_all.ps1 -ManifestPath <path> -DryRun" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path $ManifestPath)) {
    Write-Host "ERROR: Manifest file not found" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path "docker-compose.yml")) {
    Write-Host "ERROR: docker-compose.yml not found. Run from project root." -ForegroundColor Red
    exit 1
}

$manifest = Get-Content $ManifestPath -Raw | ConvertFrom-Json
$manifestDir = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($ManifestPath))
$manifestFileName = [System.IO.Path]::GetFileName($ManifestPath)

if (-not $manifest.db_backup_file) {
    Write-Host "ERROR: Manifest is missing db_backup_file. Full restore requires database backup." -ForegroundColor Red
    exit 1
}

if (-not $manifest.storage_backup_file) {
    Write-Host "ERROR: Manifest is missing storage_backup_file. Full restore requires storage backup." -ForegroundColor Red
    exit 1
}

$dbFile = Join-Path (Join-Path $manifestDir "db") $manifest.db_backup_file
$storageFile = Join-Path (Join-Path $manifestDir "storage") $manifest.storage_backup_file
$dbBackupPresent = Test-Path $dbFile
$storageBackupPresent = Test-Path $storageFile

if ($DryRun) {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  [DRY RUN] Restore Validation" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  Backup timestamp: $($manifest.timestamp)" -ForegroundColor Cyan
    Write-Host "  App version: $($manifest.app_version)" -ForegroundColor Cyan
    Write-Host "  Embedding dimension: $($manifest.embedding_dimension)" -ForegroundColor Cyan
    Write-Host ""

    $drillOk = $true

    if ($dbBackupPresent) {
        Write-Host "  [OK] DB backup found: $($manifest.db_backup_file)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] DB backup missing: $($manifest.db_backup_file)" -ForegroundColor Red
        $drillOk = $false
    }

    if ($storageBackupPresent) {
        Write-Host "  [OK] Storage backup found: $($manifest.storage_backup_file)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Storage backup missing: $($manifest.storage_backup_file)" -ForegroundColor Red
        $drillOk = $false
    }

    if ($manifest.eval_backup_file) {
        $evalFile = Join-Path (Join-Path $manifestDir "evals") $manifest.eval_backup_file
        if (Test-Path $evalFile) {
            Write-Host "  [OK] Eval backup found: $($manifest.eval_backup_file)" -ForegroundColor Green
        } else {
            Write-Host "  [WARN] Eval backup missing: $($manifest.eval_backup_file) (skipping)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  [INFO] No eval backup in manifest (optional)" -ForegroundColor Cyan
    }

    if ($drillOk) {
        Write-Host "  [DRY RUN] Validation passed. No data was modified." -ForegroundColor Green
    } else {
        Write-Host "  [DRY RUN] Validation FAILED. Missing required backup files." -ForegroundColor Red
    }

    $drillTimestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
    $drillRecord = @{
        timestamp = $drillTimestamp + "Z"
        manifest_file = $manifestFileName
        dry_run = $true
        db_backup_present = $dbBackupPresent
        storage_backup_present = $storageBackupPresent
        ok = $drillOk
    }

    $drillDir = Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "artifacts") "backups"
    if (-not (Test-Path $drillDir)) {
        New-Item -ItemType Directory -Path $drillDir -Force | Out-Null
    }
    $drillFileName = "restore_drill_$drillTimestamp.json"
    $drillPath = Join-Path $drillDir $drillFileName
    $drillJson = $drillRecord | ConvertTo-Json -Depth 5
    $utf8NoBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($drillPath, $drillJson, $utf8NoBom)
    Write-Host "  Drill record: artifacts/backups/$drillFileName" -ForegroundColor Cyan

    if (-not $drillOk) {
        exit 1
    }
    exit 0
}

Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  WARNING: Full Restore" -ForegroundColor Yellow
Write-Host "  This will overwrite database, storage, and eval artifacts!" -ForegroundColor Yellow
Write-Host "  Backup timestamp: $($manifest.timestamp)" -ForegroundColor Yellow
Write-Host "  App version: $($manifest.app_version)" -ForegroundColor Yellow
Write-Host "  Embedding dimension: $($manifest.embedding_dimension)" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow

if (-not (Test-Path $dbFile)) {
    Write-Host "ERROR: DB backup file not found" -ForegroundColor Red
    exit 1
}
Write-Host "Restoring database from: $($manifest.db_backup_file)" -ForegroundColor Cyan
$restoreDbScript = Join-Path $PSScriptRoot "restore_postgres.ps1"
& $restoreDbScript -BackupFile $dbFile -ConfirmRestore
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
    Write-Host "ERROR: Database restore failed" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $storageFile)) {
    Write-Host "ERROR: Storage backup file not found" -ForegroundColor Red
    exit 1
}
Write-Host "Restoring storage from: $($manifest.storage_backup_file)" -ForegroundColor Cyan
$restoreStorageScript = Join-Path $PSScriptRoot "restore_storage.ps1"
& $restoreStorageScript -BackupFile $storageFile -ConfirmRestore
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne $null) {
    Write-Host "ERROR: Storage restore failed" -ForegroundColor Red
    exit 1
}

if ($manifest.eval_backup_file) {
    $evalFile = Join-Path (Join-Path $manifestDir "evals") $manifest.eval_backup_file
    if (Test-Path $evalFile) {
        Write-Host "Restoring eval artifacts from: $($manifest.eval_backup_file)" -ForegroundColor Cyan
        $evalDir = Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "artifacts") "evals"
        if (-not (Test-Path $evalDir)) {
            New-Item -ItemType Directory -Path $evalDir -Force | Out-Null
        }
        Expand-Archive -Path $evalFile -DestinationPath $evalDir -Force
        Write-Host "Eval artifacts restored" -ForegroundColor Green
    } else {
        Write-Host "WARN: Eval backup file not found: $($manifest.eval_backup_file) (skipping)" -ForegroundColor Yellow
    }
} else {
    Write-Host "No eval backup in manifest (optional)" -ForegroundColor Cyan
}

$drillTimestamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd_HHmmss")
$drillRecord = @{
    timestamp = $drillTimestamp + "Z"
    manifest_file = $manifestFileName
    dry_run = $false
    db_backup_present = $true
    storage_backup_present = $true
    ok = $true
}

$drillDir = Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "artifacts") "backups"
if (-not (Test-Path $drillDir)) {
    New-Item -ItemType Directory -Path $drillDir -Force | Out-Null
}
$drillFileName = "restore_drill_$drillTimestamp.json"
$drillPath = Join-Path $drillDir $drillFileName
$drillJson = $drillRecord | ConvertTo-Json -Depth 5
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($drillPath, $drillJson, $utf8NoBom)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Full Restore Completed" -ForegroundColor Green
Write-Host "  Drill record: artifacts/backups/$drillFileName" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
