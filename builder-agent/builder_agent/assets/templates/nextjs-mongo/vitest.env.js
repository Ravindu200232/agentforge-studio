/**
 * Environment for every suite, imported before the code under test (vitest.config.js, setupFiles).
 *
 * Tests get the project's own `_test` database. Code under test that connects by itself
 * (`connectDb()` reads MONGODB_URI) must land there too, whatever is exported in the shell.
 * Set a secret or a URI here, and never "restore" it by deleting it in an `afterAll`:
 * that hands the next test file an unconfigured app.
 */
process.env.TEST_MONGODB_URI ??= 'mongodb://127.0.0.1:27017/__APP_DB___test';
process.env.MONGODB_URI = process.env.TEST_MONGODB_URI;
process.env.SESSION_SECRET ??= 'test-session-secret-not-a-live-value-0123456789';
