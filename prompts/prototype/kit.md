# Shared prototype kit

Create one responsive design system and shell used by every prototype page.

Use the approved design tokens, selected design direction and project design skill below. Include practical high-fidelity styles for layout, navigation, cards, forms, tables, buttons, status, dialogs, menus, alerts, loading and responsive behavior. Keep it polished, intentional and production-like; never create wireframe placeholders or a generic corporate UI.

The JavaScript must:
- resolve every `data-go` route from `window.PROTOTYPE.routes`;
- normalise app links to route-map sibling filenames (`rooms.html`), including when a page contains an accidental `fileC:/`, `file:///`, Windows absolute path or root-relative route;
- show role-specific elements and user details;
- support sign-in/sign-out when accounts exist, the signed-in account persisting across pages;
- wire menus, dialogs, tabs, filters, form validation, toasts and theme switching;
- implement `PROTOTYPE.db`: a small, generic client-side database over `window.PROTOTYPE.seed` (written by `assets/seed.js`, loaded before this script — an object of `{table name: [rows...]}`, each row carrying a stable `id`). On first load, when nothing is saved yet, copy `window.PROTOTYPE.seed` into `localStorage` under one key for this prototype; from then on every read and write goes through that saved copy, so what a page creates, edits or deletes is still there on every other page and after a reload. Provide `PROTOTYPE.db.list(table, filter?)`, `.get(table, id)`, `.create(table, row)` (fills in a fresh `id` when the row has none), `.update(table, id, patch)` and `.remove(table, id)`. It must work for whatever tables `window.PROTOTYPE.seed` happens to hold — never hardcode a table or a field name here; that is for the pages to decide.

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

## Project design skill
Read `{{project_design_skill_path}}` yourself with your `read_file` tool.

{{customizer}}

## Routes
{{routes}}

## Sign-in
{{sign_in}}

## Main journeys
{{journeys}}

## Data
This prototype's own sample database (`window.PROTOTYPE.seed`) is written by `assets/seed.js`, which loads before this script — build `PROTOTYPE.db` over it exactly as described above.

## Reference ideas
{{ideas}}

Return only the three marked blocks requested by the system prompt.
