[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$localConfigPath = Join-Path $repoRoot 'AGENT_LOCAL.md'
$localValues = @{}

if (Test-Path -LiteralPath $localConfigPath -PathType Leaf) {
    foreach ($line in Get-Content -LiteralPath $localConfigPath) {
        if ($line -match '^\s*(PYTHON_EXE|ADB_EXE|SCRCPY_SERVER_PATH)\s*=\s*(.+?)\s*$') {
            $localValues[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
        }
    }
}

function Resolve-AgentPath {
    param([string]$Name)

    if (-not $localValues.ContainsKey($Name)) {
        return $null
    }

    $value = $localValues[$Name]
    if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith('<')) {
        return $null
    }

    if (-not [System.IO.Path]::IsPathRooted($value)) {
        $value = Join-Path $repoRoot $value
    }

    return [System.IO.Path]::GetFullPath($value)
}

$pythonExe = Resolve-AgentPath 'PYTHON_EXE'
$adbExe = Resolve-AgentPath 'ADB_EXE'
$scrcpyServer = Resolve-AgentPath 'SCRCPY_SERVER_PATH'

Push-Location $repoRoot
try {
    $branch = (& git branch --show-current).Trim()
    $head = (& git rev-parse --short HEAD).Trim()
    $worktreeOutput = @(& git status --short)
    $worktree = if ($worktreeOutput.Count -eq 0) { 'clean' } else { "dirty ($($worktreeOutput.Count))" }

    $upstream = (& git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>$null)
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($upstream)) {
        $upstreamStatus = 'not configured'
    }
    else {
        $counts = ((& git rev-list --left-right --count ("HEAD..." + $upstream.Trim())).Trim() -split '\s+')
        $ahead = [int]$counts[0]
        $behind = [int]$counts[1]
        if ($ahead -eq 0 -and $behind -eq 0) {
            $upstreamStatus = 'synced'
        }
        else {
            $upstreamStatus = "ahead $ahead / behind $behind"
        }
    }
}
finally {
    Pop-Location
}

$pythonStatus = 'not configured'
if ($pythonExe -and (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    & $pythonExe --version *> $null
    $pythonStatus = if ($LASTEXITCODE -eq 0) { 'OK' } else { 'invalid' }
}

$adbStatus = if ($adbExe -and (Test-Path -LiteralPath $adbExe -PathType Leaf)) { 'configured' } else { 'not configured' }
$scrcpyStatus = if ($scrcpyServer -and (Test-Path -LiteralPath $scrcpyServer -PathType Leaf)) { 'configured' } else { 'not configured' }

Write-Output "BRANCH: $branch"
Write-Output "HEAD: $head"
Write-Output "UPSTREAM: $upstreamStatus"
Write-Output "WORKTREE: $worktree"
Write-Output "PYTHON: $pythonStatus"
Write-Output "ADB: $adbStatus"
Write-Output "SCRCPY: $scrcpyStatus"
