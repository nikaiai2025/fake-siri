@echo off
set PYTHONUTF8=1
cd /d "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m fake_siri --stop
