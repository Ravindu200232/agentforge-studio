# Supabase pitfalls - read after pitfalls.md (stacks that use Supabase)

## Supabase and test data

- **Tests never use the project's real Supabase project.** `test/helpers/db.js` connects straight to the *local* Postgres (`supabase start`, port 54322) and refuses anything that is not a loopback address, because `clearTables()` truncates every table it finds. It deliberately does not read `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` for this reason. Symptoms of getting this wrong: a unique-constraint violation on data another suite just wrote, tests passing only once.
- Every generated app has its own real Supabase project (created once when the stack was chosen; see `.env.example`, `lib/supabase.js`) — the old shared local default let apps clobber each other. **Never** truncate or delete against the real project's URL from a test.
- Suites using `test/helpers/db.js` share that one local Postgres, so they run one after another (`fileParallelism: false` is set). Do not turn it back on.
- Every table an app reads or writes needs a Row Level Security policy before it holds real data; a missing one is a security bug, not a missing feature (most true on the Vite-only stacks, which have no server to fall back on).

## By stack

- **Next.js + Supabase**: use the request hook documented for the installed Next.js version to refresh the Auth session for protected routes. Keep the Supabase admin client in server-only code.
- **Remix + Supabase**: build `lib/supabase.js`'s `supabaseServer(request, headers)` fresh per `loader`/`action` and copy its `headers` onto the response, or a refreshed session is silently dropped. `remix-serve` reads `PORT`.
- **Vite + Supabase**: keep `SUPABASE_SERVICE_ROLE_KEY` out of `src/` and public `VITE_*` variables. Protect client database access with RLS. Use an authorized Supabase Edge Function for any operations that require server privileges.
- Set `project_id` in `supabase/config.toml` from the workspace's project slug when using the Supabase CLI.
