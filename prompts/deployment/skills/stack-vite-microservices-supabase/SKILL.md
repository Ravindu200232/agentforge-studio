---
name: stack-vite-microservices-supabase
description: A Vite + React SPA with independent Supabase Edge Functions as its backend services, one shared Postgres project. Static build, function deploys, environment, health of the whole, and the questions to ask the customer.
---

# Deploying a Vite + microservices + Supabase application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to a
Vite + React single-page app backed by independent **Supabase Edge Functions** for anything that should
not run as a direct, RLS-gated client query, sharing one Supabase project (Postgres, Auth, Storage). It
applies to every target the static frontend can run on: Vercel, Netlify, AWS EC2, AWS ECS, Azure App
Service and GitHub — the functions half deploys to Supabase's own infrastructure regardless of where the
static bundle is hosted.

## What to read in the project

The frontend half: everything in `stack-vite-supabase`'s "what to read" (this page assumes that page's
build/run facts and RLS-is-the-security-boundary point for the SPA half and does not repeat them). The
services half: `supabase/functions/` (one directory per service), `supabase/config.toml` (function names,
`verify_jwt` per function), each function's own imports. Build a table: for each function, its name, what
it does that a direct client query to Postgres could not do safely (the whole reason it is a function and
not just another RLS-gated table read), whether it requires a verified JWT, and which part of the SPA
calls it.

## How the pieces fit

- The SPA calls each function through `supabase.functions.invoke()` from the browser, alongside its
  direct `supabase.from(...)` queries for everything RLS already protects well enough. A function exists
  specifically for logic that must not run as client code: anything using the service-role key, a
  third-party secret, or a multi-step operation that must be atomic from the client's point of view.
- Each function deploys independently (`supabase functions deploy <name>`); deploying one never touches
  another or the static bundle. There is no gateway and no internal port allocation.
- A function that needs to bypass RLS uses the service-role key from its own function environment
  (`supabase secrets set`), never a key present anywhere in the SPA's bundle — the SPA has no server-side
  secret store of its own, which is precisely why privileged logic belongs in a function, not in
  `src/lib/supabase.js`.

## Build and run facts

- Frontend: build and host exactly as `stack-vite-supabase` describes (static `dist/`, no server
  process, every SPA env var is public).
- Functions: `supabase functions deploy <name>` per function. CORS headers are the function's own
  responsibility for the production domain (Supabase adds none automatically) — a missing header fails
  silently in the browser with nothing server-side to point at, so check it explicitly.
- Secrets for functions are set with `supabase secrets set KEY=value` against the linked project; this is
  a separate store from the SPA's build-time `VITE_*` variables, and nothing set there should ever be
  duplicated into a `VITE_*` variable (that would publish it).

## Making it work

- **The security boundary is split, on purpose**: RLS protects direct table access from the SPA; a
  function's `verify_jwt` setting (and whatever checks it does internally) protects everything that
  can't be a safe RLS policy. Get both right — a function with no auth check that was meant to require
  one is the equivalent of a missing RLS policy on the plain Vite+Supabase stack.
- **No internal networking to secure** — functions are only reachable through Supabase's own platform;
  there is nothing analogous to the old Express gateway's "only the gateway is public" rule to configure.
- **Deploy order** doesn't exist here: functions and the static bundle deploy independently, with no
  startup dependency between them.

## What "live" means for this stack

Beyond `core` section 10 and `stack-vite-supabase`'s frontend/RLS checks: **every function is reached
through a real call from the deployed SPA** that does what it's meant to (touches its tables, calls the
third party, whatever the function exists for); a function requiring a verified JWT refuses an
unauthenticated call; a function using the service-role key is never reachable from a browser tab with no
session when it shouldn't be; and `supabase functions deploy` logs no errors for any function.

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. Is this the Supabase project the build already connected to, or should production point at a
   different one?
2. For each function: should it require a verified Supabase Auth JWT, and does the specification confirm
   that's the right boundary (versus a plain RLS-gated table the SPA could read directly)?
3. Should the production project's tables start empty, with only required reference data, or with demo
   data?
4. Where should the static frontend itself be hosted (see `stack-vite-supabase`'s own questions)?
5. Does the customer have a custom domain?
6. Which secrets does each function need, and are they already saved, or should they be set now with
   `supabase secrets set`?
