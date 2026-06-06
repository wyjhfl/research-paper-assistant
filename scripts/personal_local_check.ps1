param(
    [switch]$RunModelSmoke,
    [string]$ApiBase = "http://localhost:8091",
    [string]$FrontendBase = "http://localhost:3000"
)

$ErrorActionPreference = "Stop"

function Test-PythonCandidate {
    param([string]$Exe, [string[]]$Args)
    $cmd = Get-Command $Exe -ErrorAction SilentlyContinue
    if (-not $cmd) { return $false }
    $prevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $null = & $Exe @($Args + @("--version")) 2>&1
        if ($LASTEXITCODE -eq 0) { return $true }
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

$projectRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
Set-Location $projectRoot

$python = Resolve-PythonCommand
$scriptArgs = @("scripts/personal_local_check.py", "--api-base", $ApiBase, "--frontend-base", $FrontendBase)
if ($RunModelSmoke) {
    $scriptArgs += "--run-model-smoke"
}

& $python.Exe @($python.Args + $scriptArgs)
exit $LASTEXITCODE
