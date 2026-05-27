param(
    [switch]$SkipBackendTests,
    [switch]$SkipFrontendBuild,
    [switch]$SkipE2E,
    [switch]$SkipProductionCheck,
    [string]$ManifestPath
)

$ErrorActionPreference = "Stop"
$step = 0
$totalSteps = 7
if ($SkipBackendTests) { $totalSteps-- }
if ($SkipFrontendBuild) { $totalSteps-- }
if ($SkipE2E) { $totalSteps-- }
if ($SkipProductionCheck) { $totalSteps-- }
if ($ManifestPath) { $totalSteps += 2 }

function Invoke-Step {
    param([string]$Name, [scriptblock]$Action)
    $script:step++
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  [$script:step/$totalSteps] $Name" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    try {
        & $Action
        Write-Host "$Name passed" -ForegroundColor Green
    } catch {
        Write-Host "ERROR: $Name failed" -ForegroundColor Red
        Write-Host $_.Exception.Message -ForegroundColor Red
        exit 1
    }
}

$projectRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
Set-Location $projectRoot

Invoke-Step "Documentation secret scan" {
    $result = & python scripts/check_docs_secrets.py 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Secret scan failed" }
    Write-Host $result
}

Invoke-Step "Frontend mojibake scan" {
    $result = & python scripts/check_frontend_mojibake.py 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Mojibake scan failed" }
    Write-Host $result
}

if (-not $SkipProductionCheck) {
    Invoke-Step "Production check" {
        $result = & docker compose exec -T backend python scripts/production_check.py 2>&1
        Write-Host $result
        if ($LASTEXITCODE -ne 0) { throw "Production check failed (exit $LASTEXITCODE)" }
    }
}

Invoke-Step "Alembic current" {
    $proc = Start-Process -FilePath "docker" -ArgumentList "compose","exec","-T","backend","python","-m","alembic","current" -NoNewWindow -Wait -PassThru -RedirectStandardOutput (Join-Path $env:TEMP "rc_alembic_out.txt") -RedirectStandardError (Join-Path $env:TEMP "rc_alembic_err.txt")
    Get-Content (Join-Path $env:TEMP "rc_alembic_out.txt"), (Join-Path $env:TEMP "rc_alembic_err.txt") | Write-Host
    if ($proc.ExitCode -ne 0) { throw "Alembic check failed (exit $($proc.ExitCode))" }
}

if (-not $SkipBackendTests) {
    Invoke-Step "Backend tests (pytest)" {
        $result = & docker compose exec -T backend python -m pytest tests/ -q 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Backend tests failed" }
        Write-Host $result
    }
}

if (-not $SkipFrontendBuild) {
    Invoke-Step "Frontend build" {
        try {
            Push-Location "apps/web"
            $result = & npm run build 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) { throw "Frontend build failed" }
            Write-Host $result
        } finally {
            Pop-Location
        }
    }
}

if (-not $SkipE2E) {
    Invoke-Step "E2E tests (Playwright)" {
        try {
            Push-Location "apps/web"
            $result = & npx playwright test 2>&1 | Out-String
            if ($LASTEXITCODE -ne 0) { throw "E2E tests failed" }
            Write-Host $result
        } finally {
            Pop-Location
        }
    }
}

if ($ManifestPath) {
    if ([System.IO.Path]::IsPathRooted($ManifestPath)) {
        Write-Host "ERROR: ManifestPath must be project-relative" -ForegroundColor Red
        exit 1
    }
    $resolvedManifest = Join-Path $projectRoot $ManifestPath
    if (-not (Test-Path $resolvedManifest)) {
        Write-Host "ERROR: Manifest file not found: $ManifestPath" -ForegroundColor Red
        exit 1
    }

    Invoke-Step "Validate backup manifest" {
        $result = & docker compose exec -T backend python scripts/validate_backup_manifest.py $ManifestPath 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Manifest validation failed" }
        Write-Host $result
    }

    Invoke-Step "Restore dry-run" {
        $result = & powershell -ExecutionPolicy Bypass -File "scripts\restore_all.ps1" -ManifestPath $ManifestPath -DryRun 2>&1
        if ($LASTEXITCODE -ne 0) { throw "Restore dry-run failed" }
        Write-Host $result
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  ALL RC GATE CHECKS PASSED" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
