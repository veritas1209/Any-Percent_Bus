param([string]$BindAddress = '127.0.0.1', [int]$Port = 8080)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$webRoot = Join-Path $projectRoot 'app\build\web'
if (-not (Test-Path -LiteralPath (Join-Path $webRoot 'index.html'))) { throw 'Run flutter build web --release --no-web-resources-cdn in app first.' }
& (Join-Path $projectRoot '.venv\Scripts\python.exe') -m http.server $Port --bind $BindAddress --directory $webRoot
