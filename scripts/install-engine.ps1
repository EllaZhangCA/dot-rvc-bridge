$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskRuntime = Join-Path $taskRoot 'runtime'
$taskControlPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
$taskEnginePython = Join-Path $taskRuntime 'engine-venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskControlPython)) { throw 'Run scripts/setup.ps1 first (Python 3.11+ required).' }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv from https://docs.astral.sh/uv/getting-started/installation/ first.' }
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { throw 'Node.js with npm is required to build the upstream UI.' }
$taskManifest = Get-Content (Join-Path $taskRoot 'engine-manifest.json') -Raw | ConvertFrom-Json
$taskSource = Join-Path $taskRuntime ('source\voice-changer-' + $taskManifest.source_commit)
$env:UV_CACHE_DIR = Join-Path $taskRuntime 'uv-cache'
& $taskControlPython (Join-Path $PSScriptRoot 'prepare-engine.py')
if ($LASTEXITCODE -ne 0) { throw 'Source/base-asset preparation failed.' }
uv python install $taskManifest.python
if ($LASTEXITCODE -ne 0) { throw 'Python runtime installation failed.' }
if (-not (Test-Path -LiteralPath $taskEnginePython)) {
    uv venv --python $taskManifest.python (Join-Path $taskRuntime 'engine-venv')
    if ($LASTEXITCODE -ne 0) { throw 'Engine environment creation failed.' }
}
uv pip install --python $taskEnginePython ('torch==' + $taskManifest.torch) ('torchaudio==' + $taskManifest.torchaudio) --index-url https://download.pytorch.org/whl/cu118
if ($LASTEXITCODE -ne 0) { throw 'CUDA runtime installation failed.' }
uv pip install --python $taskEnginePython -r (Join-Path $taskRoot 'engine-requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Engine dependencies failed. Fairseq needs Visual Studio C++ Build Tools and a Windows SDK.' }
Push-Location (Join-Path $taskSource 'client\demo')
try {
    npm ci --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
    npm run build:prod
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
} finally { Pop-Location }
uv pip check --python $taskEnginePython
if ($LASTEXITCODE -ne 0) { throw 'Engine dependency consistency check failed.' }
Write-Output 'Source engine installed. Run scripts/start-engine.ps1 after configuring dot-rvc.local.toml.'
