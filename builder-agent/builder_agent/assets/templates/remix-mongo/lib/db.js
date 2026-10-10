import mongoose from 'mongoose';

/**
 * One connection, cached across module re-evaluation.
 *
 * Remix re-evaluates modules on every hot reload in development, and a plain module-level `let`
 * would open a new connection each time until the pool is exhausted: the symptom is timeouts that
 * look like slow queries. The cache lives on globalThis because that is the one thing a reload
 * does not reset.
 *
 * Server code only: import this from a `loader`, an `action` or a `*.server.js` module, never from
 * code a browser runs. The browser never talks to the database.
 */
const cache = globalThis.__mongoose ?? (globalThis.__mongoose = { conn: null, promise: null });

// Wait 10s for the cluster rather than the driver's 30s, so a paused or unreachable cluster says so while a page or a
// health check still waits; and keep the pool small, because each serverless instance holds one of its own and a free
// Atlas cluster has a few hundred connections in all.
const OPTIONS = { bufferCommands: false, serverSelectionTimeoutMS: 10_000, maxPoolSize: 10 };

function connectionString(uri) {
  // A value piped through a shell or pasted in a dashboard can arrive with whitespace or a newline, which the driver refuses.
  const given = typeof uri === 'string' ? uri.trim() : '';
  if (given) return given;
  // Deployed without MONGODB_URI: say so, rather than quietly trying a database on the host itself that is not there.
  if (process.env.NODE_ENV === 'production' && !process.env.ALLOW_LOCAL_MONGODB) {
    throw new Error("MONGODB_URI is not set: add it to the environment variables of this deployment.");
  }
  return 'mongodb://127.0.0.1:27017/__APP_DB__';
}

export async function connectDb(uri = process.env.MONGODB_URI) {
  if (cache.conn) return cache.conn;
  // A caller that already connected (the test helper opens the project's own `_test`
  // database) owns that connection. Calling `mongoose.connect` again with another URI
  // fails ("Can't call openUri() on an active connection with different connection
  // strings"), and reusing it is what keeps tests off the application's database.
  if (mongoose.connection.readyState === 1) {
    cache.conn = mongoose.connection;
    return cache.conn;
  }
  cache.promise ??= mongoose.connect(connectionString(uri), OPTIONS);
  try {
    cache.conn = await cache.promise;
  } catch (error) {
    // A failed attempt must not be cached, or every later request replays it.
    cache.promise = null;
    throw error;
  }
  return cache.conn;
}

export async function disconnectDb() {
  if (mongoose.connection.readyState !== 0) await mongoose.disconnect();
  cache.conn = null;
  cache.promise = null;
}
