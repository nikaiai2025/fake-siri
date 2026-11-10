$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$env:PYTHONUTF8 = '1'
$env:UV_CACHE_DIR = Join-Path $projectRoot 'trash/uv-cache'
$python = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (Get-Command uv -ErrorAction SilentlyContinue) {
    if (-not (Test-Path -LiteralPath $python)) {
        uv venv .venv --python 3.12
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 environment setup failed.' }
    }
    uv pip install --python $python -r requirements.lock.txt
} else {
    if (-not (Test-Path -LiteralPath $python)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 first.' }
    }
    & $python -m pip install -r requirements.lock.txt
}
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
& $python scripts/prepare_models.py
if ($LASTEXITCODE -ne 0) { throw 'Speech model setup failed.' }
& (Join-Path $PSScriptRoot 'install-shortcuts.ps1')
Write-Host 'Setup complete. Open the Chappy shortcut on your desktop or in the Start menu.'
