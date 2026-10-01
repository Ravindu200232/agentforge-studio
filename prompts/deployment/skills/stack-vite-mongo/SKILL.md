---
name: stack-vite-mongo
description: What a Vite + React SPA with its own Express + MongoDB server needs to deploy well on AWS or Azure as one process and one port, the real Atlas connection string, session auth, health, and the questions to ask the customer.
---

# Deploying a Vite + MongoDB application

Read this page after `core/SKILL.md` and the page for the chosen target (AWS EC2, AWS ECS or Azure App
Service — this stack has its own server and does not fit a static or serverless-functions target, so it
is not offered on Vercel, Netlify or GitHub). It says what is particular to a Vite + React client with a
plain Express API server of its own behind it, both talking to one MongoDB database.

## What to read in the project

Root `package.json` (the `server` and `client` npm workspaces), `server/src/app.js` (the only process
that is MongoDB-reachable, and what it serves once the client is built), `server/src/db.js` (the one
cached Mongoose connection), `server/src/config.js` (`PORT`, `MONGODB_URI`), `client/src/api.js` (the
one place the client calls `/api` — relative URLs only), `.env.example`, `scripts/seed.mjs`, and
`.agentforge/PLUGIN.md` when a sign-in or upload plugin was selected.

## Build and run facts

- Build: `npm run build` builds only the client (`client/dist`); the server needs no build step. Start:
  `npm start` → `server/src/server.js`, which serves the built client and the API from the **same
  process and the same port** — there is no separate gateway and no internal port allocation to wire up,
  unlike `mern-microservices`. One container (ECS) or one instance (EC2) runs the whole application.
- The host gives one public port in `PORT`; the server already binds `0.0.0.0`-reachable and reads
  `PORT` from the environment (never hard-coded). `MONGODB_URI` and `SESSION_SECRET` are read on the
  server only and are never compiled into the client bundle — only `client/src/api.js`'s relative `/api`
  calls cross that boundary, so there is nothing Mongo-shaped in the client build to leak.
- `server/src/db.js`'s loopback fallback is for local development only. The deployed value must be a
  real, internet-reachable MongoDB Atlas (or equivalent) connection string — never
  `localhost`/`127.0.0.1`.
- If the project selected the Google (or another) sign-in plugin, or an image-uploads plugin,
  `.agentforge/PLUGIN.md` names its environment variables; they deploy the same way as `MONGODB_URI` and
  `SESSION_SECRET`.

## The MongoDB connection

`MONGODB_URI` is asked for and verified for real before it is accepted, not assumed: a value-only
question (`.agentforge/build/question.json`, `"variable": "MONGODB_URI"`, `"secret": true`, `"check":
"mongodb"`) runs `mongo_check.py` against the string — DNS, TCP/TLS reachability, then an actual
`MongoClient` ping — before it is saved, and a loopback address is refused outright. If the project is
already connected (the Studio's Integrations panel records `deploy_mongodb_uri_set`), read it from the
deployment's saved variables rather than asking again. Both EC2 and ECS Fargate have a fixed outbound
address (the instance's Elastic IP, or a NAT gateway for the Fargate task) — put exactly that address on
the Atlas cluster's Network Access list, not `0.0.0.0/0`, since this stack is never served from a
serverless target with no fixed address.

## Health

`server/src/app.js` already answers `/health` (and `/ready`, the same check) with a small JSON body that
says nothing about the database — use that path as the target's health-check route (the ALB target
group's health check on ECS, the `healthCheckPath` setting on Azure, the nginx pass-through on EC2) when
the project has not changed it.

## What "live" means for this stack

Beyond `core` section 10: the built client's home page loads and renders the application's own content
(proof `client/dist` was actually built and is being served, not the 503 placeholder `server/src/app.js`
shows when it is missing); a protected `/api` route refuses a request with no session; a full round trip
through the real UI (sign up or sign in with a real password check, create a document through the API,
read it back) works against the real Atlas cluster, not a local fallback; the session cookie is `Secure`
and `HttpOnly` over HTTPS; and the platform's logs show no connection errors during those requests.

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. AWS EC2 (cheapest, one small instance), AWS ECS Fargate (no server to patch, costs more), or Azure
   App Service? State the trade-off and the estimated monthly cost of each.
2. Is there already a MongoDB Atlas cluster connected for this project, or should one be created now?
3. Which region should the application and the cluster both run in?
4. Should the production database start empty, with only required reference data, or with the demo data
   the specification describes? (Never default to demo accounts on a public address.)
5. If Google (or another OAuth) sign-in is enabled, has its redirect URI been added for the production
   domain with the provider?
6. Does the customer have a custom domain?
7. Which environment variables in `.env.example` should be set now, and which are left for the customer?
