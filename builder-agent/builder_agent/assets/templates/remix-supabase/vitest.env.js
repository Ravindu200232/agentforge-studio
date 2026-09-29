/**
 * Environment for every suite, imported before the code under test (vitest.config.js, setupFiles).
 *
 * A test never sees this project's real Supabase URL and keys, even though AgentForge injects them
 * for every other command: `lib/supabase.js` reads `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` from
 * the environment, and if a suite imported it unmocked with the real values still set, it would
 * read and write the real project. Pointing them at the local stack means an unmocked import fails
 * closed (a clear connection error) instead of silently reaching production - a suite that needs a
 * live local Supabase client sets TEST_SUPABASE_ANON_KEY/TEST_SUPABASE_SERVICE_ROLE_KEY itself from
 * `supabase start`'s own printed output. `test/helpers/db.js` bypasses this entirely and talks to
 * the local Postgres directly.
 */
process.env.SUPABASE_URL = 'http://127.0.0.1:54321';
process.env.SUPABASE_ANON_KEY = process.env.TEST_SUPABASE_ANON_KEY ?? '';
process.env.SUPABASE_SERVICE_ROLE_KEY = process.env.TEST_SUPABASE_SERVICE_ROLE_KEY ?? '';
process.env.SESSION_SECRET ??= 'test-session-secret-not-a-live-value-0123456789';
