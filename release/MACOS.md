# AgentForge for macOS

`build-mac.sh` creates an Apple Silicon desktop build with:

- the exported Next.js Studio;
- the Python backend and a portable CPython 3.12 runtime;
- the backend's Python and Node dependencies, including Microsoft Presidio,
  spaCy, and the English privacy model;
- the current Node.js runtime, including npm and npx; and
- a Playwright Chromium runtime for generated-app end-to-end tests; and
- the Electron application in `.app`, `.dmg`, and `.zip` formats.

## Build

Requirements: macOS on Apple Silicon, Node.js 20+, npm, `curl`, `tar`, `sips`,
`iconutil`, `codesign`, and `hdiutil`.

```bash
chmod +x release/build-mac.sh
./release/build-mac.sh
```

Set `AGENTFORGE_MAC_OUT` to place the artifacts elsewhere. Downloads are cached
under `release/cache-mac`, so later builds reuse them.

The generated application is ad-hoc signed for local use. That verifies bundle
integrity, but it is not Apple notarization. For public distribution, supply an
Apple Developer ID Application certificate, enable hardened runtime, sign every
nested executable, submit the DMG to Apple's notary service, and staple the
notarization ticket before publishing it.

## Runtime notes

Settings are kept in `~/Library/Application Support/AgentForge`. Projects use
`~/Documents/AgentForge` unless the user chooses another empty folder through
the native macOS folder picker.

Node and npm are bundled because applications opened from Finder do not inherit
a shell configured by nvm or Homebrew. Existing tools in `/opt/homebrew/bin`,
`/usr/local/bin`, and `/opt/local/bin` are also made available to the backend.
The release bundles Playwright Chromium for generated-app tests and as a
fallback for screenshots, Mermaid rendering, and PDF rendering. An installed
Chrome, Edge, or Chromium may still be used when explicitly selected.
