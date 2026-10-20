$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    python -m venv (Join-Path $taskRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the project Python environment.' }
}
& $taskPython -m pip install -e ($taskRoot + '[audio]')
if ($LASTEXITCODE -ne 0) { throw 'Could not install the bridge dependencies.' }

$taskConfig = [ordered]@{
    '$schema' = 'https://agent-plugins.org/schemas/1.0.0/mcp.schema.json'
    mcpServers = [ordered]@{
        'dot-rvc-bridge' = [ordered]@{
            type = 'stdio'
            command = $taskPython
            args = @('-m', 'dot_rvc.mcp_server')
            env = [ordered]@{
                DOT_RVC_CONFIG = (Join-Path $taskRoot 'dot-rvc.local.toml')
                PYTHONUTF8 = '1'
            }
        }
    }
}
$taskJson = $taskConfig | ConvertTo-Json -Depth 6
[IO.File]::WriteAllText((Join-Path $taskRoot 'mcp.json'), $taskJson, [Text.UTF8Encoding]::new($false))
Write-Output 'Local bridge installed. mcp.json contains paths for this checkout.'
Write-Output 'Engine and audio-driver installation are separate scripts; see README.md.'
& $taskPython -m dot_rvc.cli status
if ($LASTEXITCODE -ne 0) { throw 'The bridge status check failed.' }
