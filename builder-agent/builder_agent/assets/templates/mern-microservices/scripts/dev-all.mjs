import { spawn } from 'node:child_process';
import { readdirSync, existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
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
 * Start every service plus the gateway locally, with no Docker and no process
 * manager. Vite serves the UI on 5173, the gateway serves API on 4000, and
 * internal service packages use 4001–4020. One Ctrl-C stops everything.
 *
 * The service list is read from the workspace rather than written here, so
 * adding a package is the only step needed to run it.
 */
const packagesDir = 'packages';
const services = readdirSync(packagesDir, { withFileTypes: true })
  .filter((entry) => entry.isDirectory() && existsSync(path.join(packagesDir, entry.name, 'src/server.js')))
  // The gateway starts last: it is the front door, and a client that reaches
  // it before the services are listening sees avoidable 503s.
  .sort((a, b) => Number(a.name.includes('gateway')) - Number(b.name.includes('gateway')))
  .map((entry) => ({ name: entry.name, cwd: path.join(packagesDir, entry.name) }));

if (!services.length) {
  console.error('No service found. A service is packages/<name>/src/server.js');
  process.exit(1);
}

const children = [];
let stopping = false;

function stopAll(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) { try { child.kill(); } catch { /* already gone */ } }
  process.exit(code);
}

const isGateway = (name) => name.includes('gateway');
const gatewayService = services.find((s) => isGateway(s.name));
const internalServices = services.filter((s) => !isGateway(s.name));

const frontendPort = Number(process.env.VITE_PORT ?? 5173);
const gatewayPort = Number(process.env.PORT ?? 4000);
const FIRST_INTERNAL = Number(process.env.INTERNAL_PORT_BASE ?? 4001);
const addresses = {};
internalServices.forEach((service, index) => {
  const envKey = service.name.replace(/[^A-Za-z0-9]+/g, '_').toUpperCase() + '_PORT';
  const port = Number(process.env[envKey] ?? (FIRST_INTERNAL + index));
  if (port < 4001 || port > 4020) throw new Error(`${service.name} must use an internal port from 4001 to 4020`);
  addresses[service.name] = port;
});
if (gatewayPort !== 4000 || frontendPort !== 5173) {
  throw new Error('Local MERN development uses Vite 5173 and gateway 4000');
}
if (!existsSync('client/vite-dev.mjs') || !existsSync('client/static-preview.mjs')) {
  throw new Error('The client preview runners are missing');
}

// Claim the fixed local ports before starting the process tree. A stale
// listener must not redirect the preview or service URLs to another app.
await Promise.all([
  freePort(frontendPort),
  freePort(gatewayPort),
  ...Object.values(addresses).map(freePort),
]);

function spawnService(service, extraEnv = {}) {
  const child = spawn(process.execPath, ['src/server.js'], {
    cwd: service.cwd,
    env: { ...process.env, ...extraEnv },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.on('data', (chunk) => process.stdout.write('[' + service.name + '] ' + chunk));
  child.stderr.on('data', (chunk) => process.stderr.write('[' + service.name + '] ' + chunk));
  child.on('exit', (code) => {
    if (!stopping) console.error('[' + service.name + '] exited with code ' + code);
    stopAll(code ?? 1);
  });
  children.push(child);
}

for (const service of internalServices) {
  const port = String(addresses[service.name]);
  spawnService(service, { SERVICE_PORT: port, PORT: port });
}

if (gatewayService) {
  const gatewayEnv = { PORT: String(gatewayPort) };
  for (const [name, port] of Object.entries(addresses)) {
    const prefix = name.replace(/[^A-Za-z0-9]+/g, '_').toUpperCase();
    gatewayEnv[prefix + '_PORT'] = String(port);
    gatewayEnv[prefix + '_URL'] = 'http://127.0.0.1:' + port;
  }
  spawnService(gatewayService, gatewayEnv);
}

function spawnClient(entry = 'vite-dev.mjs') {
  const client = spawn(process.execPath, [entry], {
    cwd: 'client', env: { ...process.env, VITE_PORT: String(frontendPort), PORT: String(gatewayPort) },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  client.stdout.on('data', (chunk) => process.stdout.write('[client] ' + chunk));
  client.stderr.on('data', (chunk) => process.stderr.write('[client] ' + chunk));
  client.on('exit', (code) => {
    if (stopping) return;
    if (entry === 'vite-dev.mjs' && code && existsSync('client/dist/index.html')) {
      console.warn('[client] Vite dev unavailable; serving the last built bundle instead');
      spawnClient('static-preview.mjs');
      return;
    }
    console.error('[client] exited with code ' + code);
    stopAll(code ?? 1);
  });
  children.push(client);
}
spawnClient();

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
