$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) {
    Write-Host 'Creating a project-local Python virtual environment...'
    $madeVenv = $false
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.14 -m venv .venv
        if ($LASTEXITCODE -eq 0) { $madeVenv = $true }
        if (-not $madeVenv) {
            & py -3 -m venv .venv
            if ($LASTEXITCODE -eq 0) { $madeVenv = $true }
        }
    }
    if (-not $madeVenv -and (Get-Command python -ErrorAction SilentlyContinue)) {
        & python -m venv .venv
        if ($LASTEXITCODE -eq 0) { $madeVenv = $true }
    }
    if (-not $madeVenv -or -not (Test-Path $pythonExe)) {
        throw 'Could not create .venv. Install Python 3.11+ and ensure the py launcher or python is on PATH, then retry.'
    }
}

Write-Host 'Installing project dependencies...'
& $pythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip upgrade failed.' }
& $pythonExe -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

Write-Host 'Compiling application modules...'
$compileFiles = @(Get-ChildItem (Join-Path $PSScriptRoot 'app') -Filter '*.py' -File | ForEach-Object { $_.FullName }) + @((Join-Path $PSScriptRoot 'scripts\demo_agent.py'))
& $pythonExe -m py_compile @compileFiles
if ($LASTEXITCODE -ne 0) { throw 'Python compilation failed.' }

Write-Host 'Running test suite...'
& $pythonExe -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed. Copy the complete output for debugging.' }

Write-Host ''
Write-Host 'Setup complete. Next, run .\start_gateway.ps1 in this terminal.' -ForegroundColor Green
