# Draw one page

Create one complete, creative, low-fidelity HTML wireframe for the single page
named below. Return HTML only — no commentary, no markdown fence.

This is the wireframe stage after plan approval. The approved `/plan` is the
scope boundary. The site map and application spec live at
`.agentforge/srs/handoff/` — read them yourself before drawing. This call draws
exactly one route; every other route is drawn in its own call, so nothing that
belongs to another route is drawn here. There is no page-count limit.

## What a wireframe is here

A sketch of a screen: what is on it, where, and how the person gets to the next
step. Not a design, not a brand, not a working app. Draw the screen as it looks
to the person using it, with the navigation that screen has. Every word on the
page is the product's own, addressed to the person using it: add no explanatory
notes, and no remarks about the plan, the specification or the wireframe itself.

## Be creative, stay low-fidelity

Do not reach for the same stack of blocks every time. Look at what this page is
*for* and let its data choose the composition: a board of columns, a card grid,
a split list-and-preview, a timeline, a wizard with a step rail, a calendar, a
centred form with one clear action, a summary strip over a table. A sign-in
page, a queue, a report and a settings screen should not look alike.

Use the ideas gathered from the web below as inspiration for the composition,
not as something to copy: take a pattern that fits this page and adapt it.

Low fidelity means outlines, plain type, grey fills, crossed boxes for images
and charts, and no styling that belongs to a finished product. Strictly black,
white and neutral grey: no brand colours, gradients, photos or decorative
blocks. High-contrast borders, strong spacing, and an obvious primary action.

## One page, one job

- Work out this page's one main job from its record and the site map, and draw
  that fully and well.
- A list or table is a page of its own; so is a substantial create or edit form,
  a detail view, or a step of a wizard. If the site map gives one of them its own
  route, it is **not** drawn here in full: this page holds the smallest honest
  way in — a button, a row that links, a three-row preview with "View all" — and
  says where it leads.
- If this page's record really does hold both a table and a form, draw the one
  that is the page's job in full and the other as its entry point: a compact
  quick-add bar, or a button that opens a small popup, with the popup drawn open
  underneath as its own frame. Never a large table and a long form stacked
  together.
- A popup is only for a short, contextual task: confirm, rename, change a status,
  a few fields. Draw both its trigger and its open state.
- Do not repeat the same information in two places, and do not fill space with
  decoration. Do not leave out a section, field, action or state that this page's
  record lists and that belongs on this page.

## One design system

The shared layout below was drawn once for the whole product. Every page begins
from it:

- Keep its `<style>` block exactly as it is (you may add rules after it for
  what only this page needs).
- Use the shell that fits this page (the layout marks each shell with a comment)
  and keep its header, navigation, sidebar and footer exactly as drawn: same
  items, same order, same labels, same size, same position. Only the active item
  changes. A public page uses the signed-out shell; a signed-in page uses the
  shell of its role — never a Sign in link on a signed-in page, never an account
  menu on a signed-out one.
- Reuse its buttons, inputs, tables, cards, tabs and status marks as they are.
  Shared components never change dimensions, spacing or placement from page to
  page; only the content of the page's own area is new.
- The layout is a reference, not a part of the page. Your document holds its
  `<style>` block, the one shell this page uses, and this page's own content —
  never the other shells, never the component kit's showcase area, never a
  second copy of anything.

## What the document must contain

- `<!DOCTYPE html>`, `<html>`, `<head>` with a title and `<meta viewport>`, and a
  `<body>` — one file that opens on its own with no build step and no server.
- All CSS inline in a single `<style>` block. No external stylesheet, font, CDN,
  image or script that needs the network.
- The whole page: the shell, the page's own sections, every control its
  functions need, and the states that matter — loading, empty, error, success —
  drawn where they belong rather than described.
- Realistic sample content throughout: real rows in every table, a real title and
  figure on every card, a plausible typed value in every input, statuses that are
  the values the specification lists. No "Lorem ipsum".
- A layout that holds together at phone width as well as desktop.
- The way forward is obvious: the primary action leads to the next step, and the
  place each secondary action goes is clear.

## The page

- Route: `{{route}}`
- Name: `{{page_name}}`
- Sections the specification gives it: {{sections}}
- Functions it must support: {{functions}}

## The product

{{app_summary}}

## This page's record

{{page_contract}}

## Ideas gathered from the web

{{ideas}}

## The shared layout (start from this)

{{layout}}

## The wireframe plan for this page

This plan was made for the whole product before any page was drawn. Draw every
item it lists for this page, and send each button and link where it says, so
the pages connect into the journeys.

{{wireframe_plan}}

## Approved /plan

{{plan}}

## Site map and application spec

Before drawing, read these two files yourself with your `read_file` tool —
they are not pasted in here:

   - `.agentforge/srs/handoff/sitemap.md`
   - `.agentforge/srs/handoff/app.md`
