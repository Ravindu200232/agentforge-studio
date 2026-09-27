---
name: vercel
description: Deploy this project to Vercel with the Vercel CLI: link, environment, build, production release, aliases, logs, rollback, live proof.
---

# Deploy to Vercel

Vercel runs a Next.js (or other framework) application as serverless functions plus a CDN, builds it
in Vercel's own cloud, and gives every deployment a URL and the project a stable production address
(`<project>.vercel.app`). Everything here is done with the `vercel` command line tool the customer
signed in to. Follow `core/SKILL.md` for the rules that apply to every target.

Notes about running the tool from this machine: it prints its progress on standard error, so a
PowerShell host may label lines "NativeCommandError"; the exit code is what counts. Pass
`--non-interactive` (or `--yes` where the command has it) so nothing waits for a keypress.
`vercel --help` and `vercel <command> --help` are the truth for the installed version.

## 1. Identity and scope

- `vercel --version`, then `vercel whoami`. The plan names the account; use the customer's chosen
  scope (personal account or team slug) with `--scope <slug>` on every command that touches the
  project, or `vercel switch <slug>` once. `vercel teams ls` lists what the account can reach.
- Look for an existing link: `.vercel/project.json` (project and org ids). If it exists and names the
  project the customer wants, reuse it: redeploys go to the same project.

## 2. Make the project deployable

Check these in the source before uploading; fix in the code when they are wrong:

- The framework is detected from `package.json`; the install and build commands are the project's
  own scripts. `vercel deploy --dry` shows the detected preset and the file list without deploying.
- Add a `.vercelignore` so the upload is only the application: `.agentforge/`, `node_modules/`,
  `.next/`, `test-results/`, `playwright-report/`, `coverage/`, `.env*` (except the example), local
  databases. Never rely on the upload to skip secrets.
- Node version: match `engines` in `package.json` (the project setting can be changed in the
  dashboard settings; the CLI follows `engines`).
- Serverless rules: no writing to the local file system except `/tmp`; no long-lived background
  process; a database client is created once per function instance and reused (module-level cache),
  because each cold start opens new connections; every route must finish within the function time
  limit. Server-only secrets must not carry the public prefix (`NEXT_PUBLIC_`).
- Region: functions default to a US region. When the database has a known region, choose a nearby one
  with `"regions": ["<id>"]` in `vercel.json` (or `--regions`) so each request is not crossing an
  ocean to reach data. Say which and why in the plan.
- Health: the application answers a cheap route the platform and the live check can call. If it has
  none, the plan adds a minimal one (status only, no data, no secrets).

## 3. Link

- New project: `vercel link --yes --project <name> [--team <slug>]`. This creates the project on the
  account if the name is free, and writes `.vercel/project.json`. Confirm with `vercel projects ls`.
- Existing project: `vercel link --yes --project <name-or-id> --team <slug>`.
- `.vercel/` is never committed.
- Connecting the Git repository (`vercel git connect`) is optional and only with the customer's
  agreement; it needs the Vercel GitHub app on the account. If it is refused, deployment through the
  CLI still works: say so and continue.

## 4. Environment

- `vercel env ls` shows what the project has (names only). Add what is missing, per environment,
  from the list made in `core` section 6:
  `vercel env add <NAME> production --sensitive --force` with the value on standard input (or
  `--value` only for a non-secret setting). Secrets are stored as sensitive so they cannot be read
  back. A value from a variable in the environment is piped in, never typed as an argument: in
  PowerShell `$env:<NAME> | vercel env add <NAME> production --sensitive`, in a POSIX shell
  `printf %s "$<NAME>" | vercel env add <NAME> production --sensitive`. A piped value can carry a
  trailing newline: after adding a secret the application must still work (the live check proves it),
  and if it does not, make the application trim that value rather than storing it wrongly.
- `vercel env pull .env.production.local --environment=production` is only for inspecting names on
  this machine; delete the file afterwards and never commit it.
- Add the variables the application needs for `preview` only when the customer asked for previews.
- The database connection string comes from the customer's saved connection (see `core`). If the
  customer chose a Marketplace database, use `vercel integration --help` and `vercel install --help`
  for what the CLI offers, and say what it will bill.

## 5. Build and release

- Local gate first (`core` section 7): install from the lockfile, tests, production build.
- Release with the remote build: `vercel deploy --prod --yes --logs`. Vercel builds it in the
  customer's project with the production environment, the last line printed is the deployment URL.
  Building remotely avoids local platform differences (Windows paths, native modules). Use
  `vercel build --prod` followed by `vercel deploy --prebuilt --prod` only when the plan needs a
  local build, after `vercel pull --yes --environment=production`.
- `vercel inspect <deployment-url>` shows the state (Ready / Error), the build, the functions and the
  aliases. The production alias `<project>.vercel.app` (and any custom domain) is what the customer
  uses; the per-deployment URL is not the address to hand out.
- If the build fails: `vercel inspect <url> --logs` (or `vercel logs <url>`), fix the cause in the
  source, redeploy. Read the whole error before changing anything.

## 6. Protection

- New deployments may be behind Vercel Authentication. The production alias is normally public; a
  401 with a Vercel sign-in page means protection is on. Never switch protection off yourself: tell
  the customer, and `vercel curl <path>` can be used to test through protection while they decide.
- A custom domain is section 10.

## 7. Prove it live

Run `core` section 10 against `https://<project>.vercel.app` (the alias printed by `vercel inspect`):
status of every route, the health route, a sign-in and one write/read-back round trip, one refused
request, and `vercel logs <deployment-url>` for errors during those calls. Check that a server-side
database call really succeeded (a page that reads data, not only the static shell).

## 8. Roll back and remove

- Bad release: `vercel rollback <previous-deployment-url>` (or `vercel promote <url>`), then confirm
  the alias serves the old build. `vercel ls` lists deployments with their state.
- Removing the project or a deployment (`vercel remove`) is destructive: only when the customer asks.

## 9. Record

The studio's live command-line monitors (the Deploy panel's navigation: what this target's own command line tool can show) are built from `run.json`, and a monitor is offered only when the values it needs are recorded. So write exactly these keys, with these names: `host.project`, `host.deployment_url` (the deployment's own address, not the alias), `host.deployment_id`, `host.scope`, `host.production_aliases`, `host.region`. Record each as soon as you know it.

In `run.json`: the project name, scope, production URL, the deployment URL and id, the environment
variable names set (never values), the `git` repository and commit deployed, the checks and their
results, and the rollback command for this project.

## 10. Domain

Use the customer's own domain when they have one (`core` section 8); the project's `<name>.vercel.app`
address always works meanwhile.

- `vercel domains ls` shows what the account already holds; `vercel domains inspect <name>` says whether it
  is verified and who answers its DNS.
- Add it to the project: `vercel domains add <name> <project>` (or `vercel alias set <deployment-url>
  <name>`). Add both the bare name and `www`, and make the one the customer did not choose redirect to the
  one they did (`vercel.json` redirects or `vercel redirects`).
- If the domain's nameservers are Vercel's, the records are created for it and nothing more is needed. If
  its DNS is elsewhere, Vercel asks for one record (an `A` record to the address it prints for the bare
  name, a `CNAME` to the value it prints for a subdomain): give exactly that to the customer once, then poll
  `Resolve-DnsName <name>` and `vercel domains inspect <name>` until it verifies. The certificate is issued
  by itself after verification: prove it (`core` section 8, step 4).
- Never `vercel domains buy`, `transfer-in` or `rm`, and never change nameservers, without the customer's
  word.

## 11. Scaling

Functions scale with traffic by themselves; there is no instance to size. What limits it is the plan's
function duration and concurrency, the plan's monthly bandwidth and invocation allowance, and the
database's connection limit (every concurrent function instance opens connections: reuse one client per
instance, keep the pool small, and use the database tier's connection limit as the real ceiling). To grow:
raise `maxDuration` on the routes that need it, set `regions` near the data, and move to a plan with the
quota that is short (a decision with a price the customer makes). Say in the plan which of these will
bite first for the traffic the customer described.

## 12. Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the pages do not already settle (see `core` section 12):

1. Which Vercel account or team scope should own the project (`vercel teams ls` shows what the signed-in
   account can reach)?
2. What is the project called? (It becomes `<name>.vercel.app`; ask again if the name is taken.)
3. Is this a commercial project? Vercel's free Hobby plan is for personal, non-commercial use; a
   commercial application belongs on a team plan. State what you know, do not decide it for them.
4. Which region should the functions run in (near the database)?
5. Should the GitHub repository be connected (`vercel git connect`) so every push deploys, or should
   releases be made only with the CLI? (Connecting needs the Vercel GitHub app installed on the account.)
6. Are preview deployments for branches wanted, and should they be protected behind Vercel sign-in?
7. Is there a custom domain, and should the bare domain or `www` be the main one?
8. Should any variables also be set for previews, and should the database be shared between previews and
   production (it should not be, by default)?
9. Are scheduled jobs (Vercel Cron) or a storage add-on (Blob, a marketplace database) wanted?
