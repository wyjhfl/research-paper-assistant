param(
    [switch]$RunModelSmoke,
    [switch]$RunWorkflowSmoke,
    [switch]$WriteSmokeNote,
    [switch]$SkipBuild,
    [int]$CheckRetries = 6,
    [int]$RetryDelaySeconds = 5
)

$ErrorActionPreference = "Stop"

$projectRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
Set-Location $projectRoot

Write-Host "Starting personal local Docker services..." -ForegroundColor Cyan
if ($SkipBuild) {
    docker compose up -d
} else {
    docker compose up -d --build
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: docker compose up failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

$checkArgs = @(
    "-ExecutionPolicy",
    "Bypass",
    "-File",
    "scripts\personal_local_check.ps1"
)
if ($RunModelSmoke) {
    $checkArgs += "-RunModelSmoke"
}
if ($RunWorkflowSmoke) {
    $checkArgs += "-RunWorkflowSmoke"
}
if ($WriteSmokeNote) {
    $checkArgs += "-WriteSmokeNote"
}

Write-Host "Running personal local validation..." -ForegroundColor Cyan
$attempt = 0
while ($attempt -lt $CheckRetries) {
    $attempt += 1
    Write-Host "Validation attempt $attempt/$CheckRetries..." -ForegroundColor Cyan
    powershell @checkArgs
    $checkExitCode = $LASTEXITCODE
    if ($checkExitCode -eq 0) {
        Write-Host "Personal local validation passed." -ForegroundColor Green
        exit 0
    }
    if ($attempt -lt $CheckRetries) {
        Write-Host "Validation failed; waiting before retry..." -ForegroundColor Yellow
        Start-Sleep -Seconds $RetryDelaySeconds
    }
}

Write-Host "ERROR: personal local validation failed after $CheckRetries attempts." -ForegroundColor Red
exit $checkExitCode
