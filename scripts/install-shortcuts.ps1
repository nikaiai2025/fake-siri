$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
$python = Join-Path $projectRoot '.venv/Scripts/pythonw.exe'
$icon = Join-Path $projectRoot 'assets/chappy.ico'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Run setup.cmd first.'
}
$shell = New-Object -ComObject WScript.Shell
$destinations = @(
    [Environment]::GetFolderPath('Desktop'),
    [Environment]::GetFolderPath('Programs')
)
foreach ($destination in $destinations) {
    $path = Join-Path $destination 'チャッピー.lnk'
    $shortcut = $shell.CreateShortcut($path)
    if ((Test-Path -LiteralPath $path) -and $shortcut.TargetPath -and $shortcut.TargetPath -ne $python) {
        throw "Another shortcut already exists: $path"
    }
    $shortcut.TargetPath = $python
    $shortcut.Arguments = '-m fake_siri'
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.IconLocation = "$icon,0"
    $shortcut.Description = 'チャッピーを起動・表示する音声アシスタント'
    $shortcut.WindowStyle = 1
    $shortcut.Save()
    Write-Host $path
}
