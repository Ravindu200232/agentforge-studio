# Silent prototype plan

Make one concise internal plan for drawing the approved clickable prototype. Do not ask the customer for approval and do not write or edit product files while planning; the plan is approved automatically and the drawing stage follows it immediately.

Before writing the plan, read the complete product context that is already in this workspace:

- `.agentforge/srs/handoff/app.md` and `.agentforge/srs/handoff/sitemap.md`;
- the approved SRS plan and every approved HTML wireframe in `.agentforge/srs/wireframes/`;
- `.agentforge/design/design-spec.json` and any staged selected-theme guidance;
- the approved route and journey information supplied with this request.

## Approved design-customizer output

{{customization}}

## Additional customer direction

{{customer_direction}}

Use the wireframes as functional blueprints, never as the finished visual style. Do not miss or silently drop any wireframe content: preserve every visible section, label, field, table, card, image reference, action, validation, button destination, state and journey step. Do not invent a guard, restriction, feature, page or route that is not supported by the wireframe, `app.md` or `sitemap.md`; authentication and role access are enforced only when those approved sources require them. Use the approved design-customizer output as the visual source of truth. State how the shared kit will provide realistic sample data through `PROTOTYPE.db`, role-based demo accounts and each role's correct landing route when authentication exists. Return a short ordered plan covering: inputs read, shared kit, data/auth flow, route map and one-at-a-time page generation. Make safe assumptions instead of stopping with questions.

Return Markdown only.
