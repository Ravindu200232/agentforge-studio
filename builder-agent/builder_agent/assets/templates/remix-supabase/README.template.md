# Scaffolded from the verified Remix + Supabase template

Everything here was installed, unit-tested, built, started and served before it
was made a template. Build the application on top of it.

    npm install
    npm run dev
    npm test
    npm run qa:inventory   # which page, route and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build && npm start

This is **Remix v2 on Vite**, so there is no `remix.config.js` — the
framework's options are the `remix()` plugin's in `vite.config.js`, and a file
of that name is ignored.

A route is a file under `app/routes/`. `_index.jsx` serves `/`; a dot in a
filename is a path separator, and a leading underscore is a segment that does
not appear in the URL.

This project's own Supabase project already exists (created for real when the Supabase stack was
picked in Build setup) - `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are set
automatically for every command run here. `lib/supabase.js` holds `supabaseServer()` (build one per
request from `request`, apply its `headers` to what the loader/action returns),
`supabaseBrowser(env)` (for a Client Component, given the `ENV` `app/root.jsx`'s loader passes
down), and `supabaseAdmin()` (service-role, server code only). Tables and Row Level Security
policies go in `supabase/migrations/`, applied with `supabase db push`; a table with no RLS policy
is a security bug.

`vitest.config.js` does not load the Remix plugin, on purpose: it rewrites
route modules for the framework's loader/action split and expects a Remix
request in flight, which under the test runner there is not.
