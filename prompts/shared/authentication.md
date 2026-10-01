# Authentication, roles and navigation

The standard for how people sign up, sign in, stay signed in, see their own area and sign out — for the
wireframes, the prototype and the real application alike. app.md decides **what exists**: the roles, which pages
need sign-in and for whom, whether people may create their own account and which role it gets, who creates the
other accounts. This file decides **how it works**. Use only the roles, pages and fields app.md has; never add a
role, a page or a sign-in method of your own.

## 1. Two states, two navigation bars

A person is either signed out or signed in, and always sees exactly one navigation bar — the one for their state.

**Signed out — the public navigation.**
- The logo (to the home page), the public pages from the site map in its order, and on the right **Sign in**
  and, only when people may create their own account, **Sign up** as the primary button.
- Nothing that needs an account: no dashboard link, no account menu, no notifications, no "My …" link, no item
  that belongs to a role.

**Signed in — the navigation of the person's role.**
- The logo (to the role's own dashboard, not the public home), the role's own destinations in the site map's
  order with the current one marked, and what the role uses everywhere (search, notifications, a cart — only
  where the product has them).
- The **account menu** on the right: the person's name and role, their initials or photo, profile and settings
  when those pages exist, and **Sign out**.
- No Sign in or Sign up anywhere, and no item of another role. Two roles that share a page each see it in their
  own navigation, with only what that role may do on it.

A public page that a signed-in person can also open (home, a catalogue, pricing) shows the signed-in navigation
while they are signed in, and its calls to action change with it: "Create account" becomes "Go to my
dashboard", "Sign in to book" becomes "Book". On a phone the navigation collapses into a menu button, and the
account menu and Sign out stay inside it.

## 2. Every role has its own home

- Every role that signs in has its own landing page — its dashboard — and signing in opens it. Roles never share
  one generic landing page, and nobody lands on the public home page after signing in.
- A dashboard is the role's working start: a greeting with the person's name, the few figures that matter to that
  role, what is waiting on them with the action beside each item, recent activity, and shortcuts to the role's
  main tasks — all of it this role's own data.
- Where a role may only see its own records (its own orders, bookings, messages, profile), every list, detail,
  count and search shows only those. A role that oversees others (an administrator, a manager) sees across them,
  with filters.

## 3. Sign in, sign up and reset

Tight, calm and complete. These pages use a minimal frame — the logo and a way back home — not the full
navigation.

**Sign in**
- Email (`type="email"`, `autocomplete="username"`), password (`type="password"`,
  `autocomplete="current-password"`) with a show/hide toggle, a primary "Sign in" button, "Forgot password?" when
  the product has a reset page, and "No account? Sign up" only when people may create their own account.
- One generic message for a wrong email or password — "That email and password don't match" — never which one was
  wrong and never whether the email has an account. Too many attempts: "Too many attempts. Try again in a few
  minutes."
- While it signs in, the button shows progress and cannot be pressed twice.
- Someone already signed in who opens it goes straight to their dashboard.

**Sign up** — only when app.md lets people create their own account.
- Only the fields app.md lists for registration, at least name, email and password
  (`autocomplete="new-password"`). The rule is shown before they type (at least 8 characters, long passphrases
  welcome) and checked as they type; each error sits under its own field. Terms consent only when the product
  has terms.
- The new account gets the role app.md gives sign-ups. A person never picks a privileged role (an administrator,
  staff) for themselves; those accounts are created by whoever app.md says provisions them.
- "Already have an account? Sign in". After sign-up: straight into the new account's dashboard, or a "check your
  email" screen when the product verifies email first. Someone already signed in who opens it goes to their
  dashboard.

**Forgot and reset password** — when the product has them. Asking for a link always answers "If that email has
an account, we've sent a link", the same words whether or not it does. The link works once and expires; the new
password follows the sign-up rule; afterwards the person signs in.

## 4. The flows

- A signed-in page opened while signed out → the sign-in page, then straight back to that page after signing in.
- A page the role may not open → their own dashboard with a short "You don't have access to that page", or a
  proper "no access" page with a way back — never a blank or broken screen, never another role's data.
- Signing in → the page they were on their way to, otherwise their role's dashboard.
- Signing out → the session ends, then the public home (or the sign-in page) with the public navigation. Back
  does not show a signed-in page's data again.
- A session that ran out → the next action leads to sign-in with "Your session ended. Sign in again.", then back
  to where they were.
- Every step is a click away. No dead ends, no page without a way forward or back.

## 5. In the wireframes

Plan and draw the public navigation and one signed-in navigation per role (section 1) as the shells of the
shared layout. Every public page uses the public shell; every signed-in page uses its role's shell. Draw the
sign-in, sign-up and reset pages with everything in section 3, their error states included, and each role's
dashboard as section 2 describes, with that role's own content.

## 6. In the prototype

The prototype has no guards — every page opens directly — but it shows both states, from the demo session that
`assets/flow.js` keeps:

- `data-auth="in"` on anything only a signed-in person sees (the signed-in navigation, the account menu, "Go to my
  dashboard"); `data-auth="out"` on anything only a signed-out person sees (Sign in, Sign up, "Create account").
  flow.js shows and hides them by the session.
- A public page carries both headers — the public one with `data-auth="out"` and the signed-in one with
  `data-auth="in"` — so it shows the right one. A signed-in page carries only its role's navigation.
- `data-roles="role_key"` on items only some roles see, `data-user="name"` (or `email`, `role`) where the person's
  details show, `data-sign-out` on Sign out.
- Each role's dashboard is drawn as that role's real home, with its own sample data.

## 7. In the real application

**Sessions and access**
- The session lives in a cookie the server sets: `HttpOnly`, `Secure` in production, `SameSite=Lax`, `Path=/`,
  with an expiry and a refresh. Never keep a token or a role in `localStorage`, `sessionStorage` or a cookie the
  page can read, and never trust a role or user id sent by the browser.
- The role comes from the server's own record of the user (a profile row, a user document), read on the server.
- Access is enforced on the server at every door: the middleware or proxy (signed out → sign-in with the return
  path; wrong role → their dashboard), every page's server-side load, every API route and server action (401 when
  signed out, 403 for a role that may not), and the data itself (Row Level Security, or every query scoped to the
  signed-in user). Hiding a link is presentation, never protection.
- The return path after sign-in is accepted only as a path of this application: it starts with one `/`, never
  `//` and never a full address.

**Sign-in security**
- Passwords go through the stack's auth provider (Supabase Auth) or `bcryptjs` with cost 12 or more — never a
  hand-rolled hash. A password is never logged, never returned, never stored in plain text.
- Sign-in, sign-up and reset requests are rate-limited per IP address and per email, and their answers never
  reveal whether an account exists.
- Signing in starts a new session; signing out ends it on the server and clears the cookie.
- A state-changing request authenticated by a cookie checks its `Origin` (or a CSRF token); framework server
  actions that already do this are enough.
- Every input is validated on the server with a schema; no query is built from raw input.
- Security headers on every response: a Content-Security-Policy, `X-Content-Type-Options: nosniff`, a
  `Referrer-Policy`, `frame-ancestors 'none'`, and HSTS in production.
- Seeded and demo accounts get real hashed passwords from the seed script and are never shown in the interface.

**On each stack**
- Supabase with a server (Next.js, Remix): Supabase Auth with `@supabase/ssr` cookie sessions; decisions use
  `supabase.auth.getUser()` (verified by Supabase) on the server, never `getSession()` alone; roles live in a
  `profiles` table whose RLS policy stops anyone changing their own role, and RLS policies on every table enforce
  them again.
- MongoDB stacks: `bcryptjs` and a `jose`-signed session cookie as above; the cookie holds the user id and the
  role is read from the database on each request.
- A browser-only app with no server (Vite with Supabase): the `@supabase/ssr` browser client keeps the session in
  cookies; nothing can hide them from scripts there, so Row Level Security is the whole boundary and every table
  has its policies.

**Fast and dependable**
- The navigation is rendered on the server from the session, so the right one is there on the first paint: no
  flash of the wrong navigation, and no flash of a protected page before a redirect.
- The session is read once per request and passed down — not fetched again by each component.
- An auth provider that is slow or down gives the sign-in page a clear message and a retry — never a hang or a
  blank page.

**Tests** (Playwright, for every role)
- Each role signs in through the form, lands on its own dashboard and sees its own navigation and account menu.
- Signed in, a reload keeps them signed in, and something they save is still there after the reload — a session
  that is not kept shows up here as being signed out and as saves refused.
- Signed out: a signed-in route goes to sign-in and back after signing in; the public navigation shows Sign in
  (and Sign up when it exists) and no account menu.
- Another role's route is refused (redirect or no-access page), and its API answers 403.
- After sign-out the signed-in route is refused again.
- A wrong password shows the generic message.
