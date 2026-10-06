# Remix + MongoDB scaffold

Stack IDs: `remix-mongo` and `remix-mongo-only` (the same application: they differ only in where uploaded files are kept, see the uploads guide staged beside this one). The root `package.json` runs Remix on Vite. `app/root.jsx` provides the document shell; `app/routes/` owns route modules, loaders and actions; `app/tailwind.css` is the styling entry; `lib/db.js` owns MongoDB access (one cached Mongoose connection); `models/` holds the Mongoose schemas; `scripts/` holds seed/setup utilities; `test/` holds Vitest tests; `e2e/` holds Playwright, axe and screenshot tests. Read `README.template.md`, the route conventions, `.env.example` and the existing files before editing.

Implement every approved screen as a route and every form with actual validated `action` behaviour. Keep server-only code (the database, secrets, password hashing) inside `loader`/`action` functions or `*.server.js` modules, never in code a browser runs: the browser never talks to the database. Add Mongoose schemas under `models/`, validation, authentication and role enforcement for every approved requirement, and check the signed-in user and their role in every loader and action, not only in the interface. Do not replace the scaffold's Vite/Tailwind/test pipeline with a different framework.

The Studio starts the local Remix preview on an isolated port for this project. It supplies `PORT`; `remix-serve` reads it. Do not hard-code a port or reuse another project's preview address.

## The database is already connected - never ask for one, never look for another

The Studio connects this project's MongoDB for you. When the customer has a MongoDB Atlas cluster connected (or an Atlas account the Studio makes one with, before the build writes anything), `MONGODB_URI` and `TEST_MONGODB_URI` are already set in the environment of every command you run and of the preview. They name databases of this project's own on that cluster (`<app>_build` for the seed, the preview and the end-to-end tests, `<app>_test` for the unit tests), so the seed and every test run on a real database. The deployment is handed the same `MONGODB_URI`, so the data your seed makes is the data the deployed application starts with: make the seed idempotent.

- **Use them exactly as they arrive.** The code reads `process.env.MONGODB_URI` (and the test helper `process.env.TEST_MONGODB_URI`). Do not copy them into `.env`, `.env.local` or any other file, do not print them, and do not write or invent a connection string. `.env.example` names the variable and carries no real value.
- **Never ask the customer for the database.** Not a connection string, not a MongoDB address or account, not whether to use Atlas or a local database: none of it is a question for a build. The Studio provides the connection and tells the customer in the chat when nothing is connected.
- **Do not look for a MongoDB on this computer.** Do not start, install, ping or probe one (`mongod`, `mongosh`, Docker, a check of port 27017, a script that connects to `localhost`), and do not write `localhost` or `127.0.0.1` anywhere as the database. The loopback address in the database module, the seed and `.env.example` is only the template's last resort for a computer with no connection at all: it is never something to check, run against or keep. A seed or a test that ran on the cluster has already shown the database works; do not verify it a second time on another one.
- **Never drop a database,** and only ever empty the `*_test` one, between tests.
- **When a command cannot connect,** read what the driver says: it is the real cluster answering (the network, the credentials, a paused cluster) and the Studio has already told the customer. Do not switch to a local database and do not stop to look for one: record a gap naming `MONGODB_URI` in the report and carry on with everything that does not need the data.
- **When `MONGODB_URI` is not set at all,** no cluster is connected and the Studio has said so in the chat. Build the whole application anyway, and record a gap saying the customer connects MongoDB Atlas in Settings; do not stop to look for a database.

## Authentication and sign-in

Build real session-based authentication with `bcryptjs` (password hashing) and `jose` (signed, httpOnly session cookies set from an `action` and read in each `loader`) - never roll a custom hash or a token scheme of your own. If the project selected the Google (or another) sign-in plugin, `.agentforge/PLUGIN.md` names its environment variables; wire it alongside, not instead of, email/password sign-in, using an official OAuth library that works with Remix.

## File and image uploads

If the project selected an image-uploads plugin (Cloudinary, S3, or another), `.agentforge/PLUGIN.md` names its environment variables and how to use them - integrate exactly that provider from an `action`, never a locally-written file as the production answer. With no plugin selected, a feature that stores images or other uploaded files keeps them where this stack's uploads guide (the `uploads-*.md` file staged beside this guide) says.
