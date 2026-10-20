param([string]$RecordName = 'engine-process.json')
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
if ($RecordName -notin @('engine-process.json', 'easy-engine-process.json')) { throw 'Unknown engine record.' }
$taskRecordFile = Join-Path (Join-Path $taskRoot 'runtime') $RecordName
if (-not (Test-Path -LiteralPath $taskRecordFile)) { throw 'No managed engine process record exists.' }
$taskRecord = Get-Content -LiteralPath $taskRecordFile -Raw | ConvertFrom-Json
$taskProcess = Get-CimInstance Win32_Process -Filter ('ProcessId = ' + [int]$taskRecord.pid)
if (-not $taskProcess) { Write-Output 'Managed engine already stopped.'; exit 0 }
if ($taskProcess.ExecutablePath -ne $taskRecord.executable -or -not $taskProcess.CommandLine.Contains($taskRecord.script)) { throw 'PID now belongs to a different process; refusing to stop it.' }
$taskActualStart = (Get-Process -Id $taskRecord.pid).StartTime.ToUniversalTime()
if ([Math]::Abs(($taskActualStart - ([DateTime]$taskRecord.started).ToUniversalTime()).TotalSeconds) -gt 1) { throw 'Process start time differs; refusing to stop it.' }
# Windows venv launchers may have a child interpreter with a different PID.
$taskChildren = @(Get-CimInstance Win32_Process -Filter ('ParentProcessId = ' + [int]$taskRecord.pid))
foreach ($taskChild in $taskChildren) {
    if ($taskChild.Name -eq 'conhost.exe' -and $taskChild.ExecutablePath -eq (Join-Path $env:WINDIR 'System32\conhost.exe')) { continue }
    if (-not $taskChild.CommandLine.Contains($taskRecord.script) -or $taskChild.Name -ne 'python.exe') { throw 'Unexpected child process; inspect manually before stopping.' }
}
foreach ($taskChild in $taskChildren | Where-Object Name -eq 'python.exe') { Stop-Process -Id $taskChild.ProcessId -ErrorAction SilentlyContinue }
Stop-Process -Id $taskRecord.pid -ErrorAction SilentlyContinue
Write-Output 'Managed engine stopped. If the app was routed to CABLE Input, restore its output in Windows.'
