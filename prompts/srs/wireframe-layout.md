# Draw the shared layout

Every page of this product is drawn in its own call. So that they still look like
one product, you draw the layout they all start from, once, now. Return one
complete HTML document and nothing else — no commentary, no markdown fence.

## What it contains

**The shells.** Read the site map and draw the shells the product needs: usually
a light one for the pages people see first and a working one, with navigation,
for the rest — but draw as many as the site map really calls for, and one if one
is enough. When people sign in, the public shell is the signed-out one (Sign in,
and Sign up when people may create their own account) and each role that signs
in has its own shell, with only that role's destinations and an account menu
holding the person's name and Sign out. Mark each shell with a comment, `<!-- shell: name — used by: which
pages -->`, and draw it whole:

- the header or app bar, the navigation, a sidebar if this kind of product suits
  one, and the footer;
- the navigation lists every destination the site map gives that shell, in the
  order the site map gives them, under the pages' real names, each linking to its
  route, with the first destination marked as the active one;
- an empty area where the page's own content goes, marked with the comment
  `<!-- page content -->`.

**The component kit.** Below the shells, one clearly separated area, opened with
the comment `<!-- component kit: reference only, never copied into a page -->`,
draws every
recurring component once, in the exact size, spacing and weight the pages will
use: primary, secondary and destructive buttons, a text input, a select, a text
area, a checkbox and a radio, a labelled form row, a table with its header and
two rows, a card, tabs, a status mark, pagination, an empty state, an alert, and
a popup frame with its title, body and actions.

## How it looks

Low fidelity and creative: a composition suited to this kind of product, drawn in
outlines, plain type and grey fills — not the generic header-and-left-sidebar
unless that really is the best fit. Strictly black, white and neutral grey; no
brand colours, gradients or photos. High-contrast borders and generous spacing.
Use the ideas gathered from the web as inspiration, adapted, not copied.

All CSS is inline in one `<style>` block, written with reusable class names and
kept compact (a few short rules per component, not long repeated declarations),
because every page will keep this block exactly as it is and carry it along. Keep
the whole document under about 20,000 characters. No external stylesheet,
font, CDN, image or script that needs the network. The layout must hold together
at phone width: say how the navigation collapses.

This document is the design system, not a page: it has no page-specific content,
nothing about who may see what, and nothing about how anyone signs in.

## The product

{{app_summary}}

## The site map

{{site_map}}

## Ideas gathered from the web

{{ideas}}

## The wireframe plan — shells, navigation and shared components

Draw the shells, their navigation items (in this order, with these labels) and
the shared components exactly as the plan sets them out.

{{plan}}
