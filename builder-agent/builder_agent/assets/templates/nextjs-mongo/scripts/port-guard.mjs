import net from 'node:net';
import { pathToFileURL } from 'node:url';

function isOpen(port) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: '127.0.0.1', port });
    socket.once('connect', () => { socket.destroy(); resolve(true); });
    socket.once('error', () => resolve(false));
  });
}

/** Never terminate another app: Studio allocates a different private preview port. */
export async function freePort(port) {
  if (!Number.isInteger(Number(port)) || Number(port) < 1024 || Number(port) > 65535) {
    throw new Error(`Invalid application port: ${port}`);
  }
  if (await isOpen(Number(port))) {
    throw new Error(`Port ${port} is occupied. Let Studio allocate a different preview port.`);
  }
}

// `file://${process.argv[1]}` never equals import.meta.url on Windows (drive letter,
// backslashes, percent-encoding), which silently turned this guard into a no-op.
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const ports = process.argv.slice(2).map(Number);
  await Promise.all(ports.map(freePort));
}
