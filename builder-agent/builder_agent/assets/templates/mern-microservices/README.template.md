# Scaffolded from the verified MERN + microservices template

Everything here was installed, unit-tested and built
before it was made a template. Build the application on top of it.

    npm install
    npm run dev      # Vite UI on PORT (or :5173); gateway and services on free ports (4000, 4001+ when free)
    npm test         # every workspace that has tests
    npm run qa:inventory   # which route, page and component has no unit test of its own (exit 1 until none)
    npm run test:coverage  # what the unit tests execute, per file
    npm run build    # the client bundle the gateway serves

If Vite cannot start, local preview serves the last client build on the same port and
proxies `/api` to the gateway. Rebuild after changing the client to refresh it.

## Adding a service

Copy `scaffold/service` to `packages/<name>` and follow the README inside it:
rename the two `.tpl` files, rename `Item`/`items` to the resource the service
owns, and route it at the gateway.

`scripts/dev-all.mjs` finds it on its own — it looks for
`packages/*/src/server.js` and needs no edit. Neither does the root `Dockerfile`: it builds
whichever package a deployment names (`--build-arg SERVICE=packages/<name>`), so a new service is
deployable to its own instance the moment it exists.

## What is yours to write

Models, routes, pages, components, each service's own `src/server.js`, and the
real stylesheet. The placeholder page/component and the starter stylesheet are
here only so the scaffold builds and renders before any feature exists.

## Test layout

Each workspace owns its runner config, and `vitest.workspace.js` at the root
ties them together, so `npm test` and a bare `vitest run` both do the right
thing. Shared helpers live in `packages/testing`:

    import { connectTestDb, clearCollections, closeTestDb, request } from 'testing';
