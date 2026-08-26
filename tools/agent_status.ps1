[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot 'agent_local.ps1')
$localPaths = Get-AgentLocalPaths -RepositoryRoot $repoRoot
$pythonExe = $localPaths.PythonExe
$adbExe = $localPaths.AdbExe
$scrcpyServer = $localPaths.ScrcpyServerPath

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
