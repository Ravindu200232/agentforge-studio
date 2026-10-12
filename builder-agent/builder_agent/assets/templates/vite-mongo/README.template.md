# Scaffolded from the verified Vite + MongoDB template

Everything here was installed, unit-tested and built before it was made a
template. Build the application on top of it.

    npm install
    npm run dev      # Vite client on PORT (or :5174); API server on a free port (4100 when free)
    npm test         # both workspaces
    npm run qa:inventory   # which route, page and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build && npm start

`server/` is the only thing that talks to MongoDB (`server/src/db.js`) and the
only door into it (`server/src/app.js`'s routes, behind `/api`). `client/` is
the Vite React UI; `client/src/api.js` is the one place it calls `/api` -
relative URLs only, so the same bundle works from the dev proxy and from the
built server. After `npm run build`, `npm start` serves the built client and
the API from the same `server/` process on one port, exactly like production.

## What is yours to write

Routes and Mongoose models in `server/src/`, pages and components in
`client/src/`, and the real stylesheet. The placeholder page and the starter
stylesheet are here only so the scaffold builds and renders before any
feature exists.
