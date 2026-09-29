# Scaffolded from the verified Vite + Supabase template

Everything here was installed, unit-tested, built and previewed in a browser
before it was made a template. Build the application on top of it.

    npm install
    npm run dev
    npm test
    npm run qa:inventory   # which page and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build && npm run start

This app has **no server of its own**. `src/lib/supabase.js` holds the one browser client, built
from `VITE_SUPABASE_URL`/`VITE_SUPABASE_ANON_KEY` (this project's own Supabase project, connected
for real when the stack was picked in Build setup - AgentForge sets these automatically). There is
no service-role key anywhere in this project, and there must never be one: every `VITE_*` variable
is compiled into the public bundle, so **Row Level Security is this application's entire security
boundary** — every table a signed-in or anonymous user can reach through `supabase.from(...)` needs
a correct RLS policy in `supabase/migrations/`, applied with `supabase db push`. A missing policy is
a security bug, not a missing feature.

`scripts/seed.mjs` is the one place `SUPABASE_SERVICE_ROLE_KEY` is used — it's a plain Node script,
never bundled into the browser build.
