# Start the AgentForge backend and the studio together.
#
#   ./studio.ps1                 backend on 7824/7825, studio on 3000
#   ./studio.ps1 -ApiPort 7924 -WsPort 7925 -UiPort 3100
#
# The ports matter: studio/next.config.js proxies /__agentforge/api to the API
# port and /__agentforge/ws to the feed port, and reads both from STUDIO_API and
# STUDIO_WS. Passing them here keeps all three in step.

param(
    [int]$ApiPort = 7824,
    [int]$WsPort  = 7825,
    [int]$UiPort  = 3000
)

$root = $PSScriptRoot
. "$root\find-python.ps1"

$python = Find-Python
if (-not $python) {
    Write-Error 'Python 3.10+ was not found. Install it from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run studio.bat again.'
    exit 2
}
Write-Host "Python   $python"
$deps = Get-PythonDeps $python $root
$env:PYTHONPATH = "$deps;$root\src;$root\srs-agent;$root\prototype-agent;$root\builder-agent;$root\qa-agent;$root\deploy-agent;$root"

# This project's Python packages, if your Python does not have them yet. They go into the project's
# own .deps folder for this Python version, so your Python's own packages are never changed, and a
# first launch cannot leave Next.js running alone with every API request (including sign-in) failing
# as an HTTP 500.
& $python -c "import ollama, httpx, pydantic, cryptography" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing missing backend Python dependencies...'
    & $python -m pip install --upgrade --target "$deps" `
        'ollama>=0.6.2,<1' 'httpx>=0.27,<1' 'pydantic>=2.6,<3' 'cryptography>=42,<48'
    if ($LASTEXITCODE -ne 0) {
        Write-Error 'Backend dependencies could not be installed. Check your Internet connection, then run studio.bat again.'
        exit 2
    }
}

if (-not (Test-Path -LiteralPath "$root\studio\node_modules")) {
    Write-Host 'Installing the studio dependencies (first run only)...'
    Push-Location "$root\studio"
    npm install --no-audit --no-fund
    Pop-Location
}

$env:AGENTFORGE_API_PORT = $ApiPort
$env:AGENTFORGE_WS_PORT  = $WsPort
$env:STUDIO_API = "http://127.0.0.1:$ApiPort"
$env:STUDIO_WS  = "http://127.0.0.1:$WsPort"

Write-Host "Backend  http://127.0.0.1:$ApiPort/__agentforge/api"
Write-Host "Feed     ws://127.0.0.1:$WsPort"
Write-Host "Studio   http://localhost:$UiPort/__agentforge"
Write-Host ''

$backend = Start-Process -FilePath $python -ArgumentList "`"$root\server.py`"" `
    -WorkingDirectory $root -PassThru -NoNewWindow

try {
    Push-Location "$root\studio"
    npx next dev --port $UiPort
} finally {
    Pop-Location
    if ($backend -and -not $backend.HasExited) { Stop-Process -Id $backend.Id -Force }
}
