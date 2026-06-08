param(
    [switch]$RunModelSmoke,
    [switch]$RunWorkflowSmoke,
    [switch]$WriteSmokeNote,
    [string]$ApiBase = "http://localhost:8091",
    [string]$FrontendBase = "http://localhost:3000"
)

$ErrorActionPreference = "Stop"

function Test-PythonCandidate {
    param([string]$Exe, [string[]]$Args)
    if (-not (Test-Path -LiteralPath $Exe -PathType Leaf)) {
        $cmd = Get-Command $Exe -ErrorAction SilentlyContinue
        if (-not $cmd) { return $false }
    }
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

function Get-PythonCandidateCommands {
    $candidates = @()
    if ($env:PYTHON) {
        $candidates += [PSCustomObject]@{ Exe = $env:PYTHON; Args = @() }
    }
    $candidates += [PSCustomObject]@{ Exe = "python"; Args = @() }
    $candidates += [PSCustomObject]@{ Exe = "py"; Args = @("-3") }

    $commonPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python*\python.exe"),
        (Join-Path $env:ProgramFiles "Python*\python.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Python*\python.exe")
    )
    foreach ($pattern in $commonPaths) {
        Resolve-Path -Path $pattern -ErrorAction SilentlyContinue | ForEach-Object {
            $candidates += [PSCustomObject]@{ Exe = $_.Path; Args = @() }
        }
    }

    Get-PSDrive -PSProvider FileSystem | ForEach-Object {
        $driveRoot = $_.Root
        Get-ChildItem -LiteralPath $driveRoot -Directory -Filter "codex*" -ErrorAction SilentlyContinue | ForEach-Object {
            $toolsDir = Join-Path $_.FullName "tools"
            Get-ChildItem -LiteralPath $toolsDir -Directory -Filter "Python*" -ErrorAction SilentlyContinue | ForEach-Object {
                $candidate = Join-Path $_.FullName "python.exe"
                if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                    $candidates += [PSCustomObject]@{ Exe = $candidate; Args = @() }
                }
            }
        }
    }
    return $candidates
}

function Resolve-PythonCommand {
    foreach ($candidate in Get-PythonCandidateCommands) {
        if (Test-PythonCandidate -Exe $candidate.Exe -Args $candidate.Args) {
            return $candidate
        }
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
if ($RunWorkflowSmoke) {
    $scriptArgs += "--run-workflow-smoke"
}
if ($WriteSmokeNote) {
    $scriptArgs += "--write-smoke-note"
}

& $python.Exe @($python.Args + $scriptArgs)
exit $LASTEXITCODE
