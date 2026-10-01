import { spawnSync } from 'node:child_process';
import net from 'node:net';
import { pathToFileURL } from 'node:url';

const windows = process.platform === 'win32';

function listenerPids(port) {
  if (windows) {
    const result = spawnSync('netstat', ['-ano', '-p', 'tcp'], { encoding: 'utf8' });
    return [...new Set((result.stdout || '').split(/\r?\n/).flatMap((line) => {
      const bits = line.trim().split(/\s+/);
      if (bits.length < 5 || bits[3]?.toUpperCase() !== 'LISTENING') return [];
      const localPort = bits[1]?.match(/:(\d+)$/)?.[1];
      return localPort === String(port) && /^\d+$/.test(bits[4]) ? [Number(bits[4])] : [];
    }))];
  }
  const result = spawnSync('lsof', ['-ti', `tcp:${port}`, '-sTCP:LISTEN'], { encoding: 'utf8' });
  return [...new Set((result.stdout || '').trim().split(/\s+/)
    .filter((value) => /^\d+$/.test(value)).map(Number))];
}

function isOpen(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port });
    socket.once('connect', () => { socket.destroy(); resolve(true); });
    socket.once('error', () => resolve(false));
  });
}

/** Free only the process which is listening on this exact application port. */
export async function freePort(port) {
  if (!Number.isInteger(Number(port)) || Number(port) < 1024 || Number(port) > 65535) {
    throw new Error(`Invalid application port: ${port}`);
  }
  for (const pid of listenerPids(Number(port))) {
    if (windows) spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore' });
    else process.kill(pid, 'SIGTERM');
  }
  const deadline = Date.now() + 6000;
  while (await isOpen(Number(port)) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  if (await isOpen(Number(port))) throw new Error(`Port ${port} is still occupied.`);
}

// `file://${process.argv[1]}` never equals import.meta.url on Windows (drive letter,
// backslashes, percent-encoding), which silently turned this guard into a no-op.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const ports = process.argv.length > 2 ? process.argv.slice(2).map(Number)
    : [Number(process.env.PORT ?? 4000)];
  await Promise.all(ports.map(freePort));
}
