---
name: stack-nextjs-microservices-supabase
description: A Next.js frontend with independent Supabase Edge Functions as its backend services, one shared Postgres project. Function deploys, the frontend's own deploy, environment, health of the whole, and the questions to ask the customer.
---

# Deploying a Next.js + microservices + Supabase application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to a
Next.js frontend backed by several independent **Supabase Edge Functions** instead of one Node backend,
sharing one Supabase project (Postgres, Auth, Storage). It applies to every target the frontend can run
on: Vercel, Netlify, AWS EC2, AWS ECS, Azure App Service and GitHub — the "microservices" half of this
stack deploys to Supabase's own infrastructure regardless of where the frontend is hosted, so no target
is excluded the way the old MongoDB-based MERN microservices stack excluded Vercel and Netlify.

## What to read in the project

The frontend half: everything in `stack-nextjs-supabase`'s "what to read" (this page assumes that page's
build/run facts for the Next.js half and does not repeat them). The services half: `supabase/functions/`
— one directory per service (`supabase/functions/<name>/index.ts`), `supabase/config.toml` (function
names, JWT verification per function, import map), and each function's own `deno.json`/imports. Build a
table from what you read: for each function, its name, what it does, which tables it touches, whether it
requires a verified Supabase Auth JWT (`verify_jwt` in `config.toml`) or is meant to be public, and which
frontend calls invoke it (`supabase.functions.invoke('<name>', ...)`).

## How the pieces fit

- The Next.js app is the only public **web** surface; it calls each function through
  `supabase.functions.invoke()` (or a plain `fetch` to `https://<ref>.functions.supabase.co/<name>`),
  never a hand-rolled internal network address.
- Each Edge Function is its own Deno process, deployed and versioned independently
  (`supabase functions deploy <name>`) — deploying one function never touches another, and never touches
  the frontend's own deploy. There is no gateway to configure and no internal port allocation: Supabase's
  platform routes `functions.supabase.co/<name>` to the right function on its own.
- Functions share the one Supabase project's Postgres, Auth and Storage. A function that needs to bypass
  RLS (an admin action) uses the service-role key from its own environment (`Deno.env.get(...)`, set via
  `supabase secrets set`), never the anon key, and never the frontend's own service-role key baked into
  client code.
- There is no `start:all`/port-guard equivalent: `supabase functions serve` runs every function locally
  against the local (or linked) project for development; nothing about it belongs in a production deploy
  plan.

## Build and run facts

- Frontend: build and run exactly as `stack-nextjs-supabase` describes.
- Functions: `supabase functions deploy <name>` per function (or `--no-verify-jwt` only for a function
  meant to be publicly callable — confirm against `config.toml`, don't guess). Secrets for functions are
  set with `supabase secrets set KEY=value` against the linked project, not through the frontend's own
  `.env` — a function's environment and the frontend's environment are separate stores.
- CORS: a function called from the browser needs its own CORS headers (Supabase does not add them); check
  each function returns `Access-Control-Allow-Origin` for the production domain, or browser calls fail
  silently with no server-side error to point at.
- Cold starts: Edge Functions cold-start in the low hundreds of milliseconds; note this in the plan if the
  specification has a latency-sensitive path, rather than silently accepting it.

## Making it work

- **No internal networking to secure** — unlike the old Express-based microservices stack, there are no
  internal ports or security groups to lock down; Supabase's platform is the only place functions are
  reachable, and each function's own `verify_jwt` setting is the access-control boundary, not network
  isolation. Get this setting right per function; it is the equivalent of the old "nothing but the
  gateway is public" rule.
- **Secrets shared across functions.** If several functions need the same third-party credential, set it
  once with `supabase secrets set` — it is available to every function in the project, not per-function.
- **Deploy order.** Functions can deploy independently of the frontend and of each other; there is no
  startup-order dependency to manage (no process waits on another to be "up").
- **Build.** The frontend builds and deploys exactly as a plain Next.js + Supabase app. Each function is
  its own small TypeScript file with no build step of its own (Deno runs it directly); `supabase
  functions deploy` bundles it.

## What "live" means for this stack

Beyond `core` section 10 and `stack-nextjs-supabase`'s frontend checks: **every function is reached
through a real call from the deployed frontend** (or a direct authenticated call to
`functions.supabase.co/<name>`) that returns data touching that function's tables — list the functions
from `supabase/config.toml` and call each one; a function that requires a verified JWT refuses an
unauthenticated call (this is the equivalent of the old "service port refuses from the internet" check —
here it is "a function meant to require auth actually does"); and `supabase functions deploy` logs no
errors for any function.

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. Is this the Supabase project the build already connected to, or should production point at a
   different one?
2. Which functions, if any, should require a verified Supabase Auth JWT versus being callable
   anonymously — confirm each against the specification rather than leaving `config.toml`'s defaults.
3. Should the production project's tables start empty, with only required reference data, or with demo
   data?
4. Where should the Next.js frontend itself be hosted (see `stack-nextjs-supabase`'s own questions for
   that half)?
5. Does the customer have a custom domain for the frontend?
6. Which secrets does each function need, and are they already saved, or should they be set now with
   `supabase secrets set`?
