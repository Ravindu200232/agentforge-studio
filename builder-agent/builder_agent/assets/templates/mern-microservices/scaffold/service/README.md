# Service skeleton

Copy this whole directory to `packages/<name>` to add a service, then:

1. rename `package.json.tpl` to `package.json` and set `"name"`,
2. rename `test/service.test.js.tpl` to `test/<resource>.test.js`,
3. rename `Item` / `items` throughout to the resource this service owns,
4. route it at the gateway: a URL in `packages/gateway/src/config.js` and a
   line in `packages/gateway/src/app.js`.

`scripts/dev-all.mjs` finds the new service on its own — it looks for
`packages/*/src/server.js` and needs no edit.

This directory is not a workspace and is never installed or run. That is why
the two files above carry a `.tpl` suffix: without it npm would try to install
the skeleton and the project's own `vitest run` would execute its test.

Everything here was verified: copied, installed, tested and started before it
became a skeleton. Keep the shape and change the names.
