param(
    [string]$OutputDir = "",
    [switch]$DryRun
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
    $OutputDir = Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "artifacts") "backups"
}
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Full Backup - $timestamp UTC" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if ($DryRun) {
    Write-Host "  [DRY RUN] Would execute the following steps:" -ForegroundColor Yellow
    Write-Host "  1. backup_postgres.ps1 -> artifacts/backups/db/" -ForegroundColor Yellow
    Write-Host "  2. backup_storage.ps1 -> artifacts/backups/storage/" -ForegroundColor Yellow
    Write-Host "  3. Eval artifacts backup (if exists)" -ForegroundColor Yellow
    Write-Host "  4. Generate backup_manifest_*.json" -ForegroundColor Yellow
    exit 0
}

$dbScript = Join-Path $PSScriptRoot "backup_postgres.ps1"
$storageScript = Join-Path $PSScriptRoot "backup_storage.ps1"

$dbOutputDir = Join-Path $OutputDir "db"
$dbBackupFile = ""
$dbBackupOutput = & $dbScript -OutputDir $dbOutputDir 2>&1
$dbExitCode = $LASTEXITCODE
if ($dbBackupOutput) {
    $dbBackupFile = ($dbBackupOutput | Where-Object { $_ -is [string] -or $_ -is [System.Management.Automation.PSObject] } | Select-Object -Last 1).ToString().Trim()
}
if ($dbExitCode -ne 0 -and $dbExitCode -ne $null) {
    Write-Host "ERROR: Database backup failed" -ForegroundColor Red
    exit 1
}
if (-not $dbBackupFile -or -not (Test-Path $dbBackupFile)) {
    Write-Host "ERROR: Database backup file not found at reported path: $dbBackupFile" -ForegroundColor Red
    exit 1
}

$storageOutputDir = Join-Path $OutputDir "storage"
$storageBackupFile = ""
$storageBackupOutput = & $storageScript -OutputDir $storageOutputDir 2>&1
$storageExitCode = $LASTEXITCODE
if ($storageBackupOutput) {
    $storageBackupFile = ($storageBackupOutput | Where-Object { $_ -is [string] -or $_ -is [System.Management.Automation.PSObject] } | Select-Object -Last 1).ToString().Trim()
}
if ($storageExitCode -ne 0 -and $storageExitCode -ne $null) {
    Write-Host "ERROR: Storage backup failed" -ForegroundColor Red
    exit 1
}
if ($storageBackupFile -and -not (Test-Path $storageBackupFile)) {
    Write-Host "ERROR: Storage backup file not found at reported path: $storageBackupFile" -ForegroundColor Red
    exit 1
}
if (-not $storageBackupFile) {
    Write-Host "ERROR: Storage backup did not produce a file. Cannot generate manifest without storage backup." -ForegroundColor Red
    exit 1
}

$evalDir = Join-Path (Join-Path (Join-Path $PSScriptRoot "..") "artifacts") "evals"
$evalBackupFile = ""
if (Test-Path $evalDir) {
    $evalBackupDir = Join-Path $OutputDir "evals"
    if (-not (Test-Path $evalBackupDir)) {
        New-Item -ItemType Directory -Path $evalBackupDir -Force | Out-Null
    }
    $evalBackupFile = Join-Path $evalBackupDir "eval_backup_$timestamp.zip"
    Compress-Archive -Path "$evalDir\*" -DestinationPath $evalBackupFile -Force
    Write-Host "Eval artifacts backup completed" -ForegroundColor Green
} else {
    Write-Host "No eval artifacts found, skipping" -ForegroundColor Yellow
}

$appVersion = "unknown"
$embeddingDimension = $null

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$versionOutput = & $dockerExe compose exec -T backend python -c "from app.config import settings; print(settings.APP_VERSION)" 2>&1
$versionExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($versionExit -eq 0 -and $versionOutput) {
    $parsed = ($versionOutput | Select-Object -Last 1).Trim()
    if ($parsed -and $parsed -notmatch "error|Error|ERROR|traceback|Traceback") {
        $appVersion = $parsed
    } else {
        Write-Host "WARN: Could not determine app_version from container" -ForegroundColor Yellow
    }
} else {
    Write-Host "WARN: Could not query app_version from container" -ForegroundColor Yellow
}

$prevEAP = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$dimOutput = & $dockerExe compose exec -T backend python -c "from app.config import settings; print(settings.EMBEDDING_DIMENSION)" 2>&1
$dimExit = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

if ($dimExit -eq 0 -and $dimOutput) {
    $parsed = ($dimOutput | Select-Object -Last 1).Trim()
    if ($parsed -match '^\d+$') {
        $embeddingDimension = [int]$parsed
    } else {
        Write-Host "WARN: Could not determine embedding_dimension from container" -ForegroundColor Yellow
    }
} else {
    Write-Host "WARN: Could not query embedding_dimension from container" -ForegroundColor Yellow
}

$dbRelative = ""
if ($dbBackupFile -and (Test-Path $dbBackupFile)) {
    $dbRelative = [System.IO.Path]::GetFileName($dbBackupFile)
}
if (-not $dbRelative) {
    Write-Host "ERROR: Cannot generate manifest: db_backup_file is empty" -ForegroundColor Red
    exit 1
}

$storageRelative = ""
if ($storageBackupFile -and (Test-Path $storageBackupFile)) {
    $storageRelative = [System.IO.Path]::GetFileName($storageBackupFile)
}
if (-not $storageRelative) {
    Write-Host "ERROR: Cannot generate manifest: storage_backup_file is empty" -ForegroundColor Red
    exit 1
}

$evalRelative = ""
if ($evalBackupFile -and (Test-Path $evalBackupFile)) {
    $evalRelative = [System.IO.Path]::GetFileName($evalBackupFile)
}

$manifest = @{
    timestamp = $timestamp + "Z"
    db_backup_file = $dbRelative
    storage_backup_file = $storageRelative
    eval_backup_file = $evalRelative
    app_version = $appVersion
    embedding_dimension = $embeddingDimension
}

$manifestPath = Join-Path $OutputDir "backup_manifest_$timestamp.json"
$manifestJson = $manifest | ConvertTo-Json -Depth 5
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($manifestPath, $manifestJson, $utf8NoBom)

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Full Backup Completed" -ForegroundColor Green
Write-Host "  Manifest: $manifestPath" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host $manifestPath
