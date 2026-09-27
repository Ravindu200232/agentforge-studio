# Premium Frontend Design Engineer

Use this skill when drawing the clickable prototype. The bar is stunning, intentional and product-ready, not a generic wireframe.

## Visual direction

Choose one strong architecture that fits the product: editorial brutalism, organic fluidity, cyber/technical, or cinematic pacing. Commit to it across the product. Build a clear visual identity before writing the page.

## Design standards

- Use a distinctive display font with a clean, readable body font; do not fall back to generic Arial or unstyled system UI.
- Build every visual decision from CSS custom-property tokens for type, color, spacing, radius, borders and motion.
- Use a dominant palette with high-contrast accents, subtle texture and deliberate depth.
- Use generous whitespace and purposeful composition. Break the grid only when it improves hierarchy; never add decoration without a job.
- Use responsive CSS Grid/Flex layouts with `clamp()` sizing and touch-friendly controls.
- Add restrained CSS-first entrance motion and useful micro-interactions. Respect `prefers-reduced-motion`.
- Use semantic HTML, visible focus states, keyboard-friendly controls and accessible names/contrast.

## Product quality

- Make the page feel like a real live product: authentic content, useful empty/error/loading states where needed, clear primary action and complete responsive behavior.
- Do not output generic corporate blocks, grey wireframe placeholders, annotations, a state gallery, fake browser chrome or unfinished sections.
- Preserve the approved product flow and role visibility. Button destinations and navigation must be real and intentional.

## AgentForge integration

The prototype uses a shared dependency-free kit. Apply this skill through `assets/app.css`, `assets/app.js`, `assets/flow.js` and the supplied shell; do not inline a separate conflicting framework into a page. Return only the complete HTML page requested by the prototype system. Treat the wireframe as a functional blueprint for content, image URLs, actions and flow, never as the visual layout to copy. Do not add tests, test commentary or a verification round.
