// Checks a MongoDB connection string the way a deployed application will use it: can the address be resolved,
// can the cluster be reached over the network, does it accept the credentials, does it answer a ping.
//
// The string arrives in the environment (CHECK_URI), never in the command line, and nothing that comes back
// contains it: what is printed is one JSON object with a plain-language message.
import { createRequire } from 'node:module';
import dns from 'node:dns/promises';
import net from 'node:net';
import path from 'node:path';
import tls from 'node:tls';

const uri = process.env.CHECK_URI || '';
const driverBase = process.env.DRIVER_BASE || '';
const done = (result) => { console.log(JSON.stringify(result)); process.exit(0); };

const secret = (uri.match(/^[a-z+]+:\/\/[^:@/]+:([^@/]+)@/i) || [])[1];
const scrub = (text) => {
  let clean = String(text ?? '');
  for (const value of [uri, secret, secret && decodeURIComponent(secret)]) if (value && (value === uri || value.length >= 6)) clean = clean.split(value).join('<hidden>');
  return clean.replace(/\/\/[^/@\s]+:[^@\s]+@/g, '//<credentials>@');
};

const parsed = uri.match(/^mongodb(\+srv)?:\/\/(?:[^@/]*@)?([^/?]+)(\/[^?]*)?/i);
if (!parsed) done({ ok: false, stage: 'parse', message: 'That is not a MongoDB connection string. It starts with mongodb:// or mongodb+srv://.' });
const srv = Boolean(parsed[1]);
const hosts = parsed[2].split(',');
const database = (parsed[3] || '').replace(/^\//, '');

// 1. Where is it? An SRV name is looked up; a plain list is taken as written.
let targets = [];
try {
  if (srv) {
    targets = (await dns.resolveSrv(`_mongodb._tcp.${hosts[0]}`)).map((row) => ({ host: row.name, port: row.port }));
  } else {
    targets = hosts.map((host) => { const [name, port] = host.split(':'); return { host: name, port: Number(port) || 27017 }; });
  }
} catch (error) {
  done({ ok: false, stage: 'dns', message: `The cluster's address could not be found (${scrub(error.code || error.message)}). Check the host name in the string.` });
}

// 2. Can it be reached from here? Atlas needs TLS; a plain mongodb:// host on a private network may not.
const secure = srv || /[?&]tls=true|[?&]ssl=true/i.test(uri);
const reach = (target) => new Promise((resolve) => {
  const socket = (secure ? tls.connect : net.connect)({ host: target.host, port: target.port, servername: target.host, timeout: 7000 });
  socket.once(secure ? 'secureConnect' : 'connect', () => { socket.destroy(); resolve(true); });
  socket.once('timeout', () => { socket.destroy(); resolve(false); });
  socket.once('error', () => resolve(false));
});
const answers = await Promise.all(targets.slice(0, 3).map(reach));
if (!answers.some(Boolean)) {
  done({ ok: false, stage: 'network', message: 'The cluster did not answer from this computer. Its network access list may not allow this address, or the address is wrong. For a deployment the list must also allow the host (for Vercel that means 0.0.0.0/0).' });
}

// 3. Does it accept the credentials? That needs the MongoDB driver, which any built project already has.
let mongodb;
try {
  mongodb = createRequire(path.join(driverBase, 'package.json'))('mongodb');
} catch {
  done({ ok: true, verified: false, stage: 'network', message: 'The cluster answers over the network, but the username and password were not checked: no MongoDB driver was found on this computer (one is installed when a project is built).' });
}

const client = new mongodb.MongoClient(uri, { serverSelectionTimeoutMS: 10000, connectTimeoutMS: 10000 });
try {
  await client.connect();
  await client.db('admin').command({ ping: 1 });
  const info = await client.db('admin').command({ buildInfo: 1 }).catch(() => ({}));
  const warnings = [];
  if (!database) warnings.push('The string names no database, so the application would use the default one (test). Add a name after the host, for example …mongodb.net/myapp?…');
  done({ ok: true, verified: true, stage: 'ping', message: 'Connected and signed in.', server_version: info.version || '', database: database || 'test', warnings });
} catch (error) {
  const text = scrub(error.message);
  if (/auth/i.test(error.codeName || '') || /authentication failed|bad auth/i.test(text) || error.code === 18) {
    done({ ok: false, stage: 'auth', message: 'The cluster answered but refused the username or password. Check the database user in Atlas → Database Access.' });
  }
  if (/whitelist|allow ?list|not allowed|ip that isn/i.test(text)) {
    done({ ok: false, stage: 'access', message: "The cluster refused this computer's address. In Atlas → Network Access add an entry for it; a deployment on Vercel needs 0.0.0.0/0." });
  }
  done({ ok: false, stage: 'connect', message: `The cluster could not be used: ${text.slice(0, 220)}` });
} finally {
  await client.close().catch(() => {});
}
