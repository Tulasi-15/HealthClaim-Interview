param([int]$Port = 8000)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path -LiteralPath 'frontend/dist/index.html')) {
        throw 'Build the React frontend first. See frontend/README.md.'
    }
    & '.venv/Scripts/python.exe' -m uvicorn backend.api.react_api:app --host 127.0.0.1 --port $Port
} finally {
    Pop-Location
}
