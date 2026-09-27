import http from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import path from 'node:path';

// Serve the built Vite client on its local preview port while the gateway and
// service packages remain on 4000–4020. This also works when Vite's dev-only
// dependency optimizer cannot traverse a restricted parent directory.
const dist = path.resolve('dist');
const port = Number(process.env.VITE_PORT ?? 5173);
const gateway = Number(process.env.PORT ?? 4000);
if (!existsSync(path.join(dist, 'index.html'))) {
  throw new Error('Client bundle is missing; run npm run build first');
}

const types = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg', '.webp': 'image/webp', '.ico': 'image/x-icon',
  '.woff': 'font/woff', '.woff2': 'font/woff2', '.map': 'application/json',
};

http.createServer((request, response) => {
  const pathname = new URL(request.url, 'http://127.0.0.1').pathname;
  if (pathname === '/api' || pathname.startsWith('/api/')) {
    const upstream = http.request({ hostname: '127.0.0.1', port: gateway,
      path: request.url, method: request.method,
      headers: { ...request.headers, host: `127.0.0.1:${gateway}` } }, (reply) => {
      response.writeHead(reply.statusCode ?? 502, reply.headers);
      reply.pipe(response);
    });
    upstream.on('error', () => {
      if (!response.headersSent) response.writeHead(502, { 'Content-Type': 'text/plain' });
      response.end('API gateway unavailable');
    });
    request.pipe(upstream);
    return;
  }

  let decoded;
  try { decoded = decodeURIComponent(pathname); } catch { response.writeHead(400).end(); return; }
  const candidate = path.resolve(dist, '.' + decoded);
  if (candidate !== dist && !candidate.startsWith(dist + path.sep)) {
    response.writeHead(403).end();
    return;
  }
  const file = existsSync(candidate) && statSync(candidate).isFile()
    ? candidate : path.join(dist, 'index.html');
  response.writeHead(200, { 'Content-Type': types[path.extname(file)] ?? 'application/octet-stream' });
  createReadStream(file).pipe(response);
}).listen(port, '127.0.0.1', () => {
  console.log(`built Vite client listening on http://127.0.0.1:${port}`);
});
