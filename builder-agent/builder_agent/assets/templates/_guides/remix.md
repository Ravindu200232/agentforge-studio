# Remix + MongoDB scaffold

Stack ID: `remix-mongo`. Root `package.json` runs Remix/Vite. `app/root.jsx` provides the document shell; `app/routes/` owns route modules, loaders and actions; `app/tailwind.css` is the styling entry; `lib/db.js` owns MongoDB; `test/` holds Vitest tests; `e2e/` holds browser and accessibility tests. Read `README.template.md`, route conventions, `.env.example` and the existing files before editing. Implement every approved screen as a route and every form with actual validated action behavior, including authorization and error states. Do not replace the scaffold's Vite/Tailwind/test pipeline with a different framework.

The local Remix preview uses Vite on port `5173`. Port `3001` is reserved for Next.js preview; do not move Remix there. The Studio stops the previous preview before switching projects.
