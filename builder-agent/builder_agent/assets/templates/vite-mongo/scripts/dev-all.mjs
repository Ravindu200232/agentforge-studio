import { spawn } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';

/**
 * Start the API server and the Vite client locally, with no Docker and no process manager. The
 * server owns MongoDB; Vite serves the UI and proxies /api to the server. One Ctrl-C stops both.
 *
 * PORT is the one port a browser opens - the Vite client here, the server in production
 * (`npm start`). The AgentForge Studio gives every project's preview a private PORT of its own,
 * so nothing here may insist on a fixed number: the server takes a free port (4100 when it is
 * free). Run directly, with no PORT given, the client is on VITE_PORT or 5174.
 */
// The port a parent gave this process, before .env can say anything: that one is the browser's.
const givenPort = process.env.PORT;

// Also support running the downloaded project directly, where no parent has loaded its environment.
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

if (!existsSync('server/src/server.js')) throw new Error('server/src/server.js is missing');
if (!existsSync('client/vite-dev.mjs')) throw new Error('client/vite-dev.mjs is missing');

/** `preferred` when nothing listens there and it is not `avoid`, else any free port. */
function freePort(preferred, avoid) {
  const tryPort = (port) => new Promise((resolve) => {
    const probe = net.createServer();
    probe.once('error', () => resolve(0));
    probe.listen(port, '127.0.0.1', () => {
      const found = probe.address().port;
      probe.close(() => resolve(found));
    });
  });
  return (async () => {
    for (const port of [preferred, 0, 0, 0]) {
      if (port && port === avoid) continue;
      const found = await tryPort(port);
      if (found && found !== avoid) return found;
    }
    throw new Error('No free local port is available for the server.');
  })();
}

const clientPort = Number(givenPort || process.env.VITE_PORT || 5174);
const serverPort = await freePort(Number(process.env.SERVER_PORT || (givenPort ? 0 : process.env.PORT) || 4100),
  clientPort);

const children = [];
let stopping = false;

function stopAll(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) { try { child.kill(); } catch { /* already gone */ } }
  process.exit(code);
}

function spawnPart(name, file, env) {
  const child = spawn(process.execPath, [file], {
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

// The Studio shows which parts are listening and can start one that is not, so it is told where each part should be
// and how it is run. Only when it asks (AGENTFORGE_PORTS_FILE); nothing secret goes in.
const portsFile = process.env.AGENTFORGE_PORTS_FILE;
if (portsFile) {
  try {
    mkdirSync(path.dirname(portsFile), { recursive: true });
    writeFileSync(portsFile, JSON.stringify({
      written_at: new Date().toISOString(), runtime: process.env.AGENTFORGE_PREVIEW_RUNTIME_ID || '',
      ports: [
        { name: 'client', kind: 'client', port: clientPort, cwd: 'client', command: 'node vite-dev.mjs',
          env: { VITE_PORT: String(clientPort), PORT: String(serverPort) } },
        { name: 'server', kind: 'server', port: serverPort, cwd: '.', command: 'node server/src/server.js',
          env: { PORT: String(serverPort) } },
      ],
    }, null, 2));
  } catch { /* the Studio's view only: the app runs without it */ }
}

spawnPart('server', 'server/src/server.js', { PORT: String(serverPort) });
spawnPart('client', 'vite-dev.mjs', { VITE_PORT: String(clientPort), PORT: String(serverPort) });
console.log(`client http://127.0.0.1:${clientPort} · server ${serverPort}`);

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
