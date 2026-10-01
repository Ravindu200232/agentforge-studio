# MERN microservices scaffold

Stack ID: `mern-microservices`. Root `package.json` is an npm workspace. `client/` is the Vite React UI; `packages/gateway/` is the public HTTP boundary; `packages/testing/` provides test helpers; `scaffold/service/` is an inert service skeleton with `.tpl` manifests. Copy that skeleton into a *new* named package for each required bounded context, remove its `.tpl` suffix only in the new package, connect through the gateway, and add the package to startup orchestration. `scripts/` starts and seeds services. `e2e/` tests the public gateway. Read `README.template.md`, service README and existing app/gateway/config files first. Do not put all domain behavior in the gateway or serve fake in-memory data where persistence is required. Preserve Vite/Tailwind and Vitest workspace configuration.

Local MERN preview is the Vite client at `127.0.0.1:5173`. The API gateway package listens on `127.0.0.1:4000`; internal service packages use `4001` through `4020`. The client proxies `/api` to the gateway. Do not use port 3001 (reserved for Next.js preview) or 5174 (reserved for vite-mongo). Keep deployment and short-lived QA host-provided ports configurable rather than baking local addresses into product code.

## The database is real, not local

Every service's `MONGODB_URI` fallback to `mongodb://127.0.0.1:27017/...` exists only for local development and `npm test` on this machine. The deployed services are given a real, internet-reachable connection string (MongoDB Atlas or any host that is not this computer) - if it is not already set, ask for it as a value-only question (`.agentforge/build/question.json`, `"variable": "MONGODB_URI"`, `"secret": true`, `"check": "mongodb"`, explaining it must not be `localhost`/`127.0.0.1`); the studio tries it for real before accepting it. Never invent or default to a loopback address for this variable in a service's production configuration. Each service may hold its own database within the same cluster (a separate database name per service is the usual microservices pattern), but the connection string itself is the one real cluster the deployment was given.

## Authentication and sign-in

Build real session-based authentication at the gateway (`bcryptjs` for password hashing, signed httpOnly session cookies, verified by each service that needs the caller's identity) - never roll a custom hash. If the project selected the Google (or another) sign-in plugin, `.agentforge/PLUGIN.md` names its environment variables; wire the OAuth flow at the gateway, alongside email/password sign-in, using a well-supported Node OAuth library rather than a hand-rolled redirect/token exchange.

## File and image uploads

If the project selected an image-uploads plugin (Cloudinary, S3, or another), `.agentforge/PLUGIN.md` names its environment variables and how to use them - integrate exactly that provider from whichever service owns the upload, never a locally-written file as the production answer. With no plugin selected, a feature that stores images or other uploaded files still needs a real provider: ask the customer once whether to keep them in Supabase Storage ("Yes — Supabase Storage" recommended). This project has its own Supabase project, and `SUPABASE_URL`, `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY` are already in the environment of every command and of the preview - never ask the customer for them. On yes, upload from the server with the `@supabase/supabase-js` Storage API into a bucket per kind of file, store the object path in the document, and serve public files by their public URL and private ones through signed URLs. On no, ask which provider to use - never write uploads to the local disk as the production answer.

## Deployment

The root `Dockerfile` builds any one package (`--build-arg SERVICE=packages/<name>`) into its own image, so the gateway and every service can each run on its own instance - it needs no edit when a service is added. It is built in the cloud by the deployment flow, never locally. Every package answers `/health` with a body that says nothing about anything behind it; keep that contract when a service's `src/app.js` is extended.
