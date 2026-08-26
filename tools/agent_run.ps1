param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidatePattern('^[A-Za-z_][A-Za-z0-9_.]*$')]
    [string]$Module,

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$ModuleArguments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$currentRoot = [System.IO.Path]::GetFullPath((Get-Location).Path)
if ($currentRoot -ne $repoRoot) {
    throw "agent_run.ps1 must be executed from repository root: $repoRoot"
}

. (Join-Path $PSScriptRoot 'agent_local.ps1')
$localPaths = Get-AgentLocalPaths -RepositoryRoot $repoRoot

if (-not $localPaths.PythonExe -or -not (Test-Path -LiteralPath $localPaths.PythonExe -PathType Leaf)) {
    throw "PYTHON_EXE is missing or invalid in $($localPaths.ConfigPath)"
}

$previousAdbPath = $env:ADB_PATH
$previousScrcpyServerPath = $env:SCRCPY_SERVER_PATH
try {
    if ($localPaths.AdbExe) {
        $env:ADB_PATH = $localPaths.AdbExe
    }
    if ($localPaths.ScrcpyServerPath) {
        $env:SCRCPY_SERVER_PATH = $localPaths.ScrcpyServerPath
    }

    & $localPaths.PythonExe -m $Module @ModuleArguments
    $childExitCode = $LASTEXITCODE
}
finally {
    $env:ADB_PATH = $previousAdbPath
    $env:SCRCPY_SERVER_PATH = $previousScrcpyServerPath
}

exit $childExitCode
