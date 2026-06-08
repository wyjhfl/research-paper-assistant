param(
    [switch]$RunModelSmoke,
    [switch]$RunWorkflowSmoke,
    [switch]$WriteSmokeNote,
    [switch]$SkipBuild
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
powershell @checkArgs
exit $LASTEXITCODE
