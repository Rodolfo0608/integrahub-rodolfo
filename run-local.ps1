param([int]$Port = 8000, [switch]$SetupOnly)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path '.venv/Scripts/python.exe')) {
    $pythonPath = $env:INTEGRAHUB_PYTHON
    if (-not $pythonPath) {
        $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
        if ($pythonCommand -and $pythonCommand.Source -notlike '*Microsoft/WindowsApps*' -and $pythonCommand.Source -notlike '*Microsoft\WindowsApps*') {
            $pythonPath = $pythonCommand.Source
        }
    }
    if (-not $pythonPath) {
        # Codex bundles a Python runtime next to its Node runtime.
        $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
        if ($nodeCommand) {
            $dependencyRoot = Split-Path (Split-Path (Split-Path $nodeCommand.Source -Parent) -Parent) -Parent
            $bundledPython = Join-Path $dependencyRoot 'python/python.exe'
            if (Test-Path $bundledPython) { $pythonPath = $bundledPython }
        }
    }
    if (-not $pythonPath) {
        $pyCommand = Get-Command py -ErrorAction SilentlyContinue
        if ($pyCommand) {
            & $pyCommand.Source -3 -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno con py -3.' }
        } else {
            throw 'Se necesita Python 3.12+. Instálalo o define INTEGRAHUB_PYTHON con su ruta.'
        }
    } else {
        & $pythonPath -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo crear el entorno Python.' }
    }
}

& '.venv/Scripts/python.exe' -m pip install -r requirements-dev.txt -c constraints.txt
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias.' }
if (-not (Test-Path '.env')) {
    & '.venv/Scripts/python.exe' -c "from pathlib import Path; import secrets; Path('.env').write_text(Path('.env.example').read_text(encoding='utf-8').replace('replace-with-a-random-local-key', secrets.token_urlsafe(32)), encoding='utf-8')"
    if ($LASTEXITCODE -ne 0) { throw 'No se pudo generar .env.' }
}
if ($SetupOnly) { Write-Host 'Entorno listo. Ejecuta .\.venv\Scripts\python.exe -m pytest -q'; exit 0 }
Write-Host "IntegraHub: http://127.0.0.1:$Port/docs (clave local en .env). Ctrl+C para detener."
& '.venv/Scripts/python.exe' -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port $Port --no-access-log
