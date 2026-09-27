---
name: stack-nextjs
description: What a Next.js application needs to deploy well on any target: build output, environment at build and run time, the database connection, headers, health, and the questions to ask the customer.
---

# Deploying a Next.js application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to
a Next.js (App Router) application with a MongoDB database. It applies to every target: Vercel,
Netlify, AWS EC2, AWS ECS, Azure App Service and GitHub. Where it and the target page disagree about a
target's own commands, the target page wins.

## What to read in the project

`package.json` (scripts, `engines`, the Next.js version, package manager and lockfile), `next.config.*`
(output mode, headers, image settings, the tracing root), the `app/` tree (which routes are pages, which
are route handlers, which segments set `runtime`, `dynamic`, `revalidate` or `maxDuration`), the
middleware or proxy file, `lib/db.js` (how the database connection is opened and reused), `.env.example`,
and `scripts/` (seed and setup scripts: which are safe on a production database).

## Build and run facts

- Build: the project's own `build` script. Production start: `next start`, or for self-hosted targets the
  standalone server. Self-hosted targets (EC2, ECS, Azure) set `output: "standalone"` in `next.config.*`
  (a small change the plan names) and run `node <standalone folder>/server.js` with `PORT` and
  `HOSTNAME=0.0.0.0`; `.next/static` and `public/` are copied beside `server.js`, because the standalone
  folder does not include them. Vercel and Netlify build the application themselves and need no output
  mode. Keep the tracing root the project already sets.
- Public variables (`NEXT_PUBLIC_*`) are written into the JavaScript at **build** time: they must be
  present in the build environment, and changing one means building again. Everything else is read at
  run time from the server's environment. Never give a secret the public prefix.
- Response headers and the content-security policy are set in `next.config.*` and baked in at build time.
  If the application needs to be framed or to load a third-party origin, the customer's answer decides the
  build environment; do not weaken them silently.
- Server Actions and multiple instances: several instances of one application must share an encryption
  key for Server Actions (`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY`, a 32-byte random value generated once and
  kept across releases), and the same session or signing secret. A single serverless project needs them
  too, so a deployment never invalidates in-flight forms.
- The middleware or proxy file runs on every request: check its runtime and that it works on the target
  (serverless targets run it at the edge or in a function; self-hosted ones in the server process).
- Rendering: a page that reads data at request time must not be cached as static. Look for routes that
  are accidentally static (they show build-time data) and for routes that call the database during the
  build; a build that needs a live database is repaired so it does not, or the database is provided to
  the build on purpose.
- Images: `next/image` on a self-hosted server optimizes with `sharp`, present with Next; a serverless
  platform handles it itself. Remote image hosts must be listed in the config.
- Uploads and files: a serverless or container file system is not durable. If the specification stores
  user files, they go to object storage the customer chooses, not to local disk.
- Background work: nothing may rely on a process staying alive after the response on a serverless
  target. Scheduled work uses the platform's cron feature (Vercel Cron, a scheduled function, an
  EventBridge rule or an Azure timer), named in the plan.

## The database connection

`lib/db.js` must cache the connection on the module (or `globalThis`) so each function instance or
process opens one connection and reuses it, and must fail with a clear message when the connection string
is missing. Keep the pool small on serverless targets. The connection string is only ever read from
`MONGODB_URI`, never hard-coded. Seed scripts: the production database gets only what the customer chose
(see the questions); never run a destructive development seed against it.

## Health

Add a minimal route handler (for example `app/api/health/route.js`) that answers 200 with a small JSON
body and no data, plus an optional deeper one that pings the database, when the project has none. A
target's load balancer or platform check points at the cheap one.

## What "live" means for this stack

Beyond `core` section 10: the server-rendered home page contains the application's own content; a
protected page requested without a session redirects to sign-in (or answers 401) and never renders
protected data; a route handler round trip (sign in, create, read back) works through the real database;
the `Set-Cookie` of a session is `Secure` and `HttpOnly` over HTTPS; a static asset from `/_next/static`
loads; and the platform's logs show no server errors during those requests.

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation first,
and let "you decide" be an answer:

1. Where is the production MongoDB, and is its connection string saved in Settings? (Options: use the
   one saved, use a different one the customer will save first, deploy without a database and show the
   application's unconfigured state.)
2. Which region should the application run in, given where the database and the users are?
3. Should the production database start empty, with only the required reference data, or with the demo
   data the specification describes? (Never default to demo accounts on a public address.)
4. Does the customer have a custom domain, and should `www` and the bare domain both work?
5. Are preview deployments for branches wanted, or only production?
6. Does the specification need scheduled jobs, file uploads or outbound email, and where should those
   go (which cron feature, which storage, which mail provider)?
7. Which environment variables in `.env.example` should be set now, and which are left for the customer?
