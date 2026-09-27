# Shared prototype kit

Create one responsive design system and shell used by every prototype page.

Use the approved design tokens, selected design direction and Premium Frontend Design Engineer skill below. Include practical high-fidelity styles for layout, navigation, cards, forms, tables, buttons, status, dialogs, menus, alerts, loading and responsive behavior. Keep it polished, intentional and production-like; never create wireframe placeholders or a generic corporate UI.

The JavaScript must:
- resolve every `data-go` route from `window.PROTOTYPE.routes`;
- normalise app links to route-map sibling filenames (`rooms.html`), including when a page contains an accidental `fileC:/`, `file:///`, Windows absolute path or root-relative route;
- show role-specific elements and user details;
- support sign-in/sign-out when accounts exist;
- wire menus, dialogs, tabs, filters, form validation, toasts and theme switching.

The shell must use the route map, keep shared navigation consistent, include the literal `<!-- page content -->` marker, and contain working `data-go="/route"` links. The shell and kit must use sibling relative filenames resolved from the route map, never filesystem or root-relative app URLs.

You have a small, fixed number of tool calls for this task. Read exactly the
two files named below with `read_file` — nothing else. Do not call
`list_files` or `search_text` first to "see what's there": both paths are
already exact and correct. Every other input you need (routes, sign-in,
journeys, reference ideas) is already given to you as text below, not as
something to go read. After those two reads, answer — do not keep exploring.

## Design
Read `{{design_spec_path}}` yourself with your `read_file` tool — the approved
design tokens are not pasted in here.

## Premium frontend skill
Read `{{premium_frontend_skill_path}}` yourself with your `read_file` tool.

{{design_md}}

{{customizer}}

## Routes
{{routes}}

## Sign-in
{{sign_in}}

## Main journeys
{{journeys}}

## Reference ideas
{{ideas}}

Return only the three marked blocks requested by the system prompt.
