$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
$frontendIndex = Join-Path $projectRoot 'frontend\dist\photo-booth\browser\index.html'

if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Create the project Python environment using README.md.'
}
if (-not (Test-Path -LiteralPath $frontendIndex -PathType Leaf)) {
    throw 'Build the Angular application using README.md.'
}
Push-Location (Join-Path $projectRoot 'backend')
try {
    & $pythonPath -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
    if ($LASTEXITCODE -ne 0) { throw "FastAPI exited with code $LASTEXITCODE." }
} finally {
    Pop-Location
}
