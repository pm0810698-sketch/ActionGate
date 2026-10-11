$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { throw 'Python environment is missing. Run .\setup.ps1 first.' }
$compileFiles = @(Get-ChildItem (Join-Path $PSScriptRoot 'app') -Filter '*.py' -File | ForEach-Object { $_.FullName }) + @((Join-Path $PSScriptRoot 'scripts\demo_agent.py'))
& $pythonExe -m py_compile @compileFiles
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }
& $pythonExe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
