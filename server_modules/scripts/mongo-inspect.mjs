// What a MongoDB database holds, read through the application's own driver: its databases, collections, indexes,
// GridFS buckets, or a few documents of one collection.
//
// The connection string arrives in the environment (CHECK_URI), never on the command line, and nothing printed
// contains it: the answer is one JSON object. The action is the first argument (overview, collections, indexes,
// gridfs, rows); the database, collection and row count come from INSPECT_DATABASE, INSPECT_COLLECTION, INSPECT_LIMIT.
import { createRequire } from 'node:module';
import path from 'node:path';

const uri = process.env.CHECK_URI || '';
const driverBase = process.env.DRIVER_BASE || '';
const action = process.argv[2] || 'overview';
const done = (result) => { console.log(JSON.stringify(result)); process.exit(0); };

const secret = (uri.match(/^[a-z+]+:\/\/[^:@/]+:([^@/]+)@/i) || [])[1];
const scrub = (text) => {
  let clean = String(text ?? '');
  for (const value of [uri, secret, secret && decodeURIComponent(secret)]) if (value && (value === uri || value.length >= 6)) clean = clean.split(value).join('<hidden>');
  return clean.replace(/\/\/[^/@\s]+:[^@\s]+@/g, '//<credentials>@');
};
const fail = (stage, message) => done({ ok: false, action, stage, message: scrub(message) });

const parsed = uri.match(/^mongodb(\+srv)?:\/\/(?:[^@/]*@)?([^/?]+)(\/[^?]*)?/i);
if (!parsed) fail('parse', 'No MongoDB connection string is saved for this project.');
const hosts = parsed[2].split(',');
const appDatabase = decodeURIComponent((parsed[3] || '').replace(/^\//, '')) || 'test';

// A name the database itself would accept, never an operator or a path.
const NAME = /^[A-Za-z0-9_.\- ]{1,120}$/;
const database = process.env.INSPECT_DATABASE || appDatabase;
if (!NAME.test(database)) fail('input', 'That is not a database name.');
const limit = Math.min(Math.max(Number(process.env.INSPECT_LIMIT) || 20, 1), 100);

let mongodb;
try {
  mongodb = createRequire(path.join(driverBase, 'package.json'))('mongodb');
} catch {
  fail('driver', 'No MongoDB driver was found: it is installed when a MongoDB project is built.');
}

// Fields that hold credentials are shown as masked, whatever the collection.
const SENSITIVE = /(pass(word|wd)?|secret|token|hash|salt|otp|api[_-]?key|private|credential)/i;
const masked = new Set();
const mask = (value, key = '') => {
  if (key && SENSITIVE.test(key) && value !== null && value !== undefined && typeof value !== 'object') { masked.add(key); return '<masked>'; }
  if (Array.isArray(value)) return value.map((item) => mask(item));
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, mask(v, k)]));
  return value;
};

const settle = async (promise, fallback = null) => { try { return await promise; } catch { return fallback; } };

async function collectionStats(db, name) {
  const [stats] = await settle(db.collection(name).aggregate([{ $collStats: { storageStats: {} } }]).toArray(), []) || [];
  const storage = stats?.storageStats || {};
  const count = storage.count ?? await settle(db.collection(name).estimatedDocumentCount(), null);
  const indexes = await settle(db.collection(name).indexes(), []);
  return {
    count, bytes: storage.size ?? null, storage_bytes: storage.storageSize ?? null,
    average_document_bytes: storage.avgObjSize ?? null, index_bytes: storage.totalIndexSize ?? null,
    indexes: storage.nindexes ?? indexes.length,
  };
}

const client = new mongodb.MongoClient(uri, { serverSelectionTimeoutMS: 12000, connectTimeoutMS: 12000 });
try {
  await client.connect();
  const db = client.db(database);

  if (action === 'overview') {
    const admin = client.db('admin');
    const info = await settle(admin.command({ buildInfo: 1 }), {});
    const hello = await settle(admin.command({ hello: 1 }), {});
    const listed = await settle(admin.command({ listDatabases: 1 }), null);
    const names = listed ? listed.databases : [{ name: database }];
    const stats = await settle(db.command({ dbStats: 1 }), {});
    done({
      ok: true, action, server_version: info.version || '', host: hosts[0], srv: Boolean(parsed[1]),
      replica_set: hello.setName || '', members: (hello.hosts || []).length, writable: Boolean(hello.isWritablePrimary),
      app_database: appDatabase,
      database: {
        name: database, collections: stats.collections ?? null, views: stats.views ?? null, documents: stats.objects ?? null,
        data_bytes: stats.dataSize ?? null, storage_bytes: stats.storageSize ?? null, indexes: stats.indexes ?? null,
        index_bytes: stats.indexSize ?? null,
      },
      databases: names.map((row) => ({ name: row.name, bytes: row.sizeOnDisk ?? null, empty: Boolean(row.empty), app: row.name === appDatabase }))
        .sort((a, b) => Number(b.app) - Number(a.app) || (b.bytes || 0) - (a.bytes || 0)),
    });
  }

  if (action === 'collections') {
    const listed = await db.listCollections({}, { nameOnly: false }).toArray();
    const rows = [];
    for (const item of listed.sort((a, b) => a.name.localeCompare(b.name))) {
      const view = item.type === 'view';
      rows.push({
        name: item.name, type: item.type || 'collection', capped: Boolean(item.options?.capped),
        validator: Boolean(item.options?.validator), time_series: Boolean(item.options?.timeseries),
        gridfs: /\.(files|chunks)$/.test(item.name),
        ...(view ? { count: null, indexes: 0 } : await collectionStats(db, item.name)),
      });
    }
    done({ ok: true, action, database, collections: rows });
  }

  if (action === 'indexes') {
    const listed = await db.listCollections({ type: 'collection' }, { nameOnly: true }).toArray();
    const rows = [];
    for (const { name } of listed.sort((a, b) => a.name.localeCompare(b.name))) {
      const usage = Object.fromEntries((await settle(db.collection(name).aggregate([{ $indexStats: {} }]).toArray(), []))
        .map((row) => [row.name, Number(row.accesses?.ops ?? 0)]));
      for (const index of await settle(db.collection(name).indexes(), [])) {
        rows.push({
          collection: name, name: index.name, keys: Object.entries(index.key).map(([k, v]) => `${k}: ${v}`).join(', '),
          unique: index.name === '_id_' || Boolean(index.unique), sparse: Boolean(index.sparse), ttl_seconds: index.expireAfterSeconds ?? null,
          partial: Boolean(index.partialFilterExpression), uses: usage[index.name] ?? null,
        });
      }
    }
    done({ ok: true, action, database, indexes: rows });
  }

  if (action === 'gridfs') {
    const listed = await db.listCollections({}, { nameOnly: true }).toArray();
    const buckets = [];
    for (const { name } of listed.filter((row) => row.name.endsWith('.files'))) {
      const bucket = name.slice(0, -'.files'.length);
      const [totals] = await settle(db.collection(name).aggregate([
        { $group: { _id: null, files: { $sum: 1 }, bytes: { $sum: '$length' }, last: { $max: '$uploadDate' } } },
      ]).toArray(), []) || [];
      buckets.push({ name: bucket, files: totals?.files ?? 0, bytes: totals?.bytes ?? 0, last_upload: totals?.last ?? null,
                     chunks: await settle(db.collection(`${bucket}.chunks`).estimatedDocumentCount(), null) });
    }
    done({ ok: true, action, database, buckets });
  }

  if (action === 'rows') {
    const name = process.env.INSPECT_COLLECTION || '';
    if (!name || name.startsWith('system.') || name.includes('$') || name.length > 120) fail('input', 'That is not a collection of this database.');
    const exists = await db.listCollections({ name }, { nameOnly: true }).toArray();
    if (!exists.length) fail('input', `There is no collection called ${name} in ${database}.`);
    const documents = await db.collection(name).find({}).sort({ _id: -1 }).limit(limit).toArray();
    const plain = JSON.parse(mongodb.BSON.EJSON.stringify(documents, { relaxed: true }));
    const rows = plain.map((row) => mask(row));
    const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
    done({ ok: true, action, database, collection: name, columns, rows, masked: [...masked],
           total: await settle(db.collection(name).estimatedDocumentCount(), null) });
  }

  fail('input', `There is no ${action} action.`);
} catch (error) {
  const text = scrub(error.message);
  if (/auth/i.test(error.codeName || '') || /authentication failed|bad auth/i.test(text) || error.code === 18) {
    fail('auth', 'The cluster refused the saved username or password.');
  }
  fail('connect', `The database could not be read: ${text.slice(0, 240)}`);
} finally {
  await client.close().catch(() => {});
}
