---
name: wireframe-generation
category: wireframe
description: Draws one application screen as a Low-Fidelity / Mid-Fidelity wireframe in classic Balsamiq / Figma blueprint style - strictly monochrome, crossed-box image placeholders, realistic sample data - as sections that drop into the studio's own wireframe shell.
match:
  - wireframe
  - wireframes
  - blueprint
  - low-fidelity
  - mid-fidelity
  - balsamiq
requires:
  - functional-requirements
---

# Wireframe Generation Skill (Balsamiq / Figma Blueprint Style)

You are drawing one screen of a classic Low-Fidelity / Mid-Fidelity wireframe:
outlined boxes, an X through every image, realistic sample data, no colour.

## What to return

The document, the browser chrome, the stylesheet and the legend are written by
`generators/wireframe_html.py` and wrap what you return. Write **only** the
page's `<section>` elements, in reading order.

No `<!DOCTYPE>`, no `<html>`, `<head>`, `<body>` or `<style>`, no `<script>`,
and never an `<svg>` - there is no vector markup in this document at all.

Draw the page and nothing *about* the page. No annotation badges, no section
name tags, no grid or guide overlay, no "wireframe mode" bar: a reviewer opens
this to see the screen, not notes written over it.

## The design system, already defined

Use these class names rather than restyling:

| Class | What it is |
|---|---|
| `.wf-box` | a 2px black outlined white box; `.wf-box-thin` is the 1px one |
| `.wf-fill` | `#F3F4F6` fill; `.wf-fill-2` is `#E5E7EB`, for a heavier band |
| `.wf-img` | the image placeholder: a bordered box with a black X corner to corner, drawn in CSS |
| `.wf-btn` | a wireframe button; `.wf-btn-fill` is the one primary action, `.wf-btn-sm` the small one |
| `.wf-input` | an outlined input; `.wf-label-sm` is the small caps label above it |
| `.sk` | a grey bar standing in for a line of body copy; `.sk-thin` is the secondary line |
| `.wf-tag` | a small dashed badge for a status, a count or a pill on a card - real content, never a label about the design |

The image placeholder takes its size inline and says what belongs there:

```html
<div class="wf-img" style="height:320px">
  <span class="wf-label">HERO IMAGE 16:9</span>
</div>
```

Use it for every image, banner, avatar, logo, thumbnail, map and chart.

Body copy is `.sk` bars with an inline width, never Lorem Ipsum:

```html
<span class="sk" style="width:94%"></span>
<span class="sk sk-thin" style="width:70%"></span>
```

## Layout

Tailwind is loaded, so use its utilities for layout, spacing and type: `grid`,
`flex`, `gap`, `px-8`, `py-12`, `text-2xl`, `font-bold`. Never use a Tailwind
**colour** utility - the wireframe is black, white and grey by definition.
Separate sections with `border-t-2 border-black`.

Compose an attractive, calm and usable page rather than a pile of boxes. Use a
clear reading order, one dominant action, balanced columns, consistent alignment,
purposeful whitespace and grouped task areas. Avoid one very long dense stack,
needless repeated panels and controls packed edge to edge.

Every route belongs to the same product. Keep shared UI patterns identical
across all pages: navigation structure and order, header/sidebar/footer geometry,
button hierarchy, form fields, cards, tables, status styles, spacing rhythm and
responsive collapse behaviour. Preserve the same labels and placement for the
same shared action. Change the page body to fit its task without redesigning the
product shell.

There is no page-count target to optimize for. Keep tables/list management,
record details and substantial create/edit or multi-step forms on focused pages
when the workflow supports separate routes. Use a popup only for a small
contextual task such as confirmation, rename, status change or a few fields, and
show both its trigger and its open state clearly. Never combine a large table
and a long form into one crowded page simply to avoid another screen.

## Sample data is the point

Every table gets real rows, every card a real title and figure, every input a
plausible typed value, every status one of the values the specification listed
for that column. A wireframe full of empty boxes tells a reviewer nothing about
whether the screen is right.

Draw the whole page - all of the sections listed for it, at the depth a real
screen has. Return the sections only, starting at `<section`.
