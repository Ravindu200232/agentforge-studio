# MERN microservices build prompt

Author an npm workspace with client/, packages/gateway/ and packages for the approved bounded contexts. Write a Vite React client, an Express gateway for the public HTTP API and built client, and separately testable MongoDB services. Write scripts/start-all.mjs to coordinate processes and pass the assigned port and environment to each. Include dev/start/build scripts and a deployment Dockerfile with a SERVICE build argument. Follow the exact stack's uploads guide.

`npm run dev` (`scripts/dev-all.mjs`) starts everything. `PORT` is the one port a browser opens: the Vite client in development, the gateway in production (`npm start`). The Studio gives every project's preview a private `PORT` of its own, so the gateway and the services take free ports (4000 and 4001+ when free), and every package is handed the whole address map (`<NAME>_URL`/`<NAME>_PORT`, `GATEWAY_URL`). The client proxies `/api` to the gateway. Keep it that way when you extend `dev-all.mjs`: never require, check for or kill a fixed port, and never write a local address into product code - read the address a package is given. When the Studio sets `AGENTFORGE_PORTS_FILE`, `dev-all.mjs` writes every part it starts there (name, port, folder, command, address variables) so the Studio's Ports view can show which ones listen; a part you start some other way goes into that list too.

## The database is already connected - never ask for one, never look for another

The Studio connects this project's MongoDB for you. When the customer has a MongoDB Atlas cluster connected (or an Atlas account the Studio makes one with, before the build writes anything), `MONGODB_URI` and `TEST_MONGODB_URI` are already set in the environment of every command you run and of the preview. They name databases of this project's own on that cluster (`<app>_build` for the seed, the preview and the end-to-end tests, `<app>_test` for the unit tests), so the seed and every test run on a real database. The deployment is handed the same `MONGODB_URI`, so the data your seed makes is the data the deployed application starts with: make the seed idempotent.

- **Use them exactly as they arrive.** The code reads `process.env.MONGODB_URI` (and the test helper `process.env.TEST_MONGODB_URI`). Do not copy them into `.env`, `.env.local` or any other file, do not print them, and do not write or invent a connection string. `.env.example` names the variable and carries no real value.
- **Never ask the customer for the database.** Not a connection string, not a MongoDB address or account, not whether to use Atlas or a local database: none of it is a question for a build. The Studio provides the connection and tells the customer in the chat when nothing is connected.
- **Do not look for a MongoDB on this computer.** Do not start, install, ping or probe one (`mongod`, `mongosh`, Docker, a check of port 27017, a script that connects to `localhost`), and do not write `localhost` or `127.0.0.1` anywhere as the database.
- **Never drop a database,** and only ever empty the `*_test` one, between tests.
- **When a command cannot connect,** read what the driver says: it is the real cluster answering (the network, the credentials, a paused cluster) and the Studio has already told the customer. Do not switch to a local database and do not stop to look for one: record a gap naming `MONGODB_URI` in the report and carry on with everything that does not need the data.
- **When `MONGODB_URI` is not set at all,** no cluster is connected and the Studio has said so in the chat. Build the whole application anyway, and record a gap saying the customer connects MongoDB Atlas in Settings; do not stop to look for a database.

Each service may hold its own database within the same cluster (a separate database name per service is the usual microservices pattern), but the connection string itself is the one cluster the Studio connected.

## Authentication and sign-in

Build real session-based authentication at the gateway (`bcryptjs` for password hashing, signed httpOnly session cookies, verified by each service that needs the caller's identity) - never roll a custom hash. If the project selected the Google (or another) sign-in plugin, `.agentforge/PLUGIN.md` names its environment variables; wire the OAuth flow at the gateway, alongside email/password sign-in, using a well-supported Node OAuth library rather than a hand-rolled redirect/token exchange.

## File and image uploads

If the project selected an image-uploads plugin (Cloudinary, S3, or another), `.agentforge/PLUGIN.md` names its environment variables and how to use them - integrate exactly that provider from whichever service owns the upload, never a locally-written file as the production answer. With no plugin selected, a feature that stores images or other uploaded files keeps them where this stack's uploads guide (the `uploads-*.md` file staged beside this guide) says.

## Deployment

Write the root `Dockerfile` to build one package (`--build-arg SERVICE=packages/<name>`) into its own image, so the gateway and services can run on separate instances. It is built in the cloud by the deployment flow, never locally. Every package answers `/health` with a body that says nothing about anything behind it; keep that contract when a service's `src/app.js` is extended.
