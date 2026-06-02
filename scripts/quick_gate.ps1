param(
    [switch]$SkipProductionCheck
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

function Test-PythonCandidate {
    param([string]$Exe, [string[]]$Args)
    $cmd = Get-Command $Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { return $false }
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $null = & $Exe @($Args + @("--version")) 2>&1
        if ($LASTEXITCODE -eq 0) { return $true }
    } catch {
        return $false
    } finally {
        $ErrorActionPreference = $prevEAP
    }
    return $false
}

function Resolve-PythonCommand {
    if (Test-PythonCandidate -Exe "python" -Args @()) {
        return [PSCustomObject]@{ Exe = "python"; Args = @() }
    }
    if (Test-PythonCandidate -Exe "py" -Args @("-3")) {
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

$projectRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
Set-Location $projectRoot

$Python = Resolve-PythonCommand

$step = 0
$totalSteps = 4
if ($SkipProductionCheck) { $totalSteps-- }

$step++
Write-Step "[$step/$totalSteps] Documentation secret scan"
Invoke-PythonSafeCommand -PythonArgs @("scripts/check_docs_secrets.py") -ErrorMessage "Secret scan failed"
Write-Ok "Documentation secret scan passed"

$step++
Write-Step "[$step/$totalSteps] Frontend mojibake scan"
Invoke-PythonSafeCommand -PythonArgs @("scripts/check_frontend_mojibake.py") -ErrorMessage "Mojibake scan failed"
Write-Ok "Frontend mojibake scan passed"

if (-not $SkipProductionCheck) {
    $step++
    Write-Step "[$step/$totalSteps] Production check"
    Invoke-SafeCommand -Command { docker compose exec -T backend python scripts/production_check.py } -ErrorMessage "Production check failed"
    Write-Ok "Production check passed"
}

$step++
Write-Step "[$step/$totalSteps] Alembic current"
$alembicOutFile = Join-Path $env:TEMP "qg_alembic_out.txt"
$alembicErrFile = Join-Path $env:TEMP "qg_alembic_err.txt"
$proc = Start-Process -FilePath "docker" -ArgumentList "compose","exec","-T","backend","python","-m","alembic","current" -NoNewWindow -Wait -PassThru -RedirectStandardOutput $alembicOutFile -RedirectStandardError $alembicErrFile
foreach ($file in @($alembicOutFile, $alembicErrFile)) {
    if (Test-Path $file) {
        foreach ($line in Get-Content $file) {
            $skip = $false
            foreach ($pat in $SENSITIVE_PATTERNS) {
                if ($line -match $pat) { $skip = $true; break }
            }
            if (-not $skip) { Write-Host "  $line" }
        }
    }
}
if ($proc.ExitCode -ne 0) {
    Write-Fail "Alembic check failed (exit code: $($proc.ExitCode))"
    exit 1
}
Write-Ok "Alembic current passed"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  QUICK GATE PASSED" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
