---
name: stack-remix-supabase
description: What a Remix (Vite) + Supabase application needs to deploy well on any target: the production server, adapters per platform, environment, the Supabase project's URL and keys, health, and the questions to ask the customer.
---

# Deploying a Remix + Supabase application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to a
Remix v2 application built on Vite with Supabase (Postgres, Auth, Storage). It applies to every target:
Vercel, Netlify, AWS EC2, AWS ECS, Azure App Service and GitHub. Where it and the target page disagree
about a target's own commands, the target page wins.

## What to read in the project

`package.json` (scripts, `engines`, the Remix and Vite versions, lockfile), `vite.config.*` (the Remix
plugin and its future flags), `app/root.jsx`, the `app/routes/` tree (each route's `loader`, `action`,
`headers`), `lib/supabase.js` (how the request-scoped server client, cookie handling and any admin
client are built), `supabase/migrations/`, `.env.example` and `scripts/` (seed and setup).

## Build and run facts

- Build: `npm run build` produces `build/client` and `build/server`. Production start:
  `remix-serve ./build/server/index.js` on `PORT` (default 3000); confirm on the installed version
  whether it needs `HOST=0.0.0.0` behind a container or proxy.
- **Self-hosted targets** (EC2, ECS, Azure App Service) run exactly that: install production
  dependencies, keep `build/` and `package.json` together, start with `remix-serve`.
- **Vercel and Netlify** run server code as functions and need their adapter in the Vite config: look up
  the current official setup for the installed Remix version with `web_search`/`web_fetch` before
  finalizing the plan, and name the change.
- **GitHub** publishes the repository; a Remix application with a live database is not a static Pages
  site.
- Environment: `SUPABASE_URL` and `SUPABASE_ANON_KEY` are safe to expose to the browser (loaders pass
  them through a small `ENV` object rendered in `root.jsx`, the usual Remix pattern — never expose the
  whole environment); `SUPABASE_SERVICE_ROLE_KEY` is read only in server code (`loader`/`action`) and
  never rendered.
- Sessions and cookies: Supabase Auth's SSR helper reads/writes the session cookie per request through
  the `lib/supabase.js` server client; check it is built fresh per request (cookies differ per request)
  and that the cookie is `Secure`, `HttpOnly`, `SameSite`.
- Single fetch and future flags: leave the project's flags as they are.

## The Supabase connection

Read `SUPABASE_URL`/`SUPABASE_ANON_KEY`/`SUPABASE_SERVICE_ROLE_KEY` from the deployment's saved
variables — the Studio's Supabase connect step already fetched them for this project; never ask the
customer to paste them again unless production is meant to point at a different project. Apply
`supabase/migrations/` with `supabase db push` before or during deploy, never by hand. Seed scripts touch
only what the customer chose; a seed creating Auth users uses the service-role key's admin API.

## Health

Add a minimal resource route (for example `app/routes/healthz.jsx`) returning a small JSON response, no
data, when the project has none; a deeper check can run one cheap query through the anon key.

## What "live" means for this stack

Beyond `core` section 10: the home page's HTML is server-rendered with the application's own content; a
route that needs a session, requested anonymously, redirects to sign-in (or answers 401); a full round
trip (sign in through Supabase Auth, submit a form via an `action`, read the result back) works through
the real project's RLS policies, not just the service-role key; a file uploaded to Storage is retrievable;
the session cookie carries `Secure` and `HttpOnly`; a built asset from `/assets/` loads; and the
platform's and Supabase project's logs show no errors during those requests.

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. Is this the Supabase project the build already connected to, or should production point at a
   different one?
2. Which region, given where the Supabase project and the users are?
3. Should the production project's tables start empty, with only required reference data, or with demo
   data?
4. On a function platform: is the current official adapter for the installed Remix version acceptable to
   add to the project, and are deployment previews wanted?
5. If OAuth sign-in is enabled, has the production redirect URI been added in Supabase Auth settings?
6. Does the customer have a custom domain?
7. Does the specification need scheduled jobs (Edge Functions) or outbound email?
8. Which environment variables in `.env.example` should be set now, and which are left for the customer?
