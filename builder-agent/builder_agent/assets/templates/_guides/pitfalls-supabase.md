# Supabase pitfalls - read after pitfalls.md (stacks that use Supabase)

## Supabase and test data

- **Tests never use the project's real Supabase project.** `test/helpers/db.js` connects straight to the *local* Postgres (`supabase start`, port 54322) and refuses anything that is not a loopback address, because `clearTables()` truncates every table it finds. It deliberately does not read `SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY` for this reason. Symptoms of getting this wrong: a unique-constraint violation on data another suite just wrote, tests passing only once.
- Every generated app has its own real Supabase project (created once when the stack was chosen; see `.env.example`, `lib/supabase.js`) — the old shared local default let apps clobber each other. **Never** truncate or delete against the real project's URL from a test.
- Suites using `test/helpers/db.js` share that one local Postgres, so they run one after another (`fileParallelism: false` is set). Do not turn it back on.
- Every table an app reads or writes needs a Row Level Security policy before it holds real data; a missing one is a security bug, not a missing feature (most true on the Vite-only stacks, which have no server to fall back on).

## By stack

- **Next.js + Supabase**: `middleware.js` runs on the **Edge runtime** and refreshes the Auth session cookie on every request — do not remove it or gate it behind a route matcher that skips real pages. `lib/supabase.js`'s `supabaseAdmin()` (service-role) is server code only; keep it out of anything a Client Component imports.
- **Remix + Supabase**: build `lib/supabase.js`'s `supabaseServer(request, headers)` fresh per `loader`/`action` and copy its `headers` onto the response, or a refreshed session is silently dropped. `remix-serve` reads `PORT`.
- **Vite + Supabase (plain or with microservices)**: there is no server, so `SUPABASE_SERVICE_ROLE_KEY` must never be imported anywhere in `src/` — every `VITE_*` variable ends up in the public bundle. RLS is this app's only security boundary; anything needing the service-role key belongs in a Supabase Edge Function instead (the microservices variant), never in client code.
- **The two microservices stacks**: a "service" is a Supabase Edge Function under `supabase/functions/<name>/`, not an Express process — there is no gateway and no internal port scheme, and `supabase functions serve` (part of `supabase start`) runs them locally. Test a function's own logic directly; an E2E journey calls it the same way the app does, through `supabase.functions.invoke(...)`.
