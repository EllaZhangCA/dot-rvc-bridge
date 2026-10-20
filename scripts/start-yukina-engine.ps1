$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot 'runtime\engine-venv\Scripts\python.exe'
$taskScript = Join-Path $PSScriptRoot 'run_yukina_engine.py'
$taskRuntime = Join-Path $taskRoot 'runtime'
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Run scripts/install-engine.ps1 first.' }
if (Get-NetTCPConnection -LocalPort 18888 -State Listen -ErrorAction SilentlyContinue) {
    throw 'Port 18888 is already occupied. Run dot-rvc status to inspect it.'
}
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList @('-u', ('"' + $taskScript + '"')) -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskRuntime 'engine.stdout.log') -RedirectStandardError (Join-Path $taskRuntime 'engine.stderr.log')
$taskRecord = @{ pid = $taskProcess.Id; script = $taskScript; executable = $taskPython; started = $taskProcess.StartTime.ToUniversalTime().ToString('o') }
$taskRecord | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRuntime 'engine-process.json') -Encoding utf8
Write-Output ('Engine starting, PID ' + $taskProcess.Id + '. Logs: runtime/engine.stderr.log')
$taskReady = $false
for ($taskAttempt = 0; $taskAttempt -lt 45; $taskAttempt++) {
    try {
        $taskInfo = Invoke-RestMethod -Uri 'http://127.0.0.1:18888/info' -TimeoutSec 1
        if ($taskInfo.status -eq 'OK') { $taskReady = $true; break }
    } catch { }
    if ($taskProcess.HasExited) { break }
    Start-Sleep -Milliseconds 500
}
if (-not $taskReady) { throw 'Engine did not become ready. Inspect runtime/engine.stderr.log.' }
$taskListeners = @(Get-NetTCPConnection -LocalPort 18888 -State Listen)
if ($taskListeners | Where-Object { $_.LocalAddress -notin @('127.0.0.1', '::1') }) { throw 'Unexpected non-loopback listener; stop the engine and inspect.' }
Write-Output 'Safe profile is online and paused. Configure the approved headphone route explicitly; no audio route was applied by this script.'
