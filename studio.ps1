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
$bundled = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'

if (Test-Path -LiteralPath $bundled) {
    $python = $bundled
    $env:PYTHONPATH = "$root\.deps;$root\src;$root\srs-agent;$root\prototype-agent;$root\builder-agent;$root\qa-agent;$root\deploy-agent;$root"
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Error 'Python was not found. Install Python 3.10+ and run: python -m pip install -e .'
        exit 2
    }
    $env:PYTHONPATH = "$root\.deps;$root\src;$root\srs-agent;$root\prototype-agent;$root\builder-agent;$root\qa-agent;$root\deploy-agent;$root"
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
