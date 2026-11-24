# Remix + Supabase build prompt

Author a Remix/Vite app at the workspace root. Write the manifest with @remix-run/serve, Vite configuration, app/root and route modules. Build to build/server/index.js and serve it on PORT. Add request-scoped Supabase Auth, private server utilities, RLS migrations and an idempotent seed.

The project's own Supabase project is already connected (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` in `.env` — created for real by the build setup step, never pasted by hand). Implement every approved screen as a route and every form with actual validated `action` behavior, using Supabase's own surface rather than reinventing it: Postgres tables migrated with `supabase db push` and protected by RLS policies (never the service-role key from anything a browser can trigger without a server check), `supabase.auth.*` for sign-in and sessions (passed to the client only through a loader's small `ENV` object, never by exposing the whole environment), Storage buckets with their own RLS for uploads, and Realtime/Edge Functions only where the specification calls for them. Use the selected Remix, Vite and Tailwind pipeline.

The Studio starts the local Remix preview on an isolated port for this project. It supplies `PORT`; do not hard-code a port and do not stop another project's preview when switching projects.
