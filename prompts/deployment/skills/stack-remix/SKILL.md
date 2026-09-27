---
name: stack-remix
description: What a Remix (Vite) application needs to deploy well on any target: the production server, adapters per platform, environment, the database connection, health, and the questions to ask the customer.
---

# Deploying a Remix application

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to a
Remix v2 application built on Vite with a MongoDB database. It applies to every target: Vercel,
Netlify, AWS EC2, AWS ECS, Azure App Service and GitHub. Where it and the target page disagree about a
target's own commands, the target page wins.

## What to read in the project

`package.json` (scripts, `engines`, the Remix and Vite versions, lockfile), `vite.config.*` (the Remix
plugin and its future flags: Remix on Vite has no `remix.config.js`), `app/root.jsx`, the `app/routes/`
tree (each route's `loader`, `action`, `headers`), `lib/db.js`, the session and authentication code (how
the cookie is signed, which secret), `.env.example` and `scripts/` (seed and setup).

## Build and run facts

- Build: `npm run build` produces `build/client` (static assets) and `build/server` (the server bundle).
  Production start: `remix-serve ./build/server/index.js`, which serves both. It listens on `PORT`
  (default 3000); confirm on the installed version whether it needs `HOST=0.0.0.0` to accept traffic from
  outside a container or a proxy, and set it if so.
- **Self-hosted targets** (EC2, ECS, Azure App Service) run exactly that: install production dependencies
  from the lockfile (or ship them), keep `build/` and `package.json` together, start with `remix-serve`.
  No code change is needed.
- **Vercel and Netlify** run server code as functions and need their adapter in the Vite config: the
  plan names the change (a dependency and a preset or plugin entry in `vite.config.*`) and a `vercel.json`
  or `netlify.toml` when the adapter asks for one. Adapters change between Remix releases: before the
  plan is final, look up the current official setup for the project's Remix version with `web_search` and
  `web_fetch`, and write what you found in the step. Never guess the plugin name.
- **GitHub** publishes the repository; a Remix application with a database is not a static Pages site.
- Environment: server code reads `process.env` at run time (loaders, actions, `lib/db.js`), so secrets
  are provided by the host and never reach the client. Values the browser needs are passed through a
  loader (a small `ENV` object rendered in `root.jsx`), never by exposing the whole environment. Vite
  variables (`import.meta.env.VITE_*`) are compiled into the client build: only public values.
- Sessions and cookies: check how the session secret is configured (`SESSION_SECRET` or similar), that it
  is required in production, that the cookie is `Secure`, `HttpOnly` and `SameSite`, and that all
  instances share the secret. A generated secret is kept across releases.
- Streaming and long requests: check the target's response time limit against slow loaders.
- Single fetch and future flags: leave the flags the project already enables; do not change them to make
  a build pass.

## The database connection

`lib/db.js` must reuse one connection per server process or function instance and fail with a clear
message when `MONGODB_URI` is missing. On function-based targets cache it on `globalThis` so warm
instances reuse it and keep the pool small. Seed scripts: only what the customer chose reaches the
production database; never a destructive development seed.

## Health

Add a minimal resource route (for example `app/routes/healthz.jsx` with a `loader` returning a small
JSON response, no data) when the project has none; a target's platform check points at it. A deeper check
that pings the database can sit on a second route.

## What "live" means for this stack

Beyond `core` section 10: the home page's HTML is server-rendered with the application's own content; a
route that needs a session, requested anonymously, redirects to sign-in (or answers 401) and does not
render protected data; an `action` round trip (sign in, submit a form, read the result back) works
through the real database; the session cookie carries `Secure` and `HttpOnly`; a built asset from
`/assets/` loads; and the platform's logs show no server errors during those requests.

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
4. On a function platform: is the current official adapter for the installed Remix version acceptable to
   add to the project, and are deployment previews wanted?
5. Does the customer have a custom domain?
6. Does the specification need scheduled jobs, file uploads or outbound email, and where should those
   go?
7. Which environment variables in `.env.example` should be set now, and which are left for the customer?
