$ErrorActionPreference = "Stop"

$workspaceRoot = Split-Path -Parent $PSScriptRoot
$apiRoot = Join-Path $workspaceRoot "services\api"
$webRoot = Join-Path $workspaceRoot "apps\web"
$runtimeRoot = Join-Path $workspaceRoot "output\runtime"
$statePath = Join-Path $runtimeRoot "local-services.json"

function Assert-PortAvailable {
    param([int]$Port)

    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $Port is already in use by process $($listener[0].OwningProcess)."
    }
}

function Wait-ForListener {
    param(
        [int]$Port,
        [System.Diagnostics.Process]$Launcher,
        [int]$TimeoutSeconds = 45
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -First 1
        if ($listener) {
            return [int]$listener.OwningProcess
        }
        if ($Launcher.HasExited) {
            throw "The process for port $Port exited before it became ready."
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Timed out waiting for port $Port."
}

function Start-DetachedCommand {
    param([string]$CommandLine)

    $created = Invoke-CimMethod `
        -ClassName Win32_Process `
        -MethodName Create `
        -Arguments @{ CommandLine = $CommandLine }
    if ($created.ReturnValue -ne 0) {
        throw "Windows could not create the detached process (code $($created.ReturnValue))."
    }
    return Get-Process -Id $created.ProcessId -ErrorAction Stop
}

Assert-PortAvailable -Port 8000
Assert-PortAvailable -Port 3000

New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null

$pythonPath = @(
    (Join-Path $apiRoot ".venv313\Scripts\python.exe"),
    (Join-Path $apiRoot ".venv\Scripts\python.exe")
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
$null = Get-Command node.exe -ErrorAction Stop
$nextCliPath = Join-Path $webRoot "node_modules\next\dist\bin\next"
$apiRunnerPath = Join-Path $PSScriptRoot "run-api-local.cmd"
$webRunnerPath = Join-Path $PSScriptRoot "run-web-local.cmd"

if (-not $pythonPath) {
    throw "Backend Python environment was not found. Create services\api\.venv first."
}
if (-not (Test-Path -LiteralPath $nextCliPath)) {
    throw "Next.js was not installed at $nextCliPath. Run npm install in apps\web."
}
if (-not (Test-Path -LiteralPath $apiRunnerPath) -or -not (Test-Path -LiteralPath $webRunnerPath)) {
    throw "Local service runner scripts are missing."
}

$apiStdout = Join-Path $runtimeRoot "api.stdout.log"
$apiStderr = Join-Path $runtimeRoot "api.stderr.log"
$webStdout = Join-Path $runtimeRoot "web.stdout.log"
$webStderr = Join-Path $runtimeRoot "web.stderr.log"

$apiCommand = (
    "cmd.exe /d /c `"`"$apiRunnerPath`" " +
    "1>`"$apiStdout`" 2>`"$apiStderr`"`""
)
$apiProcess = Start-DetachedCommand -CommandLine $apiCommand

try {
    $apiPid = Wait-ForListener -Port 8000 -Launcher $apiProcess

    $webCommand = (
        "cmd.exe /d /c `"`"$webRunnerPath`" " +
        "1>`"$webStdout`" 2>`"$webStderr`"`""
    )
    $webProcess = Start-DetachedCommand -CommandLine $webCommand

    $webPid = Wait-ForListener -Port 3000 -Launcher $webProcess
} catch {
    Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    if ($apiPid) {
        Stop-Process -Id $apiPid -Force -ErrorAction SilentlyContinue
    }
    if ($webProcess) {
        Stop-Process -Id $webProcess.Id -Force -ErrorAction SilentlyContinue
    }
    throw
}

[pscustomobject]@{
    api_pid = $apiPid
    web_pid = $webPid
    api_launcher_pid = $apiProcess.Id
    web_launcher_pid = $webProcess.Id
    api_launcher_started_at = $apiProcess.StartTime.ToUniversalTime().ToString("o")
    web_launcher_started_at = $webProcess.StartTime.ToUniversalTime().ToString("o")
    api_url = "http://127.0.0.1:8000"
    web_url = "http://127.0.0.1:3000"
    started_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8

Write-Output "API PID: $apiPid"
Write-Output "Web PID: $webPid"
Write-Output "Dashboard: http://127.0.0.1:3000/dashboard"
