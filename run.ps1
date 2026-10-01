$projectRoot = $PSScriptRoot
. "$projectRoot\find-python.ps1"

$pythonExe = Find-Python
if (-not $pythonExe) {
    Write-Error 'Python 3.10+ was not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run: python -m pip install -e .'
    exit 2
}
$env:PYTHONPATH = "$(Get-PythonDeps $pythonExe $projectRoot);$projectRoot\src"

& $pythonExe -m ollama_terminal.cli @args
exit $LASTEXITCODE
