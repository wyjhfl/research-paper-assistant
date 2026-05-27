param(
    [switch]$SkipDockerBuild,
    [switch]$RunRealModelEval,
    [switch]$SkipE2E,
    [switch]$RunProductionCheck,
    [switch]$RunMigrationCheck,
    [switch]$RunBackupCheck
)

$ErrorActionPreference = "Stop"

$SENSITIVE_PATTERNS = @(
    "API_KEY", "SECRET", "TOKEN", "AUTHORIZATION",
    "DATABASE_URL", "password", "sk-",
    "postgresql\+asyncpg://"
)

function Write-Step {
    param([string]$Label)
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "  $Label" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
}

function Write-Fail {
    param([string]$Msg)
    Write-Host "  FAILED: $Msg" -ForegroundColor Red
}

function Write-Ok {
    param([string]$Msg)
    Write-Host "  $Msg" -ForegroundColor Green
}

function Resolve-PythonCommand {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) {
        return [PSCustomObject]@{ Exe = "python"; Args = @() }
    }
    $py3 = Get-Command py -ErrorAction SilentlyContinue
    if ($py3) {
        return [PSCustomObject]@{ Exe = "py"; Args = @("-3") }
    }
    Write-Host "ERROR: Python was not found. Install Python or add it to PATH." -ForegroundColor Red
    exit 1
}

function Invoke-PythonSafeCommand {
    param(
        [string[]]$PythonArgs,
        [string]$ErrorMessage
    )
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $allArgs = $Python.Args + $PythonArgs
    $output = & $Python.Exe @allArgs 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP

    foreach ($line in $output) {
        $lineStr = $line.ToString()
        $skip = $false
        foreach ($pat in $SENSITIVE_PATTERNS) {
            if ($lineStr -match $pat) {
                $skip = $true
                break
            }
        }
        if (-not $skip) {
            Write-Host "  $lineStr"
        }
    }

    if ($exitCode -ne 0) {
        Write-Fail "$ErrorMessage (exit code: $exitCode)"
        exit 1
    }
}

function Invoke-SafeCommand {
    param(
        [scriptblock]$Command,
        [string]$ErrorMessage
    )
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $Command 2>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP

    foreach ($line in $output) {
        $lineStr = $line.ToString()
        $skip = $false
        foreach ($pat in $SENSITIVE_PATTERNS) {
            if ($lineStr -match $pat) {
                $skip = $true
                break
            }
        }
        if (-not $skip) {
            Write-Host "  $lineStr"
        }
    }

    if ($exitCode -ne 0) {
        Write-Fail "$ErrorMessage (exit code: $exitCode)"
        exit 1
    }
}

function Test-DockerAvailable {
    $dockerExe = "docker"
    $dockerPath = Get-Command docker -ErrorAction SilentlyContinue
    if (-not $dockerPath) {
        $dockerExe = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
        if (-not (Test-Path $dockerExe)) { return $false }
    }
    try {
        $null = & $dockerExe info 2>&1
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

if (-not (Test-Path "docker-compose.yml")) {
    Write-Fail "docker-compose.yml not found in current directory. Please run this script from the project root."
    exit 1
}

$Python = Resolve-PythonCommand

$totalSteps = 0
if (-not $SkipDockerBuild) { $totalSteps++ }
$totalSteps++  # doc secret scan
$totalSteps++  # doc secret scan tests
$totalSteps++  # frontend mojibake scan
$totalSteps++  # smoke check
if ($RunMigrationCheck) { $totalSteps++ }
if ($RunProductionCheck) { $totalSteps++ }
$totalSteps++  # pytest
$totalSteps++  # frontend build
if (-not $SkipE2E) { $totalSteps++ }
if ($RunBackupCheck) { $totalSteps++ }
if ($RunRealModelEval) { $totalSteps += 2 }

$step = 0

if (-not $SkipDockerBuild) {
    $step++
    Write-Step "[$step/$totalSteps] Starting Docker services"
    if (-not (Test-DockerAvailable)) {
        Write-Fail "Docker Desktop not running or Docker daemon not accessible. Please start Docker Desktop and try again."
        exit 1
    }
    Invoke-SafeCommand -Command { docker compose up -d --build } -ErrorMessage "Docker compose failed"
    Write-Ok "Docker services started"
} else {
    if (-not (Test-DockerAvailable)) {
        Write-Fail "Docker Desktop not running or Docker daemon not accessible. Please start Docker Desktop and try again."
        exit 1
    }
    Write-Host ""
    Write-Host "  [SKIP] Docker build (-SkipDockerBuild)" -ForegroundColor Yellow
}

$step++
Write-Step "[$step/$totalSteps] Documentation secret scan"
Invoke-PythonSafeCommand -PythonArgs @("scripts/check_docs_secrets.py") -ErrorMessage "Documentation secret scan failed"
Write-Ok "Doc secret scan passed"

$step++
Write-Step "[$step/$totalSteps] Documentation secret scan tests"
Invoke-PythonSafeCommand -PythonArgs @("-m", "pytest", "tests/test_check_docs_secrets.py", "-q") -ErrorMessage "Documentation secret scan tests failed"
Write-Ok "Doc secret scan tests passed"

$step++
Write-Step "[$step/$totalSteps] Frontend mojibake scan"
Invoke-PythonSafeCommand -PythonArgs @("scripts/check_frontend_mojibake.py") -ErrorMessage "Frontend mojibake scan failed"
Write-Ok "Frontend mojibake scan passed"

$step++
Write-Step "[$step/$totalSteps] Backend smoke check"
Invoke-SafeCommand -Command { docker compose exec -T backend python scripts/smoke_check.py } -ErrorMessage "Smoke check failed"
Write-Ok "Smoke check passed"

if ($RunMigrationCheck) {
    $step++
    Write-Step "[$step/$totalSteps] Migration check (Alembic)"
    Write-Host "  Checking Alembic current version..." -ForegroundColor Cyan
    Invoke-SafeCommand -Command { docker compose exec -T backend python -m alembic current } -ErrorMessage "Alembic current check failed"
    Write-Host "  Checking Alembic head version..." -ForegroundColor Cyan
    Invoke-SafeCommand -Command { docker compose exec -T backend python -m alembic heads } -ErrorMessage "Alembic heads check failed"
    Write-Ok "Migration check passed"
}

if ($RunProductionCheck) {
    $step++
    Write-Step "[$step/$totalSteps] Production check"
    Invoke-SafeCommand -Command { docker compose exec -T backend python scripts/production_check.py } -ErrorMessage "Production check failed"
    Write-Ok "Production check passed"
}

$step++
Write-Step "[$step/$totalSteps] Backend tests (pytest)"
Invoke-SafeCommand -Command { docker compose exec -T backend python -m pytest tests/ -q } -ErrorMessage "Backend tests failed"
Write-Ok "Backend tests passed"

$step++
Write-Step "[$step/$totalSteps] Frontend build"
try {
    Push-Location "apps/web"
    Invoke-SafeCommand -Command { npm run build } -ErrorMessage "Frontend build failed"
    Write-Ok "Frontend build passed"
} finally {
    Pop-Location
}

if (-not $SkipE2E) {
    $step++
    Write-Step "[$step/$totalSteps] E2E tests (Playwright)"
    try {
        Push-Location "apps/web"
        Remove-Item -Recurse -Force ".next" -ErrorAction SilentlyContinue
        Remove-Item Env:\E2E_BASE_URL -ErrorAction SilentlyContinue
        Invoke-SafeCommand -Command { npx playwright test } -ErrorMessage "E2E tests failed"
        Write-Ok "E2E tests passed"
    } finally {
        Pop-Location
    }
} else {
    Write-Host ""
    Write-Host "  [SKIP] E2E tests (-SkipE2E)" -ForegroundColor Yellow
}

if ($RunBackupCheck) {
    $step++
    Write-Step "[$step/$totalSteps] Backup check"
    Write-Host "  Running backup_all.ps1 (no restore)..." -ForegroundColor Cyan
    Invoke-SafeCommand -Command { powershell -ExecutionPolicy Bypass -File scripts/backup_all.ps1 } -ErrorMessage "Backup check failed"
    Write-Ok "Backup check passed"
}

if ($RunRealModelEval) {
    $step++
    Write-Step "[$step/$totalSteps] Model smoke check (real model)"
    Write-Host "  This step requires REAL_MODEL_REQUIRED=true and real LLM/Embedding providers." -ForegroundColor Yellow
    Invoke-SafeCommand -Command { docker compose exec -T backend python scripts/model_smoke_check.py } -ErrorMessage "Model smoke check failed: real model providers not configured or unreachable"
    Write-Ok "Model smoke check passed"

    $step++
    Write-Step "[$step/$totalSteps] Real model evaluation"
    Invoke-SafeCommand -Command { docker compose exec -T backend python scripts/eval_real_model.py } -ErrorMessage "Real model evaluation failed: real model providers not configured or unreachable"
    Write-Ok "Real model evaluation passed"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  ALL VERIFICATION CHECKS PASSED" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
exit 0
