import pg from 'pg';

/**
 * The one thing every suite that touches Postgres directly needs, written once.
 *
 * Tests never run against this project's real Supabase project: that project is real, the same one
 * shown in the Supabase dashboard, and a test truncating its tables would delete somebody's actual
 * data. This connects straight to the *local* Supabase stack's own Postgres instead (`supabase
 * start`), and refuses anything that is not a loopback address before touching it. Most component
 * and page tests do not need this at all - they mock `lib/supabase.js` instead; reach for this only
 * for a suite that is really testing a migration or an RLS policy against a live Postgres.
 */
const TEST_DATABASE_URL = process.env.TEST_DATABASE_URL ?? 'postgresql://postgres:postgres@127.0.0.1:54322/postgres';

function assertLocalTestServer(url) {
  const hostname = new URL(url.replace(/^postgres(ql)?:/, 'http:')).hostname;
  if (!['127.0.0.1', 'localhost', '::1'].includes(hostname)) {
    throw new Error(
      `Refusing to run tests against "${hostname}": a test database must be local (127.0.0.1), `
      + "never the project's real Supabase project. Run `supabase start` and leave "
      + 'TEST_DATABASE_URL unset.',
    );
  }
}

let pool;

/** One connection pool per process, to the local stack only. */
export function testDb() {
  assertLocalTestServer(TEST_DATABASE_URL);
  pool ??= new pg.Pool({ connectionString: TEST_DATABASE_URL });
  return pool;
}

/**
 * Truncate every table in the `public` schema.
 *
 * Call it in `beforeEach`, not `beforeAll`: a row left behind changes the next test's result, and
 * that failure reads as a defect in the code under test rather than in the fixture.
 */
export async function clearTables() {
  const db = testDb();
  const { rows } = await db.query("select tablename from pg_tables where schemaname = 'public'");
  if (!rows.length) return;
  const names = rows.map((row) => `"${row.tablename}"`).join(', ');
  await db.query(`truncate table ${names} restart identity cascade`);
}

/** Close in `afterAll`, or the runner hangs on an open handle. */
export async function closeTestDb() {
  await pool?.end();
  pool = undefined;
}
