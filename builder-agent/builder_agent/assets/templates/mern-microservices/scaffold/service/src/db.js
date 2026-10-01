import mongoose from 'mongoose';

/**
 * One connection per process, created on demand.
 *
 * Connecting per request or per test exhausts the pool and produces timeouts
 * that look like slow queries. readyState 1 is connected, 0 is disconnected.
 */
export async function connectDb(uri) {
  if (mongoose.connection.readyState === 1) return mongoose.connection;
  await mongoose.connect(uri);
  return mongoose.connection;
}

export async function disconnectDb() {
  if (mongoose.connection.readyState !== 0) await mongoose.disconnect();
}
