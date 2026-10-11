$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonExe)) { throw 'Python environment is missing. Run .\setup.ps1 first.' }
if (-not $env:GEMINI_MODEL) { $env:GEMINI_MODEL = 'gemini-3.1-flash-lite' }
if (-not $env:GEMINI_API_KEY -or $env:GEMINI_API_KEY -eq 'YOUR_GEMINI_API_KEY') {
    $secure = Read-Host 'Gemini API key (hidden; press Enter to use limited local fallback)' -AsSecureString
    if ($secure.Length -gt 0) {
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        try { $env:GEMINI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    }
    Remove-Variable -Name secure -ErrorAction SilentlyContinue
}
& $pythonExe -m streamlit run app\streamlit_app.py
