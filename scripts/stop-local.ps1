$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$statePath = Join-Path $workspaceRoot "output\runtime\local-services.json"

if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Output "No recorded local service processes were found."
    exit 0
}

$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json

function Test-RecordedLauncher {
    param(
        [System.Diagnostics.Process]$Process,
        [string]$ExpectedStartedAt
    )

    $details = Get-CimInstance Win32_Process -Filter "ProcessId = $($Process.Id)"
    if (-not $details.CommandLine -or $details.CommandLine -notlike "*$workspaceRoot*") {
        return $false
    }
    if ($ExpectedStartedAt) {
        $expected = [DateTimeOffset]::Parse($ExpectedStartedAt).UtcDateTime
        $actual = $Process.StartTime.ToUniversalTime()
        if ([Math]::Abs(($actual - $expected).TotalSeconds) -gt 1) {
            return $false
        }
    }
    return $true
}

function Get-DescendantProcessIds {
    param(
        [int]$RootProcessId,
        [object[]]$ProcessSnapshot
    )

    $descendants = [System.Collections.Generic.List[int]]::new()
    $parents = [System.Collections.Generic.Queue[int]]::new()
    $parents.Enqueue($RootProcessId)
    while ($parents.Count -gt 0) {
        $parentId = $parents.Dequeue()
        foreach ($child in $ProcessSnapshot | Where-Object { $_.ParentProcessId -eq $parentId }) {
            $childId = [int]$child.ProcessId
            $descendants.Add($childId)
            $parents.Enqueue($childId)
        }
    }
    return $descendants.ToArray()
}

$launchers = @(
    [pscustomobject]@{ id = $state.web_launcher_pid; started_at = $state.web_launcher_started_at },
    [pscustomobject]@{ id = $state.api_launcher_pid; started_at = $state.api_launcher_started_at }
) | Where-Object { $_.id }

$skipped = $false
foreach ($launcher in $launchers) {
    $processId = [int]$launcher.id
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        if (-not (Test-RecordedLauncher -Process $process -ExpectedStartedAt $launcher.started_at)) {
            Write-Warning "Skipped launcher process $processId because its identity no longer matches this workspace."
            $skipped = $true
            continue
        }

        $snapshot = @(Get-CimInstance Win32_Process)
        $descendants = @(Get-DescendantProcessIds -RootProcessId $processId -ProcessSnapshot $snapshot)
        [array]::Reverse($descendants)
        foreach ($descendantId in $descendants) {
            Stop-Process -Id $descendantId -Force -ErrorAction SilentlyContinue
            Write-Output "Stopped child process $descendantId."
        }
        Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
        Write-Output "Stopped launcher process $processId."
    }
}

if (-not $skipped) {
    Remove-Item -LiteralPath $statePath -Force
}
