# Build the prototype

Read:
- `.agentforge/srs/handoff/app.md`
- `.agentforge/srs/handoff/sitemap.md`
- `.agentforge/srs/handoff/prototype.md`
- every approved HTML wireframe in `.agentforge/srs/wireframes/`
- the approved design

Create the static clickable prototype in `.agentforge/prototype/`.

Read the handoff, route map and each approved wireframe before its page is drawn. Draw pages one at a time. Use wireframes only as functional blueprints for content, images, button destinations and next-page flow. Produce a high-fidelity real product UI from the approved visual design; never copy wireframe styling, placeholder blocks or annotations. Keep every route connected. When a route or flow is unclear, reread the supplied blueprint and flow instead of guessing.

Write one HTML file per route plus `assets/app.css`, `assets/app.js`, `assets/flow.js` and `routes.json`.

## Browser render check

This prototype is already served as a small static site by the studio itself, at
`http://127.0.0.1:7824/__agentforge/api/prototype/<project>/<file>` — `<project>` is this project's
id and `<file>` is each route's `file` entry in `routes.json` (`/` serves as `index.html`). After a
page is written, call `browser_inspect` with that page's exact URL at `desktop`, then again at
`mobile`, before moving to the next route. Read the layout facts it returns — horizontal overflow,
clipped labels, controls under 24px, broken or pending images, missing `alt` — and look at the saved
screenshot for real visual defects: misaligned or overlapping elements, wrong sizing, cropped
content, a layout that doesn't match the approved design. Fix a real defect directly in that page's
HTML/CSS or the shared kit, then re-inspect only that page once. A pending image on a slow first
paint is not automatically broken — judge it from the screenshot, not the flag alone.

This is a rendering check, not a test suite: do not write test files, test commentary, or assertions
anywhere in the prototype. Do not re-inspect a page that already looked correct on its first pass.
Finish after every route has been drawn and checked once at both viewports and all links resolve.
