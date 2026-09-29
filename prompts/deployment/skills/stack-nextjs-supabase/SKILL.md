---
name: stack-nextjs-supabase
description: What a Next.js + Supabase application needs to deploy well on any target: build output, environment at build and run time, the Supabase project's URL and keys, Auth and Storage, headers, health, and the questions to ask the customer.
---

# Deploying a Next.js + Supabase application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to
a Next.js (App Router) application on Supabase (Postgres, Auth, Storage). It applies to every target:
Vercel, Netlify, AWS EC2, AWS ECS, Azure App Service and GitHub. Where it and the target page disagree
about a target's own commands, the target page wins.

## What to read in the project

`package.json` (scripts, `engines`, the Next.js version, package manager and lockfile), `next.config.*`
(output mode, headers, image settings, the tracing root), the `app/` tree (which routes are pages, which
are route handlers, which segments set `runtime`, `dynamic`, `revalidate` or `maxDuration`), the
middleware file (Supabase's SSR auth refreshes the session there), `lib/supabase.js` (or `/server.js` +
`/client.js`: how the browser client, the server client and any admin/service-role client are built),
`supabase/migrations/` (the schema and RLS policies actually shipped), `.env.example`, and `scripts/`
(seed and setup scripts: which are safe against a production project).

## Build and run facts

- Build: the project's own `build` script. Production start: `next start`, or for self-hosted targets
  the standalone server. Self-hosted targets (EC2, ECS, Azure) set `output: "standalone"` in
  `next.config.*` and run `node <standalone folder>/server.js` with `PORT` and `HOSTNAME=0.0.0.0`.
  Vercel and Netlify build the application themselves and need no output mode.
- Public variables (`NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`) are written into the
  JavaScript at **build** time and are meant to be public — the anon key is only useful together with
  RLS policies, never a secret on its own. `SUPABASE_SERVICE_ROLE_KEY` is read at run time on the server
  only, bypasses RLS, and must never carry the `NEXT_PUBLIC_` prefix or reach a client bundle.
- Response headers and the content-security policy are set in `next.config.*` and baked in at build
  time. The CSP's `connect-src` needs the project's own `https://<ref>.supabase.co` (and
  `wss://<ref>.supabase.co` if Realtime is used) or the browser client is blocked silently.
- Server Actions and multiple instances: several instances share `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY`.
  Supabase Auth's session is a signed cookie the SSR helper manages; nothing extra to share beyond the
  project's own anon key, which is stable per environment.
- The middleware file runs on every request when Supabase SSR auth is wired up (it refreshes an
  expiring session and writes the new cookie) — check it exists and runs on the target's runtime.
- Rendering: a page that reads data at request time must not be cached as static; a route that calls the
  Supabase client during the build needs a public (anon-key, RLS-gated) read or a build-time env answer.
- Uploads: files go to a Supabase Storage bucket (already provisioned by the project's connect step),
  never to local disk on a serverless or container target.
- Background work: nothing may rely on a process staying alive after the response on a serverless
  target. Scheduled work is a platform cron **or** a Supabase Edge Function invoked by `pg_cron`/the
  Supabase dashboard's own scheduler — say which in the plan.

## The Supabase connection

A project connected through the Studio's Supabase sign-in already has `SUPABASE_URL`,
`SUPABASE_ANON_KEY` (mirrored as `NEXT_PUBLIC_*`) and `SUPABASE_SERVICE_ROLE_KEY` recorded — read them
from the deployment's saved variables rather than asking the customer to paste them again. `lib/supabase.js`
must build a fresh client per request on the server (the SSR pattern: cookies differ per request) and a
single client on the browser; never share a server client across requests. Migrations (`supabase/migrations/`)
are applied with `supabase db push` against the linked project before or during deploy, never by hand
against production. Seed scripts touch only what the customer chose (see the questions), and a seed that
creates Auth users uses the service-role key's admin API, never the anon key.

## Health

Add a minimal route handler (for example `app/api/health/route.js`) that answers 200 with a small JSON
body and no data, plus an optional deeper one that runs one cheap Postgres query through the anon key
(proving RLS and the connection both work), when the project has none.

## What "live" means for this stack

Beyond `core` section 10: the server-rendered home page contains the application's own content; a
protected page requested without a session redirects to sign-in (or answers 401) and never renders
protected data; a full round trip (sign up or sign in through Supabase Auth, create a row, read it back)
works through the real project and its RLS policies — not just through the service-role key; a file
uploaded to Storage is retrievable at its public or signed URL; the session cookie is `Secure` and
`HttpOnly` over HTTPS; a static asset from `/_next/static` loads; and the platform's logs and the
Supabase project's own logs show no errors during those requests.

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. Is this the Supabase project the build already connected to, or should production point at a
   different one? (Recommend the one already connected unless the customer wants to separate staging
   from production.)
2. Which region should the application run in, given where the Supabase project and the users are?
3. Should the production project's tables start empty, with only required reference data, or with the
   demo data the specification describes? (Never default to demo accounts on a public address.)
4. If Google (or another OAuth) sign-in is enabled, has its redirect URI been added for the production
   domain in the Supabase Auth settings? Push it through the Management API rather than asking the
   customer to click through the dashboard, when possible.
5. Does the customer have a custom domain, and should `www` and the bare domain both work?
6. Are preview deployments for branches wanted, or only production?
7. Does the specification need scheduled jobs (Edge Functions + cron) or outbound email (Supabase Auth's
   own, or a separate provider)?
8. Which environment variables in `.env.example` should be set now, and which are left for the customer?
