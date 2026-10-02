# Scaffolded from the Remix + MongoDB template

Build the application on top of it.

    npm install
    npm run dev
    npm test
    npm run qa:inventory   # which page, route and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build && npm start

This is **Remix v2 on Vite**, so there is no `remix.config.js` - the
framework's options are the `remix()` plugin's in `vite.config.js`, and a file
of that name is ignored.

A route is a file under `app/routes/`. `_index.jsx` serves `/`; a dot in a
filename is a path separator, and a leading underscore is a segment that does
not appear in the URL.

`lib/db.js` holds the cached MongoDB connection - import `connectDb` from it (in a `loader`, an `action` or a
`*.server.js` module) rather than calling `mongoose.connect` anywhere else. Models go in `models/`, and data access
in `lib/`. The browser never talks to the database.

`vitest.config.js` does not load the Remix plugin, on purpose: it rewrites
route modules for the framework's loader/action split and expects a Remix
request in flight, which under the test runner there is not. Server code is tested in Node: start the file
with `// @vitest-environment node`.
