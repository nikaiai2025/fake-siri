$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $projectRoot '.venv/Scripts/pythonw.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run setup.cmd first.'
}
$env:PYTHONUTF8 = '1'
Start-Process -FilePath $python -ArgumentList @('-m', 'fake_siri') -WorkingDirectory $projectRoot -WindowStyle Hidden
