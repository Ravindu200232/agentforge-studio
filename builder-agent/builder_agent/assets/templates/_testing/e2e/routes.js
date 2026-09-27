// The app's pages, for the checks that visit every one of them.
// QA writes e2e/routes.json from the sitemap:
//   [{ "route": "/", "name": "Home" }, { "route": "/dashboard", "name": "Dashboard", "roles": ["member"] }, ...]
//
// A page with `roles` (or `"auth": true`) needs a signed-in visitor. A signed-out
// browser only ever sees the sign-in page there, so those pages are not screenshotted,
// axe-checked or Lighthouse-scored as if they were the page itself: smoke.spec.js
// proves they refuse a signed-out visitor, and the journeys prove them signed in.
// A route with a parameter (`[id]` or `:id`) is left out: it needs a real record,
// which a journey provides.
import fs from 'node:fs'

const file = new URL('./routes.json', import.meta.url)

function listed() {
  let text
  try {
    text = fs.readFileSync(file, 'utf8')
  } catch {
    return [{ route: '/', name: 'Home' }] // no file yet: the home page
  }
  // A file that exists but cannot be read is an error, not "just the home page": a BOM
  // (PowerShell writes one) or a stray comma used to shrink every check to a single page.
  return JSON.parse(text.charCodeAt(0) === 0xfeff ? text.slice(1) : text)
}

const concrete = row => row?.route && !/\[|\/:/.test(row.route)

export const isProtected = row => row?.auth === true || (Array.isArray(row?.roles) && row.roles.length > 0)

/** Every concrete page, protected or not. */
export const routes = () => listed().filter(concrete)

/** Pages a signed-out visitor can open. */
export const publicRoutes = () => routes().filter(row => !isProtected(row))

/** Pages that must refuse a signed-out visitor. */
export const protectedRoutes = () => routes().filter(isProtected)

export const slug = route => route.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '') || 'home'
