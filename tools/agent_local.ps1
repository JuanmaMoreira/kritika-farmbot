function Get-AgentLocalPaths {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepositoryRoot
    )

    $root = [System.IO.Path]::GetFullPath($RepositoryRoot)
    $configPath = Join-Path $root 'AGENT_LOCAL.md'
    $values = @{}

    if (Test-Path -LiteralPath $configPath -PathType Leaf) {
        foreach ($line in Get-Content -LiteralPath $configPath) {
            if ($line -match '^\s*(PYTHON_EXE|ADB_EXE|SCRCPY_SERVER_PATH)\s*=\s*(.+?)\s*$') {
                $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
            }
        }
    }

    function Resolve-ConfiguredPath {
        param([string]$Name)

        if (-not $values.ContainsKey($Name)) {
            return $null
        }

        $value = $values[$Name]
        if ([string]::IsNullOrWhiteSpace($value) -or $value.StartsWith('<')) {
            return $null
        }
        if (-not [System.IO.Path]::IsPathRooted($value)) {
            $value = Join-Path $root $value
        }
        return [System.IO.Path]::GetFullPath($value)
    }

    return [PSCustomObject]@{
        ConfigPath = $configPath
        PythonExe = Resolve-ConfiguredPath 'PYTHON_EXE'
        AdbExe = Resolve-ConfiguredPath 'ADB_EXE'
        ScrcpyServerPath = Resolve-ConfiguredPath 'SCRCPY_SERVER_PATH'
    }
}
