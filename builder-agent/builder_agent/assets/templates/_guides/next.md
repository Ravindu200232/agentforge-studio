# Next.js + MongoDB scaffold

Stack ID: `nextjs-mongo`. The root `package.json` runs Next.js; `app/` owns pages and layouts; `app/api/` owns HTTP endpoints; `lib/db.js` owns MongoDB access; `test/` holds Vitest tests; `e2e/` holds Playwright, axe and screenshot tests. `scripts/` holds seed/setup utilities. Read `README.template.md`, the existing files and `.env.example` before changing them. Replace the placeholder home screen, not the working runner configuration. Keep server-only credentials out of client components. Add route files, data models, validation, authentication and role enforcement for every approved requirement. Preserve the Tailwind/PostCSS pipeline when editing CSS or package dependencies.

The local Next.js preview uses port `3001`; the Vite-based MERN and Remix previews use `5173`. Keep the selected stack's port rather than reusing another stack's preview address.
