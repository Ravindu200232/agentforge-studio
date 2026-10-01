import mongoose from 'mongoose';

/**
 * The three things every suite that touches MongoDB needs, written once.
 *
 * Copied into each test file instead, they drift: one file forgets to clear
 * between tests, another connects per test and exhausts the pool, and the
 * failures read as product bugs in whichever suite happens to run second.
 *
 * Tests get a database of their own. This helper deliberately does NOT read
 * `MONGODB_URI`: that is the application's database, and `clearCollections()`
 * deletes every document in whatever it is connected to. Set `TEST_MONGODB_URI`
 * to use another server; its database name must end in `_test`, and anything else
 * is refused before a single document is touched.
 */
const TEST_URI = process.env.TEST_MONGODB_URI ?? 'mongodb://127.0.0.1:27017/__APP_DB___test';

const databaseName = (uri) => decodeURIComponent(uri.split('?')[0].replace(/\/+$/, '').split('/').pop() ?? '');

function assertTestDatabase(name) {
  if (!name.endsWith('_test')) {
    throw new Error(
      `Refusing to use database "${name}": a test database's name must end in "_test". `
      + 'Unset TEST_MONGODB_URI, or point it at a database such as "myapp_test".',
    );
  }
}

/** Connect once per process. `readyState` 1 is connected, 0 is disconnected. */
export async function connectTestDb(uri = TEST_URI) {
  assertTestDatabase(databaseName(uri));
  if (mongoose.connection.readyState === 1) {
    assertTestDatabase(mongoose.connection.name);
    return mongoose.connection;
  }
  await mongoose.connect(uri);
  return mongoose.connection;
}

/**
 * Empty every collection.
 *
 * Call it in `beforeEach`, not `beforeAll`: a document left behind changes the
 * next test's result, and that failure reads as a defect in the code under
 * test rather than in the fixture.
 */
export async function clearCollections() {
  assertTestDatabase(mongoose.connection.name);
  const { collections } = mongoose.connection;
  await Promise.all(Object.values(collections).map((collection) => collection.deleteMany({})));
}

/** Close in `afterAll`, or the runner hangs on an open handle. */
export async function closeTestDb() {
  if (mongoose.connection.readyState !== 0) await mongoose.disconnect();
}

/**
 * The server's app is a value, so a suite drives it with supertest and never
 * binds a port. `createApp()` in `server/src/app.js` is what makes this possible.
 */
export { default as request } from 'supertest';
