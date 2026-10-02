# Build an AgentForge desktop release: the app, its online installer, and the manifest the installer reads.
#
#   ./release/build.ps1                     build everything into release/out
#   ./release/build.ps1 -Publish            ...and upload it as a GitHub release (needs `gh auth login`)
#
# release/out gets:
#   AgentForge-<version>-win-x64.zip        the app: Electron, the studio UI, the backend, and its own Python
#   AgentForgeSetup.exe                     the one-click installer people download
#   manifest.json                           what the installer installs, with every file's sha256
#   manifest.local.json                     the same, from the files on this computer (to test the installer offline)
#
# The command line tools a blank Windows computer is missing (Node.js, Git, gh, AWS and Azure CLIs, the Vercel,
# Netlify and Supabase CLIs, Playwright's browser) are not in the zip: the installer fetches each from its official
# source, pinned here to the version current when the release was built.
param(
    [string]$Repo = '',
    [switch]$Publish,
    # One part at a time (each is quick enough to run on its own, and the next picks up what it left in
    # release/stage and release/out): ui, stage, python, package, zip, manifest. Default: all of them.
    [string[]]$Phase = @('all')
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# `-Phase ui,stage` arrives as one string when the script is run with -File.
$Phase = @($Phase | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$root = Split-Path -Parent $PSScriptRoot
$release = $PSScriptRoot
$stage = Join-Path $release 'stage\app'
$out = Join-Path $release 'out'
$cache = Join-Path $release 'cache'
$version = (Get-Content (Join-Path $root 'desktop\package.json') -Raw | ConvertFrom-Json).version
if (-not $Repo) {
    $remote = (git -C $root remote get-url origin).Trim()
    $Repo = ($remote -replace '^.*github\.com[:/]', '' -replace '\.git$', '')
}
$PythonVersion = '3.12.10'
$StudioModules = @{ 'puppeteer' = '25.12.0'; 'marked' = '4.3.0'; '@mermaid-js/mermaid-cli' = '11.17.0' }
$BackendPackages = @('ollama>=0.6.2,<1', 'httpx>=0.27,<1', 'pydantic>=2.6,<3', 'cryptography>=42,<48')

function Step($text) { Write-Host "`n== $text" -ForegroundColor Cyan }

function Get-Cached($url, $name) {
    New-Item -ItemType Directory -Force $cache | Out-Null
    $file = Join-Path $cache $name
    if (-not (Test-Path $file)) {
        Write-Host "   downloading $url"
        # Windows' own curl streams to disk and resumes; Windows PowerShell's Invoke-WebRequest holds the whole file
        # in memory first and stalls on large ones (the Azure CLI zip).
        $curl = Join-Path $env:WINDIR 'System32\curl.exe'
        if (Test-Path $curl) {
            & $curl --fail --location --silent --show-error --retry 4 --continue-at - --user-agent 'AgentForge-release' --output "$file.part" $url
            if ($LASTEXITCODE -ne 0) { throw "download failed: $url (curl $LASTEXITCODE)" }
        } else {
            Invoke-WebRequest -Uri $url -OutFile "$file.part" -UseBasicParsing -Headers @{ 'User-Agent' = 'AgentForge-release' }
        }
        Move-Item "$file.part" $file -Force
    }
    return $file
}

function Get-Sha256($file) { (Get-FileHash -Algorithm SHA256 $file).Hash.ToLowerInvariant() }

function Get-ZipStrip($file) {
    # 1 when every entry sits under one top folder (node-v24.x-win-x64\...), else 0.
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($file)
    try {
        $tops = $zip.Entries | ForEach-Object { ($_.FullName -replace '\\', '/').Split('/')[0] } | Sort-Object -Unique
        $nested = $zip.Entries | Where-Object { ($_.FullName -replace '\\', '/').Contains('/') }
        if (@($tops).Count -eq 1 -and @($nested).Count -gt 0) { return 1 } else { return 0 }
    } finally { $zip.Dispose() }
}

function Find-Python312 {
    try { $found = (& py -3.12 -c 'import sys; print(sys.executable)' 2>$null) } catch { $found = $null }
    if ($found) { return $found.Trim() }
    $default = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path $default) { return $default }
    throw 'Python 3.12 is needed to stage the app''s Python packages (py -3.12).'
}

function Invoke-Robocopy($from, $to) {
    robocopy $from $to /E /XD __pycache__ node_modules .pytest_cache /XF *.pyc /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy $from failed ($LASTEXITCODE)" }
}

New-Item -ItemType Directory -Force $out | Out-Null
$appZip = Join-Path $out "AgentForge-$version-win-x64.zip"
$unpacked = Join-Path $root 'desktop\dist\win-unpacked'
function Want($name) { return ($Phase -contains 'all') -or ($Phase -contains $name) }

if (Want 'ui') {
    Step "Studio UI (static build)"
    Push-Location (Join-Path $root 'studio')
    $env:STUDIO_EXPORT = '1'
    try { npx.cmd next build; if ($LASTEXITCODE -ne 0) { throw 'next build failed' } } finally { Remove-Item Env:STUDIO_EXPORT; Pop-Location }
}

if (Want 'stage') {
    Step "Stage the app in $stage"
    if (Test-Path $stage) { Remove-Item -Recurse -Force $stage }
    New-Item -ItemType Directory -Force $stage | Out-Null
    Invoke-Robocopy (Join-Path $root 'studio\out') (Join-Path $stage 'studio')
    $backend = Join-Path $stage 'backend'
    New-Item -ItemType Directory -Force $backend | Out-Null
    Copy-Item (Join-Path $root 'server.py') $backend
    foreach ($folder in 'server_modules', 'src', 'srs-agent', 'prototype-agent', 'builder-agent', 'qa-agent', 'deploy-agent', 'prompts',
                        'srs-test-sources\srs-sources', 'srs-test-sources\diagram-sources') {
        Invoke-Robocopy (Join-Path $root $folder) (Join-Path $backend $folder)
    }

    Step "The backend's Node modules (PDF and diagram rendering)"
    $studioRuntime = Join-Path $backend 'studio'
    New-Item -ItemType Directory -Force $studioRuntime | Out-Null
    $deps = @{}; foreach ($key in $StudioModules.Keys) { $deps[$key] = $StudioModules[$key] }
    @{ name = 'agentforge-backend-runtime'; private = $true; dependencies = $deps } | ConvertTo-Json | Set-Content (Join-Path $studioRuntime 'package.json') -Encoding UTF8
    $env:PUPPETEER_SKIP_DOWNLOAD = '1'
    Push-Location $studioRuntime
    try { npm.cmd install --omit=dev --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'npm install failed' } } finally { Pop-Location; Remove-Item Env:PUPPETEER_SKIP_DOWNLOAD }
}

if (Want 'python') {
    Step "Python $PythonVersion (embeddable) and the backend's packages"
    $embed = Get-Cached "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" "python-$PythonVersion-embed-amd64.zip"
    $python = Join-Path $stage 'python'
    if (Test-Path $python) { Remove-Item -Recurse -Force $python }
    Expand-Archive -Path $embed -DestinationPath $python -Force
    $site = Join-Path $python 'Lib\site-packages'
    New-Item -ItemType Directory -Force $site | Out-Null
    $pth = Get-ChildItem $python -Filter 'python3*._pth' | Select-Object -First 1
    # The embeddable Python ignores PYTHONPATH and reads this instead; server.py adds the backend's own folders.
    @('python312.zip', '.', 'Lib\site-packages', 'import site') | Set-Content $pth.FullName -Encoding ASCII
    $hostPython = Find-Python312
    & $hostPython -m pip install --disable-pip-version-check --target $site --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp @BackendPackages
    if ($LASTEXITCODE -ne 0) { throw 'pip install failed' }
}

if (Want 'package') {
    Step "Package the app (Electron)"
    Push-Location (Join-Path $root 'desktop')
    try { npx.cmd electron-builder --dir --publish never; if ($LASTEXITCODE -ne 0) { throw 'electron-builder failed' } } finally { Pop-Location }
}

if (Want 'zip') {
    Step "Zip the app"
    if (Test-Path $appZip) { Remove-Item $appZip }
    # Windows' own tar writes a zip several times faster than .NET for tens of thousands of small files.
    $tar = Join-Path $env:WINDIR 'System32\tar.exe'
    if (Test-Path $tar) {
        & $tar -a -c -f $appZip -C $unpacked *
        if ($LASTEXITCODE -ne 0) { throw 'tar could not write the zip' }
    } else {
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [IO.Compression.ZipFile]::CreateFromDirectory($unpacked, $appZip, [IO.Compression.CompressionLevel]::Fastest, $false)
    }
}

if (-not (Want 'manifest')) { Step "Done"; return }
if (-not (Test-Path $appZip)) { throw "$appZip is missing: run the zip phase first" }

Step "The command line tools, pinned to today's versions"
$headers = @{ 'User-Agent' = 'AgentForge-release' }
# Windows PowerShell hands a JSON array over as one object: take it into a variable first so the pipeline walks it.
$releases = Invoke-RestMethod 'https://nodejs.org/dist/index.json' -Headers $headers
$node = ($releases | Where-Object { $_.version -like 'v24.*' -and $_.files -contains 'win-x64-zip' } | Select-Object -First 1).version
$mingit = (Invoke-RestMethod 'https://api.github.com/repos/git-for-windows/git/releases/latest' -Headers $headers).assets | Where-Object { $_.name -match '^MinGit-[\d.]+-64-bit\.zip$' } | Select-Object -First 1
$gh = (Invoke-RestMethod 'https://api.github.com/repos/cli/cli/releases/latest' -Headers $headers).assets | Where-Object { $_.name -match '_windows_amd64\.zip$' } | Select-Object -First 1
$awsTags = Invoke-RestMethod 'https://api.github.com/repos/aws/aws-cli/tags?per_page=100' -Headers $headers
$aws = ($awsTags | Where-Object { $_.name -match '^2\.\d+\.\d+$' } | Select-Object -First 1).name
# The same zip Microsoft's own blob store serves, from GitHub's CDN: that store can crawl at tens of KB/s.
$azure = ((Invoke-RestMethod 'https://api.github.com/repos/Azure/azure-cli/releases/latest' -Headers $headers).assets | Where-Object { $_.name -match '^azure-cli-[\d.]+-x64\.zip$' } | Select-Object -First 1).browser_download_url
if (-not $azure) { $azure = [Net.WebRequest]::Create('https://aka.ms/installazurecliwindowszipx64').GetResponse().ResponseUri.AbsoluteUri }
$npmClis = foreach ($name in 'vercel', 'netlify-cli', 'supabase') { "$name@" + (npm.cmd view $name version).Trim() }
$playwright = (npm.cmd view playwright version).Trim()

$tools = @(
    @{ id = 'node'; title = "Node.js $node"; url = "https://nodejs.org/dist/$node/node-$node-win-x64.zip"; type = 'zip'; target = 'tools/node' },
    @{ id = 'git'; title = 'Git'; url = $mingit.browser_download_url; type = 'zip'; target = 'tools/git' },
    @{ id = 'gh'; title = 'GitHub CLI'; url = $gh.browser_download_url; type = 'zip'; target = 'tools/gh' },
    @{ id = 'aws'; title = "AWS CLI $aws"; url = "https://awscli.amazonaws.com/AWSCLIV2-$aws.msi"; type = 'msi-extract'; target = 'tools/aws' },
    @{ id = 'az'; title = 'Azure CLI'; url = "$azure"; type = 'zip'; target = 'tools/az' }
)
$components = @()
$localComponents = @()
$appSize = (Get-Item $appZip).Length
$appEntry = [ordered]@{ id = 'app'; title = "AgentForge $version"; version = $version; type = 'zip'; target = '.'; strip = 0;
                        url = "https://github.com/$Repo/releases/download/v$version/" + (Split-Path $appZip -Leaf);
                        sha256 = (Get-Sha256 $appZip); size = $appSize }
$components += $appEntry
$localApp = [ordered]@{}; foreach ($key in $appEntry.Keys) { $localApp[$key] = $appEntry[$key] }; $localApp.url = $appZip
$localComponents += $localApp
foreach ($tool in $tools) {
    $name = Split-Path ([Uri]$tool.url).AbsolutePath -Leaf
    $file = Get-Cached $tool.url $name
    $entry = [ordered]@{ id = $tool.id; title = $tool.title; type = $tool.type; target = $tool.target; url = $tool.url;
                         sha256 = (Get-Sha256 $file); size = (Get-Item $file).Length }
    if ($tool.type -eq 'zip') { $entry.strip = (Get-ZipStrip $file) }
    Write-Host ("   {0,-6} {1}  {2:N0} MB" -f $tool.id, $name, ($entry.size / 1MB))
    $components += $entry
    $local = [ordered]@{}; foreach ($key in $entry.Keys) { $local[$key] = $entry[$key] }; $local.url = $file
    $localComponents += $local
}
$npmEntry = [ordered]@{ id = 'npm-clis'; title = 'the Vercel, Netlify and Supabase CLIs'; type = 'npm-global'; target = 'tools/npm';
                        packages = @($npmClis); weight = 250000000 }
$browserEntry = [ordered]@{ id = 'playwright'; title = "the browser for app tests (Playwright $playwright)"; type = 'npm-exec';
                            target = 'tools/ms-playwright'; command = @("playwright@$playwright", 'install', 'chromium');
                            env = @{ PLAYWRIGHT_BROWSERS_PATH = '{install}\tools\ms-playwright' }; weight = 200000000 }
$components += $npmEntry, $browserEntry
$localComponents += $npmEntry, $browserEntry

Step "manifest.json"
[ordered]@{ version = $version; repo = $Repo; built = (Get-Date).ToString('s'); components = $components } |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $out 'manifest.json') -Encoding UTF8
[ordered]@{ version = $version; repo = $Repo; built = (Get-Date).ToString('s'); components = $localComponents } |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $out 'manifest.local.json') -Encoding UTF8

Step "AgentForgeSetup.exe"
$installer = Join-Path $release 'installer'
@"
namespace AgentForge.Setup { static class Config {
    public const string AppName = "AgentForge";
    public const string Publisher = "AgentForge";
    public const string ManifestUrl = "https://github.com/$Repo/releases/latest/download/manifest.json";
} }
"@ | Set-Content (Join-Path $installer 'Config.generated.cs') -Encoding UTF8
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $csc -nologo -target:winexe -optimize+ "-out:$(Join-Path $out 'AgentForgeSetup.exe')" `
    "-win32icon:$(Join-Path $root 'desktop\build\icon.ico')" "-win32manifest:$(Join-Path $installer 'app.manifest')" `
    -r:System.IO.Compression.dll -r:System.IO.Compression.FileSystem.dll -r:System.Web.Extensions.dll `
    -r:System.Windows.Forms.dll -r:System.Drawing.dll `
    (Join-Path $installer 'AgentForgeSetup.cs') (Join-Path $installer 'Config.generated.cs')
if ($LASTEXITCODE -ne 0) { throw 'the installer did not compile' }

Step "Done"
Get-ChildItem $out | Where-Object { -not $_.PSIsContainer } | ForEach-Object { "   {0,-40} {1,10:N1} MB" -f $_.Name, ($_.Length / 1MB) }

if ($Publish) {
    Step "Publish v$version to github.com/$Repo"
    gh release create "v$version" (Join-Path $out 'AgentForgeSetup.exe') $appZip (Join-Path $out 'manifest.json') `
        --repo $Repo --title "AgentForge $version" --notes "Download AgentForgeSetup.exe and run it."
    if ($LASTEXITCODE -ne 0) { throw 'gh release create failed' }
}
