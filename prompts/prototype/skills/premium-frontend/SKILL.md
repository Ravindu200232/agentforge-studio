# Premium Frontend Design Engineer

Use this skill when drawing the clickable prototype. The bar is stunning, intentional and product-ready, not a generic wireframe.

## Visual direction

Before writing the first page, decide and hold yourself to four things, grounded in the approved brief rather than a default template:

- **Subject and audience** — what this product is and who is looking at it; let that decide the tone (editorial brutalism, organic fluidity, cyber/technical, cinematic pacing, or another architecture that actually fits) rather than reaching for whichever is most familiar.
- **Palette** — a dominant palette with high-contrast accents, chosen for this product, not a generic SaaS blue-and-white default.
- **Typography** — a distinctive display font paired with a clean, readable body font; never generic Arial or unstyled system UI.
- **One deliberate aesthetic risk** — a specific choice that makes this design memorable rather than safe (an unusual layout rhythm, a bold type pairing, an unexpected but purposeful motion or color move) — small enough to stay usable, real enough to be visible on every page.

Commit to all four across the entire product; a later page contradicting an earlier one is a defect, not variety.

## Design standards

- Build every visual decision from CSS custom-property tokens for type, color, spacing, radius, borders and motion.
- Use generous whitespace and purposeful composition. Break the grid only when it improves hierarchy; never add decoration without a job.
- Use responsive CSS Grid/Flex layouts with `clamp()` sizing and touch-friendly controls (44px minimum target size).
- Add restrained CSS-first entrance motion and useful micro-interactions. Respect `prefers-reduced-motion`.

## Accessible by construction

Build these in while drawing the page, not as a later pass — each is a real POUR requirement (Perceivable, Operable, Understandable, Robust), not a style preference:

- **Perceivable** — body text at 4.5:1 contrast against its background, large text/UI components at 3:1; every meaningful image has real `alt` text describing what it shows, and a purely decorative image has `alt=""`; never convey a state (error, required, selected) by color alone.
- **Operable** — every interactive element reachable and usable by keyboard alone, with a visible focus state that isn't the browser default outline removed with nothing put back; a logical tab order that follows the visual layout; no control that only responds to hover.
- **Understandable** — one `<h1>` per page and a heading hierarchy with no skipped levels; form fields with real associated `<label>`s, not placeholder text standing in for one; error and validation messages tied to their field, not just colored red.
- **Robust** — semantic HTML elements (`nav`, `main`, `header`, `footer`, `button`, not a `div` wearing an `onclick`) and landmark regions a screen reader can navigate by.

## Product quality

- Make the page feel like a real live product: authentic content, useful empty/error/loading states where needed, clear primary action and complete responsive behavior.
- Do not output generic corporate blocks, grey wireframe placeholders, annotations, a state gallery, fake browser chrome or unfinished sections.
- Preserve the approved product flow and role visibility. Button destinations and navigation must be real and intentional.

## AgentForge integration

The prototype uses a shared dependency-free kit. Apply this skill through `assets/app.css`, `assets/app.js`, `assets/flow.js` and the supplied shell; do not inline a separate conflicting framework into a page. Return only the complete HTML page requested by the prototype system. Treat the wireframe as a functional blueprint for content, image URLs, actions and flow, never as the visual layout to copy. Do not write test files or test commentary; the one browser render check `generate.md` describes is the only verification round this phase runs.
