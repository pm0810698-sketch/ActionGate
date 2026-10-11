$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { throw 'Python environment is missing. Run .\setup.ps1 first.' }
& $pythonExe scripts\demo_agent.py
