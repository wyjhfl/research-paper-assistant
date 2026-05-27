param(
    [switch]$SkipProductionCheck
)

$ErrorActionPreference = "Stop"
$step = 0
$totalSteps = 4

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

if ($SkipProductionCheck) { $totalSteps-- }

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
    $proc = Start-Process -FilePath "docker" -ArgumentList "compose","exec","-T","backend","python","-m","alembic","current" -NoNewWindow -Wait -PassThru -RedirectStandardOutput (Join-Path $env:TEMP "qg_alembic_out.txt") -RedirectStandardError (Join-Path $env:TEMP "qg_alembic_err.txt")
    Get-Content (Join-Path $env:TEMP "qg_alembic_out.txt"), (Join-Path $env:TEMP "qg_alembic_err.txt") | Write-Host
    if ($proc.ExitCode -ne 0) { throw "Alembic check failed (exit $($proc.ExitCode))" }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  QUICK GATE PASSED" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
