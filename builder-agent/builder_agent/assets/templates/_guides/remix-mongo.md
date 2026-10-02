# Remix + MongoDB scaffold

Stack IDs: `remix-mongo` and `remix-mongo-only` (the same application: they differ only in where uploaded files are kept, see the uploads guide staged beside this one). The root `package.json` runs Remix on Vite. `app/root.jsx` provides the document shell; `app/routes/` owns route modules, loaders and actions; `app/tailwind.css` is the styling entry; `lib/db.js` owns MongoDB access (one cached Mongoose connection); `models/` holds the Mongoose schemas; `scripts/` holds seed/setup utilities; `test/` holds Vitest tests; `e2e/` holds Playwright, axe and screenshot tests. Read `README.template.md`, the route conventions, `.env.example` and the existing files before editing.

Implement every approved screen as a route and every form with actual validated `action` behaviour. Keep server-only code (the database, secrets, password hashing) inside `loader`/`action` functions or `*.server.js` modules, never in code a browser runs: the browser never talks to the database. Add Mongoose schemas under `models/`, validation, authentication and role enforcement for every approved requirement, and check the signed-in user and their role in every loader and action, not only in the interface. Do not replace the scaffold's Vite/Tailwind/test pipeline with a different framework.

The Studio starts the local Remix preview on an isolated port for this project. It supplies `PORT`; `remix-serve` reads it. Do not hard-code a port or reuse another project's preview address.

## The database is real, not local

`lib/db.js`'s fallback (`mongodb://127.0.0.1:27017/...`) exists only so `npm test` and local development have something to connect to on this machine. It is never what a deployed application uses. Before this app can be deployed, `MONGODB_URI` must be a real, internet-reachable connection string (MongoDB Atlas or any host that is not this computer) - if it is not already set, it is the customer's to supply, asked for before the plan as a value-only question (`"variable": "MONGODB_URI"`, `"secret": true`, `"check": "mongodb"`, explaining it must not be `localhost`/`127.0.0.1`); the studio tries it for real before accepting it. Once the build is planned it never stops to ask, so a build that still has no real connection string records an `"unavailable"` gap naming `MONGODB_URI`. Never invent or default to a loopback address for this variable.

## Authentication and sign-in

Build real session-based authentication with `bcryptjs` (password hashing) and `jose` (signed, httpOnly session cookies set from an `action` and read in each `loader`) - never roll a custom hash or a token scheme of your own. If the project selected the Google (or another) sign-in plugin, `.agentforge/PLUGIN.md` names its environment variables; wire it alongside, not instead of, email/password sign-in, using an official OAuth library that works with Remix.

## File and image uploads

If the project selected an image-uploads plugin (Cloudinary, S3, or another), `.agentforge/PLUGIN.md` names its environment variables and how to use them - integrate exactly that provider from an `action`, never a locally-written file as the production answer. With no plugin selected, a feature that stores images or other uploaded files keeps them where this stack's uploads guide (the `uploads-*.md` file staged beside this guide) says.
