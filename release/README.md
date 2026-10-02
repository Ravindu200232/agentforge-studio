# AgentForge desktop release

AgentForge ships as a Windows desktop app, installed by a one-click online installer.

| File | What it is |
|---|---|
| `AgentForgeSetup.exe` | What people download. About 150 KB. It installs everything below. |
| `AgentForge-<version>-win-x64.zip` | The app: Electron, the studio UI, the backend, and its own Python 3.12. |
| `manifest.json` | What the installer installs, each file pinned by sha256. |

## Build

```powershell
./release/build.ps1
```

This needs, on the build computer only:
- Node.js
- Python 3.12 (`py -3.12`)
- An internet connection

The script:
1. Builds the studio UI (`STUDIO_EXPORT=1`).
2. Stages the backend, its Node modules and an embeddable Python in `release/stage/app`.
3. Packages Electron (`desktop/`).
4. Pins today's versions of the command line tools and writes both manifests.
5. Compiles the installer with the C# compiler built into Windows.

Everything is written to `release/out`.

## Test the installer without publishing

`manifest.local.json` points at the files on this computer:

```powershell
release\out\AgentForgeSetup.exe /manifest=release\out\manifest.local.json /dir=$env:TEMP\AgentForgeTest /noshortcuts /auto
```

`/auto` starts at once and exits with code 0 when everything installed. A clean Windows Sandbox is the real
"blank computer" test.

## Publish

```powershell
./release/build.ps1 -Repo Ravindu200232/agentforge-releases -Publish
```

This creates the GitHub release `v<version>` (version from `desktop/package.json`). The installer always reads
`https://github.com/<repo>/releases/latest/download/manifest.json`, so the repository it publishes to must be public.
The source repository stays private: releases go to the public `agentforge-releases` repository. A new release needs
a new version in `desktop/package.json`.

## What a blank computer gets

Everything is installed per user into `%LOCALAPPDATA%\Programs\AgentForge`, with no administrator rights:

- The app and its Python.
- In `tools\`:
  - Node.js
  - Git (MinGit)
  - GitHub CLI
  - AWS CLI (unpacked from its MSI)
  - Azure CLI
  - The Vercel, Netlify and Supabase CLIs
  - Playwright's Chromium

The installer also adds a Desktop shortcut, a Start-menu shortcut, and an "Installed apps" entry.

The user's own files live outside the install folder, so updates and uninstalls never touch them:
- Settings and records: `%APPDATA%\AgentForge`
- Projects: `Documents\AgentForge`

## No ports

The desktop app's backend (`server.py --stdio`) talks to the window over stdin and stdout, so nothing listens:
- The studio's requests go through the app's own `agentforge://` protocol.
- The live feed arrives over IPC.
- A test run's live view goes through a folder.

The one exception is a short-lived `127.0.0.1:7824` listener, open only while a Supabase browser sign-in waits for
its callback. A generated app's own preview still runs on its own `127.0.0.1` port.

## Unsigned builds

Until the exe files are code-signed, Windows SmartScreen shows "Windows protected your PC" the first time someone
runs the installer. They click **More info → Run anyway** to continue. A code-signing certificate (for example Azure
Trusted Signing) removes the warning.
