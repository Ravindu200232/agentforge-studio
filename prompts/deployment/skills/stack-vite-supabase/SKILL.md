---
name: stack-vite-supabase
description: What a Vite + React SPA on Supabase needs to deploy well on any target: static build output, the anon key and RLS as the whole security boundary, environment, health, and the questions to ask the customer.
---

# Deploying a Vite + Supabase application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to a
Vite + React single-page app that talks to Supabase (Postgres, Auth, Storage) directly from the browser,
with no application server of its own. It applies to every target: Vercel, Netlify, AWS EC2, AWS ECS,
Azure App Service and GitHub (Pages or otherwise) — this stack is a static bundle, so it is the easiest
of the five to host anywhere.

## What to read in the project

`package.json` (scripts, lockfile), `vite.config.*`, `src/lib/supabase.js` (how the single browser
client is created — there is only ever one, unlike the SSR stacks), `src/` for anywhere Auth state is
read, `supabase/migrations/` (the schema and, critically, the RLS policies — they are the *only* access
control this stack has), `.env.example`.

## Build and run facts

- Build: `npm run build` produces a static `dist/` folder. There is no server process to start; every
  target here serves static files (Vercel/Netlify build and host it directly; EC2/ECS/Azure serve
  `dist/` from nginx or a static file server in the same container/instance; GitHub serves it from Pages
  or alongside a separate API).
- **Every environment variable in this app is public.** `VITE_SUPABASE_URL` and
  `VITE_SUPABASE_ANON_KEY` are compiled into the JavaScript bundle at build time and are visible to
  anyone who opens dev tools — this is expected and safe *only if* every table's Row Level Security
  policy is correct, because the anon key is the entire security boundary. Never let
  `SUPABASE_SERVICE_ROLE_KEY` anywhere near this project: there is no server to keep it secret from the
  browser.
- Routing: a client-side router needs the host configured to serve `index.html` for unknown paths (a
  rewrite rule), or deep links 404 on refresh. Say which rewrite the chosen target needs.
- Caching: static assets under `dist/assets/` are content-hashed and can be cached forever;
  `index.html` itself must not be, or a deploy never reaches returning visitors.
- Realtime subscriptions (if used) open a WebSocket to `wss://<ref>.supabase.co`; check the target's
  network/CDN does not block WebSocket upgrades if the specification uses them.

## The Supabase connection

Read `SUPABASE_URL`/`SUPABASE_ANON_KEY` from the deployment's saved variables (as `VITE_SUPABASE_URL`/
`VITE_SUPABASE_ANON_KEY`) — the Studio's Supabase connect step already fetched them for this project.
Apply `supabase/migrations/` with `supabase db push` before deploy. Because there is no server-side
code, **every RLS policy the specification implies must actually exist and be tested** — this is the
one place in the whole review where a missing policy is a security bug, not a missing feature. Seed
scripts run locally against the linked project (`supabase db push` + a Node script using the
service-role key from the developer's own machine, never bundled into the app) and touch only what the
customer chose.

## Health

A static app has no server to health-check; the target's own "the file exists and returns 200" check is
enough. If the specification calls for a synthetic check that the Supabase project itself is reachable,
that is a client-side check run by the QA suite, not a server route.

## What "live" means for this stack

Within the smoke proof of `core` section 10 (read-only requests: no sign-in, no write, no test data):
`index.html` loads and renders the application's own content, not a blank shell or a build error; a deep link
returns the app shell instead of a 404; and one read through the project's REST endpoint with the public key from
the environment (not printed) answers with rows or an empty list that RLS allows, never an error. Whether a
protected screen redirects is decided in the browser and is not probed.

## Questions to ask the customer

Take these as defaults, not as questions: `core` section 12 caps a whole deployment at three questions, so most of what follows is a choice to state in the plan, not to ask.

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. Is this the Supabase project the build already connected to, or should production point at a
   different one?
2. Should the production project's tables start empty, with only required reference data, or with demo
   data?
3. If OAuth sign-in is enabled, has the production redirect URI been added in Supabase Auth settings?
4. Does the customer have a custom domain?
5. Should unknown paths rewrite to `index.html` (needed for client-side routing) — confirmed set up on
   the chosen target?
6. Are preview deployments for branches wanted, or only production?
7. Which environment variables in `.env.example` should be set now, and which are left for the customer?
