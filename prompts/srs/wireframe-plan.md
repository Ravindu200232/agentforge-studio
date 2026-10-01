# Plan the wireframes

The specification is approved. Before any wireframe is drawn, plan all of
them together, so every page is complete and the pages connect into the
journeys. You only plan here; the pages are drawn afterwards, each from its
part of this plan.

Read these first, all in one turn (issue every `read_file` call at once), and
nothing else:

- `.agentforge/srs/handoff/app.md`
- `.agentforge/srs/handoff/sitemap.md`
{{auth}}
## What the plan holds

Write it in Markdown, in exactly this shape:

```
## Shared
- Shells: each shell (for example the public one and one per signed-in area),
  which routes use it, and its navigation items in order, with their labels
  and the route each one opens. A product with sign-in has the public shell
  (signed out: public pages, Sign in, and Sign up when people may create
  their own account) and one signed-in shell per role (that role's own
  destinations and an account menu with Sign out) — never one navigation
  shared by everyone.
- Shared components every page reuses.

## Pages
### `/route` — Page name
- Job: the one main job of this page.
- Shell: which shell it uses and which navigation item is active.
- Content: every section, heading, field, table and its columns, card, list,
  filter, tab, stat, image and state (empty, error, success) it shows.
- Actions: every button and link, and the route it opens — the next step of
  each journey this page is part of goes to that step's page.
- States: what it shows while loading, when empty, on an error and after
  success, and — for a signed-in page — what each role that opens it sees.
- Entry points: for a list, form or detail that has its own route, the small
  way in this page holds and where it leads.
```

- One `###` section for every route below, with the route written exactly as
  it is listed, and no other routes: never add or invent a page.
- Use only the specification's own content, roles and vocabulary.
- Every action that goes somewhere names a route from the list below.
- A step of a journey is reachable from the step before it, and no page is a
  dead end: each has a way forward and a way back.
- Each role that signs in has its own dashboard as its first page, holding
  that role's own figures, waiting items and shortcuts.
- Keep it concrete and short — lists, not prose.

## The routes

{{routes}}

## The journeys (step → page)

{{journeys}}
