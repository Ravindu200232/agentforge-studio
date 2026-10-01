import { spawn } from 'node:child_process';
import { readdirSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import net from 'node:net';
import path from 'node:path';
import process from 'node:process';

/**
 * Start every service, the gateway and the Vite client locally, with no Docker and no process
 * manager. One Ctrl-C stops everything.
 *
 * PORT is the one port a browser opens - the Vite client here, the gateway in production
 * (`npm start`). The AgentForge Studio gives every project's preview a private PORT of its own,
 * so nothing here may insist on a fixed number: the gateway and the services take free ports
 * (4000 and 4001+ when they are free), and each is told where the others are. Run directly, with
 * no PORT given, the client is on VITE_PORT or 5173.
 *
 * The service list is read from the workspace rather than written here, so adding a package is
 * the only step needed to run it.
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

const taken = new Set();

/** `preferred` when nothing listens there, else any free port; never one already handed out. */
function freePort(preferred = 0) {
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
      if (port && taken.has(port)) continue;
      const found = await tryPort(port);
      if (found && !taken.has(found)) {
        taken.add(found);
        return found;
      }
    }
    throw new Error('No free local port is available for the services.');
  })();
}

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
if (!existsSync('client/vite-dev.mjs') || !existsSync('client/static-preview.mjs')) {
  throw new Error('The client preview runners are missing');
}

const isGateway = (name) => name.includes('gateway');
const gatewayService = services.find((s) => isGateway(s.name));
const internalServices = services.filter((s) => !isGateway(s.name));
const envName = (name) => name.replace(/[^A-Za-z0-9]+/g, '_').toUpperCase();

const frontendPort = Number(givenPort || process.env.VITE_PORT || 5173);
taken.add(frontendPort);
const gatewayPort = await freePort(Number(process.env.GATEWAY_PORT || (givenPort ? 0 : process.env.PORT) || 4000));
const firstInternal = Number(process.env.INTERNAL_PORT_BASE || 4001);
const addresses = {};
for (const [index, service] of internalServices.entries()) {
  addresses[service.name] = await freePort(Number(process.env[envName(service.name) + '_PORT'] || firstInternal + index));
}

// Every package gets the whole address map: the gateway to route to the services, and a service
// that asks a sibling for something (an order reading a price) without guessing a port.
const addressEnv = { GATEWAY_PORT: String(gatewayPort), GATEWAY_URL: 'http://127.0.0.1:' + gatewayPort };
for (const [name, port] of Object.entries(addresses)) {
  addressEnv[envName(name) + '_PORT'] = String(port);
  addressEnv[envName(name) + '_URL'] = 'http://127.0.0.1:' + port;
}

// The Studio shows which parts are listening and can start one that is not, so it is told where each part should be
// and how it is run. Only when it asks (AGENTFORGE_PORTS_FILE); the address map is all it gets, nothing secret.
const portsFile = process.env.AGENTFORGE_PORTS_FILE;
if (portsFile) {
  const folder = (cwd) => cwd.split(path.sep).join('/');
  const ports = [
    { name: 'client', kind: 'client', port: frontendPort, cwd: 'client', command: 'node vite-dev.mjs',
      env: { VITE_PORT: String(frontendPort), PORT: String(gatewayPort) } },
    ...(gatewayService ? [{ name: gatewayService.name, kind: 'gateway', port: gatewayPort, cwd: folder(gatewayService.cwd),
                            command: 'node src/server.js', env: { ...addressEnv, PORT: String(gatewayPort) } }] : []),
    ...internalServices.map((service) => ({
      name: service.name, kind: 'service', port: addresses[service.name], cwd: folder(service.cwd), command: 'node src/server.js',
      env: { ...addressEnv, SERVICE_PORT: String(addresses[service.name]), PORT: String(addresses[service.name]) },
    })),
  ];
  try {
    mkdirSync(path.dirname(portsFile), { recursive: true });
    writeFileSync(portsFile, JSON.stringify({ written_at: new Date().toISOString(),
      runtime: process.env.AGENTFORGE_PREVIEW_RUNTIME_ID || '', ports }, null, 2));
  } catch { /* the Studio's view only: the app runs without it */ }
}

const children = [];
let stopping = false;

function stopAll(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) { try { child.kill(); } catch { /* already gone */ } }
  process.exit(code);
}

function spawnService(service, extraEnv = {}) {
  const child = spawn(process.execPath, ['src/server.js'], {
    cwd: service.cwd,
    env: { ...process.env, ...addressEnv, ...extraEnv },
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
if (gatewayService) spawnService(gatewayService, { PORT: String(gatewayPort) });

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
console.log(`client http://127.0.0.1:${frontendPort} · gateway ${gatewayPort} · `
  + Object.entries(addresses).map(([name, port]) => `${name} ${port}`).join(' · '));

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
