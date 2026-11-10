param([string]$BindAddress = '127.0.0.1', [int]$Port = 8001)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install backend/requirements.txt first; see README.md.' }
Push-Location $projectRoot
try { & $pythonPath -m uvicorn app.main:app --app-dir backend --host $BindAddress --port $Port }
finally { Pop-Location }
