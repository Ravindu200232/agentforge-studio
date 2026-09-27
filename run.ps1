$projectRoot = $PSScriptRoot
$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

if (Test-Path -LiteralPath $bundledPython) {
    $pythonExe = $bundledPython
    $env:PYTHONPATH = "$projectRoot\.deps;$projectRoot\src"
} else {
    $pythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $pythonExe) {
        Write-Error 'Python was not found. Install Python 3.10+ and run: python -m pip install -e .'
        exit 2
    }
    $env:PYTHONPATH = "$projectRoot\src"
}

& $pythonExe -m ollama_terminal.cli @args
exit $LASTEXITCODE
