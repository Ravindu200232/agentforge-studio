# Vite + MongoDB build prompt

Author an npm workspace with client/ and server/. Write the Vite configuration and React entries in client/, with a relative /api client and development proxy. Create Express route modules and the server/src/server.js entry. Configure Mongoose there, bind the assigned PORT, route /api before the history fallback, and serve client/dist in production. Root scripts start the client and server and build client/dist. Follow the exact stack's uploads guide.

`npm run dev` (`scripts/dev-all.mjs`) starts both. `PORT` is the one port a browser opens: the Vite client in development, the server in production. The Studio gives every project's preview a private `PORT` of its own, so the server takes a free port (4100 when free) and the client proxies `/api` to it. After `npm run build`, `server/src/app.js` serves the built client directly from the same process and port, so `npm start` alone is a complete production run. The server is the only thing MongoDB-reachable. Never require, check for or kill a fixed port in `dev-all.mjs`. When the Studio sets `AGENTFORGE_PORTS_FILE`, `dev-all.mjs` writes each part it starts there (name, port, folder, command) for the Studio's Ports view; keep that list complete if you add a part.

## The database is already connected - never ask for one, never look for another

The Studio connects this project's MongoDB for you. When the customer has a MongoDB Atlas cluster connected (or an Atlas account the Studio makes one with, before the build writes anything), `MONGODB_URI` and `TEST_MONGODB_URI` are already set in the environment of every command you run and of the preview. They name databases of this project's own on that cluster (`<app>_build` for the seed, the preview and the end-to-end tests, `<app>_test` for the unit tests), so the seed and every test run on a real database. The deployment is handed the same `MONGODB_URI`, so the data your seed makes is the data the deployed application starts with: make the seed idempotent.

- **Use them exactly as they arrive.** The code reads `process.env.MONGODB_URI` (and the test helper `process.env.TEST_MONGODB_URI`). Do not copy them into `.env`, `.env.local` or any other file, do not print them, and do not write or invent a connection string. `.env.example` names the variable and carries no real value.
- **Never ask the customer for the database.** Not a connection string, not a MongoDB address or account, not whether to use Atlas or a local database: none of it is a question for a build. The Studio provides the connection and tells the customer in the chat when nothing is connected.
- **Do not look for a MongoDB on this computer.** Do not start, install, ping or probe one (`mongod`, `mongosh`, Docker, a check of port 27017, a script that connects to `localhost`), and do not write `localhost` or `127.0.0.1` anywhere as the database.
- **Never drop a database,** and only ever empty the `*_test` one, between tests.
- **When a command cannot connect,** read what the driver says: it is the real cluster answering (the network, the credentials, a paused cluster) and the Studio has already told the customer. Do not switch to a local database and do not stop to look for one: record a gap naming `MONGODB_URI` in the report and carry on with everything that does not need the data.
- **When `MONGODB_URI` is not set at all,** no cluster is connected and the Studio has said so in the chat. Build the whole application anyway, and record a gap saying the customer connects MongoDB Atlas in Settings; do not stop to look for a database.

## Authentication and sign-in

Build real session-based authentication with `bcryptjs` (password hashing) and `jose` (signed, httpOnly session cookies) - never roll a custom hash or a token scheme of your own. If the project selected the Google (or another) sign-in plugin, `.agentforge/PLUGIN.md` names its environment variables; wire it into `server/`, alongside, not instead of, email/password sign-in, using a well-supported Node OAuth library rather than a hand-rolled redirect/token exchange.

## File and image uploads

If the project selected an image-uploads plugin (Cloudinary, S3, or another), `.agentforge/PLUGIN.md` names its environment variables and how to use them - integrate exactly that provider from `server/`, never a locally-written file as the production answer. With no plugin selected, a feature that stores images or other uploaded files keeps them where this stack's uploads guide (the `uploads-*.md` file staged beside this guide) says.
