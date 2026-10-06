---
name: stack-remix-mongo
description: What a Remix + MongoDB application needs to deploy well on AWS or Azure as one server process: build output, the real Atlas connection string, session auth, headers, health, and the questions to ask the customer.
---

# Deploying a Remix + MongoDB application

Read this page after `core/SKILL.md` and the page for the chosen target (AWS EC2, AWS ECS or Azure App
Service - this stack is a long-running Node server, so it is not offered on Vercel, Netlify or GitHub).
It says what is particular to a Remix v2 (Vite) application on MongoDB. It covers both `remix-mongo`
(uploaded files in a Supabase Storage bucket) and `remix-mongo-only` (no Supabase at all, uploaded files in
MongoDB GridFS). Where it and the target page disagree about a target's own commands, the target page wins.

## What to read in the project

`package.json` (scripts, `engines`, the Remix version, package manager and lockfile), `vite.config.js` (the
`remix()` plugin options), the `app/routes/` tree (which routes are pages, which only export a `loader` or
`action`), `lib/db.js` (how the one Mongoose connection is cached), `models/` (the schemas actually shipped),
`.env.example`, `scripts/seed.mjs`, and `.agentforge/PLUGIN.md` when a sign-in or upload plugin was selected.

## Build and run facts

- Build: the project's own `build` script (`remix vite:build`), which writes `build/server/index.js` and
  `build/client/`. Production start: `remix-serve ./build/server/index.js`, which reads `PORT` (and `HOST`:
  set `HOST=0.0.0.0` on a self-hosted target). Both `build/` folders are deployed together; the server
  serves `build/client` itself.
- `MONGODB_URI` is read on the server only (inside a `loader`, an `action` or a `*.server.js` module) and must
  never reach a client bundle. `SESSION_SECRET` (the key `jose` signs cookies with) is server-only the same
  way. Nothing about the database connection is a build-time public variable.
- `lib/db.js`'s loopback fallback is for local development only. The deployed value must be a real,
  internet-reachable MongoDB Atlas (or equivalent) connection string - never `localhost`/`127.0.0.1`.
- Uploaded files: with `remix-mongo-only` they are in MongoDB GridFS, so the one `MONGODB_URI` is all the
  storage the app needs. With `remix-mongo` they are in a Supabase Storage bucket, so the project's
  `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` deploy the same way as `MONGODB_URI`:
  real values, server-only (the service-role key never reaches a browser). If an uploads or sign-in plugin was
  selected, `.agentforge/PLUGIN.md` names its variables; they deploy the same way.
- The connection is reused across requests the way `lib/db.js` already does (`readyState === 1`
  short-circuit, cached on `globalThis`); confirm the project did not remove that caching, or every request
  opens a fresh connection and Atlas's connection limit is reached quickly under load.

## The MongoDB connection

`MONGODB_URI` is **not asked for**. The Studio provides it: the machine facts above say what this project's MongoDB is, and your commands receive `MONGODB_URI` in their environment - the customer's connected Atlas cluster with this project's own database, the one the build's seed filled, as a real, internet-reachable string (a loopback address is never handed over). When only an Atlas account is signed in, the Studio makes the cluster and the database before the run starts; when nothing is connected it does not start the deployment at all and tells the customer to connect MongoDB in Settings, so a deployment never reaches you without one. So never ask the customer for a connection string, an address, an Atlas account or whether to use a local database, never write `localhost` for it, never print it, and never run or probe a MongoDB on this computer to check it: the live check of this stack (a real round trip against the deployed address) is the proof. 

## Health

Add a minimal resource route (for example `app/routes/health.jsx` exporting a `loader` that returns a small
JSON body with no data) when the project has none. A deeper check (one cheap `ping`) is useful but must not be
the public health route a load balancer polls every few seconds - that would hit the database on every check.

## What "live" means for this stack

Within the smoke proof of `core` section 10 (read-only requests: no sign-in, no write, no test data): the
server-rendered home page contains the application's own content; a protected route requested without a
session redirects to sign-in (or answers 401) and never renders protected data; one loader route reads real
documents from the Atlas database (proof it is not the local fallback); a built asset under `/assets/` loads.

## Questions to ask the customer

Take these as defaults, not as questions: `core` section 12 caps a whole deployment at three questions, so most of what follows is a choice to state in the plan, not to ask.

These are prompts, not a script: write each question yourself for this project and ask only what the project,
an earlier answer and the skill pages do not already settle. One at a time, recommendation first, and let
"you decide" be an answer:

1. The database is not a question: the Studio provides the cluster and this project's database (see "The MongoDB connection"). Do not ask about it; carry on with the next one.
2. Which region should the application and the cluster both run in?
3. Should the production database start empty, with only required reference data, or with the demo data the
   specification describes? (Never default to demo accounts on a public address.)
4. If Google (or another OAuth) sign-in is enabled, has its redirect URI been added for the production domain
   with the provider?
5. Does the customer have a custom domain, and should `www` and the bare domain both work?
6. Which environment variables in `.env.example` should be set now, and which are left for the customer?
