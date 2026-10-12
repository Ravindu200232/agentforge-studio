# Scaffolded from the verified Next.js + Supabase template

Everything here was installed, unit-tested, seeded, built, started and opened
in a browser before it was made a template. Build the application on top of it.

    npm install
    npm run dev
    npm test
    npm run qa:inventory   # which page, route and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build && npm start

This project's own Supabase project already exists (created for real when the Supabase stack was
picked in Build setup) - `SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`
and `SUPABASE_SERVICE_ROLE_KEY` are set automatically for every command run here.

`lib/supabase.js` holds the three clients (`supabaseServer()`, `supabaseBrowser()`,
`supabaseAdmin()`) - import the right one rather than calling `createClient` anywhere else.
`middleware.js` refreshes the Auth session cookie on every request; do not remove it. Tables and
Row Level Security policies go in `supabase/migrations/`, applied with `supabase db push`; a table
with no RLS policy is a security bug. Any page or route handler that reads the database needs
`export const dynamic = 'force-dynamic'`.
