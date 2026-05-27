param()

$ErrorActionPreference = "Continue"
$step = 0
$totalSteps = 7
$failCount = 0
$warnCount = 0

function Invoke-Check {
    param([string]$Name, [scriptblock]$Action, [bool]$Critical = $true)
    $script:step++
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  [$script:step/$totalSteps] $Name" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    try {
        $result = & $Action
        if ($LASTEXITCODE -ne 0 -and $Critical) {
            Write-Host "FAIL: $Name" -ForegroundColor Red
            $script:failCount++
        } elseif ($LASTEXITCODE -ne 0 -and -not $Critical) {
            Write-Host "WARN: $Name" -ForegroundColor Yellow
            $script:warnCount++
        } else {
            Write-Host "PASS: $Name" -ForegroundColor Green
        }
        if ($result) { Write-Host $result }
    } catch {
        if ($Critical) {
            Write-Host "FAIL: $Name - $($_.Exception.Message)" -ForegroundColor Red
            $script:failCount++
        } else {
            Write-Host "WARN: $Name - $($_.Exception.Message)" -ForegroundColor Yellow
            $script:warnCount++
        }
    }
}

$projectRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
Set-Location $projectRoot

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Operations Health Check" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White

Invoke-Check "Docker services" {
    docker compose ps 2>&1 | ForEach-Object { $_.ToString() }
    if ($LASTEXITCODE -ne 0) { throw "docker compose ps failed" }
}

Invoke-Check "Backend /health" {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8091/health" -TimeoutSec 10 -ErrorAction Stop
        "status: $($resp.status), version: $($resp.version), database: $($resp.database)"
    } catch {
        throw "health endpoint unreachable"
    }
}

Invoke-Check "Backend /health/ready" {
    try {
        $resp = Invoke-RestMethod -Uri "http://localhost:8091/health/ready" -TimeoutSec 10 -ErrorAction Stop
        "ready: $($resp.ready), alembic_current: $($resp.alembic_current)"
        if ($resp.ready -ne $true) { throw "not ready" }
    } catch {
        throw "ready endpoint unreachable or not ready"
    }
}

Invoke-Check "Job worker health" {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8091/jobs/worker/health" -TimeoutSec 10 -ErrorAction Stop
        "worker_enabled: $($health.worker_enabled), stale_running_count: $($health.stale_running_count), pending_count: $($health.pending_count), failed_count: $($health.failed_count)"
        if ($health.stale_running_count -gt 0) {
            Write-Host "WARN: stale_running_count > 0" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "WARN: worker health requires authenticated session; skipped in read-only ops_check" -ForegroundColor Yellow
        $script:warnCount++
    }
} $false

Invoke-Check "Production check" {
    $result = docker compose exec -T backend python scripts/production_check.py 2>&1 | ForEach-Object { $_.ToString() }
    $result
    if ($LASTEXITCODE -ne 0) { throw "production_check FAIL" }
}

Invoke-Check "Alembic current" {
    $result = docker compose exec -T backend python -m alembic current 2>&1 | ForEach-Object { $_.ToString() }
    $result
    if ($LASTEXITCODE -ne 0) { throw "alembic current failed" }
}

Invoke-Check "Storage audit" {
    $result = docker compose exec -T backend python scripts/storage_audit.py 2>&1 | ForEach-Object { $_.ToString() }
    $result
    if ($LASTEXITCODE -ne 0) { throw "storage_audit failed" }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor White
Write-Host "  Summary" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor White
Write-Host "  PASS: $($totalSteps - $script:failCount - $script:warnCount)" -ForegroundColor Green
if ($script:warnCount -gt 0) { Write-Host "  WARN: $($script:warnCount)" -ForegroundColor Yellow }
if ($script:failCount -gt 0) { Write-Host "  FAIL: $($script:failCount)" -ForegroundColor Red }

if ($script:failCount -gt 0) {
    Write-Host ""
    Write-Host "RESULT: FAIL" -ForegroundColor Red
    exit 1
} elseif ($script:warnCount -gt 0) {
    Write-Host ""
    Write-Host "RESULT: PASS WITH WARNINGS" -ForegroundColor Yellow
    exit 0
} else {
    Write-Host ""
    Write-Host "RESULT: ALL CHECKS PASSED" -ForegroundColor Green
    exit 0
}
