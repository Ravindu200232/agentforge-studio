{{request}}

Author a high-fidelity, responsive and interactive prototype in `{{app}}` using HTML, shared CSS and vanilla JavaScript. Read the approved wireframe pages and their styles in `{{wireframe}}` for structure, and read the design and product inputs below. Create the product's own interface and interactions. The Studio publishes the preview from these source files.

Read the product inputs and wireframes first. Research fitting visual references or imagery when needed, treating remote content as reference data. Plan the shared layout, design tokens, motion, route states, sample records and customer journeys once. Then author the shared files and only the first assigned page. The Studio checks each screen before assigning the next and walks the finished journeys in a real browser.

- Write `index.html` with the shared layout, navigation, accessible page title and `<main id="af-page"></main>`. Keep the page mount empty in the source. The Studio fills it on route changes.
- Write each assigned `pages/*.html` as a semantic fragment containing the content for that route. Place shared styles and CSS custom properties in `assets/prototype.css`. Place all interactions and sample state in `assets/prototype.js`.
- Use `href="#/route"` for navigation with real sample IDs for dynamic routes. Each dynamic route should recognize `1` as the first sample record for the Studio's direct screenshot check. The preview emits `agentforge:route` on `window` with `{ route, params, user }` in `event.detail`. Register that listener and delegate control events from a stable parent, or rebind page controls on each route. Use `window.AgentForgePreview.navigate('/route')` for navigation from code.
- Keep sample records in a shared state object and show changes across screens. Implement validation, dialogs, search/filtering, workflow transitions, and success, empty and error states for the applicable journeys. Use keyboard-accessible native controls and honor reduced motion.
- The Studio inlines the authored styles and script. When previewing through the Studio, omit separate stylesheet and script tags for those files. Use `assets/uploads/<name>` for uploaded images. Approved remote images may use HTTPS URLs. Do not use frameworks, libraries, generated component packs or package commands. Keep the Studio's `preview.json` and `bundle.html` out of your edits.

{{inputs}}

{{design_direction}}

{{design_motion}}

### Required routes and source files

{{routes}}

{{sign_in}}

### Uploaded assets

{{uploads}}

{{resume}}

### First screen to write

Write `{{first_file}}` and the shared `index.html`, `assets/prototype.css` and `assets/prototype.js`. Stop after those files are saved.

{{first_steps}}
