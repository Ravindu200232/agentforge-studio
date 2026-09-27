# Scaffolded from the verified Remix + MongoDB template

Everything here was installed, unit-tested, built, started and served before it
was made a template. Build the application on top of it.

    npm install
    npm run dev
    npm test
    npm run qa:inventory   # which page, route and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build && npm start

This is **Remix v2 on Vite**, so there is no `remix.config.js` — the
framework's options are the `remix()` plugin's in `vite.config.js`, and a file
of that name is ignored.

A route is a file under `app/routes/`. `_index.jsx` serves `/`; a dot in a
filename is a path separator, and a leading underscore is a segment that does
not appear in the URL.

`lib/db.js` holds the cached connection — import `connectDb` from it rather
than calling `mongoose.connect` anywhere else, and import it only from a
`loader` or an `action`. Both run on the server, which is what keeps Mongoose
out of the browser bundle; importing it into a component puts it there and the
build fails on Node built-ins.

`vitest.config.js` does not load the Remix plugin, on purpose: it rewrites
route modules for the framework's loader/action split and expects a Remix
request in flight, which under the test runner there is not.
