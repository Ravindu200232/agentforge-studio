import { spawn } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import process from 'node:process';
import { freePort } from './port-guard.mjs';

// Studio's allocated ports win. Also support running the downloaded project
// directly, where no parent has loaded its environment yet.
const inherited = new Set(Object.keys(process.env));
for (const file of ['.env', '.env.local']) {
  if (!existsSync(file)) continue;
  for (const line of readFileSync(file, 'utf8').split(/\r?\n/)) {
    const match = line.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/);
    if (match && !inherited.has(match[1])) {
      process.env[match[1]] = match[2].replace(/^(['"])(.*)\1$/, '$2');
    }
  }
}

/**
 * Start the API server and the Vite client locally, with no Docker and no
 * process manager. The server owns MongoDB and port 4100; Vite serves the UI
 * on 5174 and proxies /api to the server. One Ctrl-C stops both.
 */
const serverPort = Number(process.env.PORT ?? 4100);
const clientPort = Number(process.env.VITE_PORT ?? 5174);
if (serverPort !== 4100 || clientPort !== 5174) {
  throw new Error('Local vite-mongo development uses server 4100 and Vite 5174');
}
if (!existsSync('server/src/server.js')) throw new Error('server/src/server.js is missing');
if (!existsSync('client/vite-dev.mjs')) throw new Error('client/vite-dev.mjs is missing');

// Claim the fixed local ports before starting the process tree. A stale
// listener must not redirect the server or client URLs to another app.
await Promise.all([freePort(serverPort), freePort(clientPort)]);

const children = [];
let stopping = false;

function stopAll(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) { try { child.kill(); } catch { /* already gone */ } }
  process.exit(code);
}

function spawnPart(name, file, args, env) {
  const child = spawn(process.execPath, [file, ...args], {
    cwd: name === 'client' ? 'client' : undefined,
    env: { ...process.env, ...env },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.on('data', (chunk) => process.stdout.write('[' + name + '] ' + chunk));
  child.stderr.on('data', (chunk) => process.stderr.write('[' + name + '] ' + chunk));
  child.on('exit', (code) => {
    if (!stopping) console.error('[' + name + '] exited with code ' + code);
    stopAll(code ?? 1);
  });
  children.push(child);
}

spawnPart('server', 'server/src/server.js', [], { PORT: String(serverPort) });
spawnPart('client', 'vite-dev.mjs', [], { VITE_PORT: String(clientPort), PORT: String(serverPort) });

process.on('SIGINT', () => stopAll(0));
process.on('SIGTERM', () => stopAll(0));

// The Studio may restart while this preview stays alive. A scoped stop signal
// lets this runner terminate its own child tree without OS-wide process rights.
const runtimeId = process.env.AGENTFORGE_PREVIEW_RUNTIME_ID;
if (runtimeId) {
  setInterval(() => {
    try {
      const signal = JSON.parse(readFileSync('.agentforge/preview-stop.json', 'utf8'));
      if (signal.runtimeId === runtimeId) stopAll(0);
    } catch { /* no stop request */ }
  }, 250).unref();
}
