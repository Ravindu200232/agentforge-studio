Create the shared CSS, JavaScript and shell for a static clickable prototype.

Return exactly these three blocks and nothing else:

===== assets/app.css =====
...
===== assets/app.js =====
...
===== shell.html =====
...

Create a high-fidelity shared product design system: polished responsive layout, real image treatment, deliberate hierarchy and usable controls. Do not use wireframe placeholders, grey mock-up blocks or annotation styling. The JavaScript should wire `data-go` routes, role visibility, session controls, menus, dialogs, forms, filters and theme switching from `window.PROTOTYPE`. The shell should contain the shared header/navigation/footer and a literal `<!-- page content -->` marker.

Hard integration requirements: keep that exact marker in `shell.html`; include at least one real shell navigation element with `data-go="/"`; use route-map values for `data-go` and sibling HTML filenames in `href`; never emit `fileC:`, `file:///`, `C:/`, `C:\\` or root filesystem URLs. This block format and the shared-kit contract take precedence over any standalone-artifact output format in the design skill.

Do not include tests, commentary or markdown fences.
