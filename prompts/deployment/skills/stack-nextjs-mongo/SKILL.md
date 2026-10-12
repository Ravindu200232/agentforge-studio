---
name: stack-nextjs-mongo
description: What a Next.js + MongoDB application needs to deploy well on any target: build output, the real Atlas connection string, session auth, headers, health, and the questions to ask the customer.
---

# Deploying a Next.js + MongoDB application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to
a Next.js (App Router) application on MongoDB. It applies to every target: Vercel, Netlify, AWS EC2, AWS
ECS, Azure App Service and GitHub. Where it and the target page disagree about a target's own commands,
the target page wins.

## What to read in the project

`package.json` (scripts, `engines`, the Next.js version, package manager and lockfile), `next.config.*`
(output mode, headers), the `app/` tree (which routes are pages, which are route handlers, which
segments set `runtime`, `dynamic`, `maxDuration`), `lib/db.js` (how the one Mongoose connection is
cached), `models/` (the schemas actually shipped), `.env.example`, `scripts/seed.mjs`, and
`.agentforge/PLUGIN.md` when a sign-in or upload plugin was selected.

## Build and run facts

- Build: the project's own `build` script. Production start: `next start`, or for self-hosted targets
  (EC2, ECS, Azure) the standalone server with `output: "standalone"` set in `next.config.*`, run as
  `node <standalone folder>/server.js` with `PORT` and `HOSTNAME=0.0.0.0`. Vercel and Netlify build the
  application themselves and need no output mode.
- `MONGODB_URI` is read on the server only and must never carry the `NEXT_PUBLIC_` prefix or reach a
  client bundle. `SESSION_SECRET` (the key `jose` signs cookies with) is server-only the same way.
  Nothing about the database connection is a build-time public variable, unlike the Supabase stacks.
- `lib/db.js`'s loopback fallback is for local development only (`guide_context`/`nextjs-mongo.md` says
  so to the builder). The deployed value must be a real, internet-reachable MongoDB Atlas (or
  equivalent) connection string — never `localhost`/`127.0.0.1`.
- If the project selected the Google (or another) sign-in plugin, or an image-uploads plugin,
  `.agentforge/PLUGIN.md` names its environment variables; they deploy the same way as `MONGODB_URI` and
  `SESSION_SECRET` — real values, server-only, never guessed.
- Serverless targets (Vercel, Netlify) reuse one connection across invocations the way `lib/db.js`
  already does (`readyState === 1` short-circuit, cached on the module/`globalThis`); confirm the
  project did not remove that caching, or every request opens a fresh connection and Atlas's connection
  limit is reached quickly under load.

## The MongoDB connection

`MONGODB_URI` is **not asked for**. The Studio provides it: the machine facts above say what this project's MongoDB is, and your commands receive `MONGODB_URI` in their environment - the customer's connected Atlas cluster with this project's own database, the one the build's seed filled, as a real, internet-reachable string (a loopback address is never handed over). When only an Atlas account is signed in, the Studio makes the cluster and the database before the run starts; when nothing is connected it does not start the deployment at all and tells the customer to connect MongoDB in Settings, so a deployment never reaches you without one. So never ask the customer for a connection string, an address, an Atlas account or whether to use a local database, never write `localhost` for it, never print it, and never run or probe a MongoDB on this computer to check it: the live check of this stack (a real round trip against the deployed address) is the proof. On Atlas, the cluster's Network Access list must allow the target's outbound addresses — a
serverless target (Vercel, Netlify) has no fixed address, so Atlas needs `0.0.0.0/0` there (the
connection string's username/password is still the real access control); a self-hosted target (EC2,
ECS, Azure) has a fixed outbound address or NAT gateway that can be listed exactly instead.

## Health

Add a minimal route handler (for example `app/api/health/route.js`) that answers 200 with a small JSON
body and no data, when the project has none. A deeper check (one cheap `findOne` or `ping`) is useful but
must not be the public health route a load balancer polls every few seconds — that would hit the
database on every check.

## What "live" means for this stack

Within the smoke proof of `core` section 10 (read-only requests: no sign-in, no write, no test data): the
server-rendered home page contains the application's own content; a protected page requested without a session
redirects to sign-in (or answers 401) and never renders protected data; one server-rendered page or API route
reads real documents from the Atlas database (proof it is not the local fallback); a static asset from
`/_next/static` loads.

## Questions to ask the customer

Take these as defaults, not as questions: `core` section 12 caps a whole deployment at three questions, so most of what follows is a choice to state in the plan, not to ask.

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. The database is not a question: the Studio provides the cluster and this project's database (see "The MongoDB connection"). Do not ask about it; carry on with the next one.
2. Which region should the application and the cluster both run in?
3. Should the production database start empty, with only required reference data, or with the demo data
   the specification describes? (Never default to demo accounts on a public address.)
4. If Google (or another OAuth) sign-in is enabled, has its redirect URI been added for the production
   domain with the provider?
5. Does the customer have a custom domain, and should `www` and the bare domain both work?
6. Are preview deployments for branches wanted, or only production?
7. Which environment variables in `.env.example` should be set now, and which are left for the customer?
