#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE="$ROOT/release"
STAGE="$RELEASE/stage/app"
CACHE="$RELEASE/cache-mac"
OUT="${AGENTFORGE_MAC_OUT:-$RELEASE/out-mac}"
VERSION="$(node -p "require('$ROOT/desktop/package.json').version")"
HOST_ARCH="$(uname -m)"
BACKEND_PACKAGES=(
  'ollama>=0.6.2,<1'
  'httpx>=0.27,<1'
  'pydantic>=2.6,<3'
  'cryptography>=42,<48'
  'presidio-analyzer>=2.2,<3'
  'presidio-anonymizer>=2.2,<3'
  'spacy>=3.7,<4'
)
PRIVACY_MODEL='https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl'

case "$HOST_ARCH" in
  arm64) PYTHON_ARCH="aarch64"; ELECTRON_ARCH="arm64" ;;
  x86_64) PYTHON_ARCH="x86_64"; ELECTRON_ARCH="x64" ;;
  *) echo "Unsupported macOS architecture: $HOST_ARCH" >&2; exit 1 ;;
esac

step() { printf '\n== %s\n' "$1"; }
need() { command -v "$1" >/dev/null || { echo "Missing required command: $1" >&2; exit 1; }; }

for command in node npm curl tar rsync sips iconutil codesign hdiutil ditto; do need "$command"; done
[[ "$(uname -s)" == "Darwin" ]] || { echo "This release script must run on macOS." >&2; exit 1; }

mkdir -p "$CACHE" "$OUT"

step "Studio dependencies and static export"
if [[ ! -x "$ROOT/studio/node_modules/.bin/next" ]]; then
  (cd "$ROOT/studio" && PUPPETEER_SKIP_DOWNLOAD=1 npm ci --no-audit --no-fund \
    --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=600000)
fi
(cd "$ROOT/studio" && STUDIO_EXPORT=1 npm run build)

step "Stage the application"
rm -rf "$STAGE"
mkdir -p "$STAGE/studio" "$STAGE/backend" "$STAGE/tools"
rsync -a --delete "$ROOT/studio/out/" "$STAGE/studio/"
cp "$ROOT/server.py" "$STAGE/backend/server.py"
for folder in server_modules src srs-agent prototype-agent builder-agent qa-agent deploy-agent prompts; do
  rsync -a --exclude '__pycache__' --exclude '*.pyc' "$ROOT/$folder/" "$STAGE/backend/$folder/"
done
mkdir -p "$STAGE/backend/srs-test-sources"
for folder in srs-sources diagram-sources; do
  rsync -a "$ROOT/srs-test-sources/$folder/" "$STAGE/backend/srs-test-sources/$folder/"
done

step "Backend JavaScript runtime"
mkdir -p "$STAGE/backend/studio"
cat > "$STAGE/backend/studio/package.json" <<'JSON'
{
  "name": "agentforge-backend-runtime",
  "private": true,
  "dependencies": {
    "@mermaid-js/mermaid-cli": "11.17.0",
    "marked": "4.3.0",
    "puppeteer": "25.12.0"
  }
}
JSON
(cd "$STAGE/backend/studio" && PUPPETEER_SKIP_DOWNLOAD=1 npm install --omit=dev --no-audit --no-fund \
  --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=600000)

step "Portable CPython 3.12 and backend packages"
METADATA="$CACHE/python-build-standalone.json"
GITHUB_HEADERS=()
if [[ -n "${GH_TOKEN:-}" ]]; then GITHUB_HEADERS=(-H "Authorization: Bearer $GH_TOKEN"); fi
# macOS's bash 3.2 treats an empty array as unbound under `set -u`: expand it only when it holds the header.
curl --fail --location --silent --show-error --retry 4 ${GITHUB_HEADERS[@]+"${GITHUB_HEADERS[@]}"} \
  https://api.github.com/repos/astral-sh/python-build-standalone/releases/latest -o "$METADATA"
PYTHON_URL="$(node -e '
const fs = require("node:fs");
const [file, arch] = process.argv.slice(1);
const release = JSON.parse(fs.readFileSync(file, "utf8"));
const suffix = `${arch}-apple-darwin-install_only_stripped.tar.gz`;
const asset = (release.assets || []).find(item => /^cpython-3\.12\./.test(item.name) && item.name.endsWith(suffix) && !item.name.includes("freethreaded"));
if (!asset) process.exit(2);
process.stdout.write(asset.browser_download_url);
' "$METADATA" "$PYTHON_ARCH")" || {
  echo "The latest python-build-standalone release has no CPython 3.12 build for $PYTHON_ARCH macOS." >&2
  exit 1
}
PYTHON_ARCHIVE="$CACHE/$(basename "$PYTHON_URL")"
if [[ ! -s "$PYTHON_ARCHIVE" ]]; then
  curl --fail --location --silent --show-error --retry 4 ${GITHUB_HEADERS[@]+"${GITHUB_HEADERS[@]}"} "$PYTHON_URL" -o "$PYTHON_ARCHIVE.part"
  mv "$PYTHON_ARCHIVE.part" "$PYTHON_ARCHIVE"
fi
PYTHON_TMP="$(mktemp -d)"
trap 'rm -rf "$PYTHON_TMP" "${NODE_TMP:-}" "${DMG_STAGE:-}"' EXIT
tar -xzf "$PYTHON_ARCHIVE" -C "$PYTHON_TMP"
rsync -a "$PYTHON_TMP/python/" "$STAGE/python/"
"$STAGE/python/bin/python3" -m pip install --disable-pip-version-check \
  "${BACKEND_PACKAGES[@]}"
"$STAGE/python/bin/python3" -m pip install --disable-pip-version-check --no-deps "$PRIVACY_MODEL"

step "Bundled Node.js and npm"
NODE_INDEX="$CACHE/node-index.json"
curl --fail --location --silent --show-error --retry 4 https://nodejs.org/dist/index.json -o "$NODE_INDEX"
NODE_VERSION="$(node -e '
const fs = require("node:fs");
const [file, arch] = process.argv.slice(1);
const needed = `osx-${arch}-tar`;
const found = JSON.parse(fs.readFileSync(file, "utf8")).find(item => /^v24\./.test(item.version) && item.files.includes(needed));
if (!found) process.exit(2);
process.stdout.write(found.version);
' "$NODE_INDEX" "$ELECTRON_ARCH")" || { echo "Could not find the current Node.js 24 macOS build." >&2; exit 1; }
NODE_URL="https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-darwin-$ELECTRON_ARCH.tar.gz"
NODE_ARCHIVE="$CACHE/$(basename "$NODE_URL")"
if [[ ! -s "$NODE_ARCHIVE" ]]; then
  curl --fail --location --silent --show-error --retry 4 "$NODE_URL" -o "$NODE_ARCHIVE.part"
  mv "$NODE_ARCHIVE.part" "$NODE_ARCHIVE"
fi
NODE_TMP="$(mktemp -d)"
tar -xzf "$NODE_ARCHIVE" -C "$NODE_TMP"
rsync -a "$NODE_TMP/node-$NODE_VERSION-darwin-$ELECTRON_ARCH/" "$STAGE/tools/node/"

step "Playwright Chromium for generated-app end-to-end tests"
PLAYWRIGHT_VERSION="$(npm view playwright version)"
PATH="$STAGE/tools/node/bin:$PATH" \
  PLAYWRIGHT_BROWSERS_PATH="$STAGE/tools/ms-playwright" \
  "$STAGE/tools/node/bin/npx" --yes "playwright@$PLAYWRIGHT_VERSION" install chromium

step "macOS application icon"
ICONSET="$RELEASE/stage/AgentForge.iconset"
rm -rf "$ICONSET"
mkdir -p "$ICONSET"
SOURCE_ICON="$ROOT/desktop/build/icon.png"
for spec in \
  '16 icon_16x16.png' '32 icon_16x16@2x.png' \
  '32 icon_32x32.png' '64 icon_32x32@2x.png' \
  '128 icon_128x128.png' '256 icon_128x128@2x.png' \
  '256 icon_256x256.png' '512 icon_256x256@2x.png' \
  '512 icon_512x512.png' '1024 icon_512x512@2x.png'; do
  pixels="${spec%% *}"
  name="${spec#* }"
  sips -z "$pixels" "$pixels" "$SOURCE_ICON" --out "$ICONSET/$name" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$ROOT/desktop/build/icon.icns"

step "Electron application"
if [[ ! -x "$ROOT/desktop/node_modules/.bin/electron-builder" ]]; then
  (cd "$ROOT/desktop" && npm ci --no-audit --no-fund \
    --fetch-retries=5 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000 --fetch-timeout=600000)
fi
(cd "$ROOT/desktop" && CSC_IDENTITY_AUTO_DISCOVERY=false npx electron-builder --mac dir --"$ELECTRON_ARCH" --publish never)
APP="$(find "$ROOT/desktop/dist" -maxdepth 3 -type d -name 'AgentForge.app' -print -quit)"
[[ -n "$APP" ]] || { echo "electron-builder did not create AgentForge.app" >&2; exit 1; }

step "Ad-hoc sign and verify"
chmod -R u+w "$APP"
xattr -cr "$APP" || true
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
"$APP/Contents/Resources/app/python/bin/python3" --version
"$APP/Contents/Resources/app/tools/node/bin/node" --version

step "DMG and ZIP"
APP_OUT="$OUT/AgentForge.app"
ZIP="$OUT/AgentForge-$VERSION-mac-$HOST_ARCH.zip"
DMG="$OUT/AgentForge-$VERSION-mac-$HOST_ARCH.dmg"
rm -rf "$APP_OUT"
rm -f "$ZIP" "$DMG"
ditto "$APP" "$APP_OUT"
codesign --verify --deep --strict --verbose=2 "$APP_OUT"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"
DMG_STAGE="$(mktemp -d)"
ditto "$APP" "$DMG_STAGE/AgentForge.app"
ln -s /Applications "$DMG_STAGE/Applications"
# On GitHub's Mac runners hdiutil sometimes answers "create failed - Resource busy" while the system still scans the files
# just copied (1.0.3's first build failed there; the same step passed the build before). It is tried again, a few times.
for attempt in 1 2 3 4 5; do
  if hdiutil create -volname AgentForge -srcfolder "$DMG_STAGE" -ov -format UDZO "$DMG"; then break; fi
  if [[ "$attempt" == 5 ]]; then echo "hdiutil could not create the DMG after $attempt tries" >&2; exit 1; fi
  echo "hdiutil was busy (try $attempt); trying again in $((attempt * 10)) seconds" >&2
  rm -f "$DMG"
  sleep $((attempt * 10))
done

step "Built AgentForge $VERSION for macOS $HOST_ARCH"
printf '%s\n%s\n%s\n' "$APP_OUT" "$DMG" "$ZIP"
