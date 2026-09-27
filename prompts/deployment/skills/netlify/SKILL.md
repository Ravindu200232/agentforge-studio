---
name: netlify
description: Deploy this project to Netlify with the Netlify CLI: site, environment, build, production release, logs, rollback, live proof.
---

# Deploy to Netlify

Netlify builds the application in its own cloud, serves static output from its CDN and runs server
code (server-rendered pages, API routes, middleware) as functions. A site has a stable address,
`<site>.netlify.app`. Everything here uses the `netlify` command line tool the customer signed in to.
Follow `core/SKILL.md` for the rules that apply to every target. `netlify <command> --help` is the
truth for the installed version.

## 1. Identity and account

- `netlify --version`, `netlify status` (who is signed in, which team, whether a site is linked),
  `netlify teams:list` when the account has several. The plan names the team; pass
  `--account-slug <slug>` when creating a site.
- Look for an existing link: `.netlify/state.json`. A linked site is redeployed, never recreated.

## 2. Make the project deployable

- Frameworks are detected. For a server-rendered Next.js application the current Next.js runtime is
  applied automatically by the build; do not vendor an old adapter or hand-write function wrappers.
  The publish directory is the framework's output (`.next` for Next.js); the build command is the
  project's own `build` script. Put them in a `netlify.toml` at the root so the release is
  reproducible and reviewable:

  ```toml
  [build]
    command = "npm run build"
    publish = ".next"
  ```

  Add `[build.environment] NODE_VERSION = "<major from engines>"` when the project pins a version.
- Serverless rules: nothing may be written to the local file system except `/tmp`; a database client
  is created once per function instance and reused; each request must finish within the function
  time limit; server secrets never use the public prefix.
- Add `.netlifyignore`-equivalent hygiene through `.gitignore`: `.agentforge/`, `node_modules/`,
  `.next/`, reports, `.env*`. The CLI uploads the project directory when deploying with `--build`.
- Health: the application answers a cheap route the live check can call; add a minimal one if it has
  none.

## 3. Create or link the site

- New site: `netlify sites:create --name <site-name> --account-slug <slug>` (creates an empty site
  and links this directory). If the name is taken, ask; never invent a different one silently.
- Existing site: `netlify link --name <site-name>` or `--id <site-id>`.
- Never `netlify deploy` without a linked site or `--site`; that would create anonymous deploys.

## 4. Environment

- `netlify env:list` (names only). Missing variables from the `core` section 6 list are added per
  context: production values for the `production` context.
- `netlify env:set` takes the value as an argument, which would put a secret in a visible command.
  For secrets write a temporary dotenv file **outside the project** (in the user's temp folder) from
  the environment variables the studio provides, import it with
  `netlify env:import <that file> --site <site>`, delete the file straight away, then mark each
  secret so it cannot be read back: `netlify env:set <NAME> --secret --context production`.
  A non-secret setting may be set directly with `netlify env:set <NAME> <value> --context production`.
- The database connection string comes from the customer's saved connection (see `core`).

## 5. Build and release

- Local gate first (`core` section 7).
- Release: `netlify deploy --build --prod --site <site-id> --json` (build in Netlify's environment
  with the site's variables, then publish to production). Read the JSON: `deploy_id`, `deploy_url`,
  `url` (the production address), `logs`. Use a draft first (`netlify deploy --build`, no `--prod`)
  when the plan says to smoke-test before promoting; a draft URL is `https://<deploy-id>--<site>.netlify.app`.
- If it fails, read the build log (`netlify deploy` prints it, and the deploy's log URL is in the JSON),
  fix the source, redeploy. `netlify open:site` / `netlify watch` help while a build runs.
- Functions logs after release: `netlify logs:function <name>` (or the site's Logs in the dashboard
  through the URL the CLI prints).

## 6. Access

- The `*.netlify.app` address is public. A custom domain is section 10.
- Site password protection, redirects and header rules go in `netlify.toml` only when the
  specification asks for them.

## 7. Prove it live

Run `core` section 10 against the production address: every route, the health route, a sign-in and a
write/read-back through the real database, a refused request, and the function logs for errors.

## 8. Roll back and remove

- Bad release: restore the previous deploy with
  `netlify api restoreSiteDeploy --data '{"site_id":"<id>","deploy_id":"<previous deploy id>"}'`
  (deploy ids from `netlify api listSiteDeploys --data '{"site_id":"<id>"}'`), then re-check the
  address. The dashboard's "Publish deploy" does the same.
- Deleting a site (`netlify sites:delete`) is destructive: only when the customer asks.

## 9. Record

The studio's live command-line monitors (the Deploy panel's navigation: what this target's own command line tool can show) are built from `run.json`, and a monitor is offered only when the values it needs are recorded. So write exactly these keys, with these names: `host.site_id`, `host.site` (its name), `host.deploy_id`, `host.url`. Record each as soon as you know it.

In `run.json`: site name and id, team, production URL, deploy id, variable names set (never values),
the commit deployed, the checks and their results, and the restore command for this site.

## 10. Domain

Use the customer's own domain when they have one (`core` section 8); `<site>.netlify.app` works meanwhile.

- Set it on the site through the API the CLI wraps: `netlify api updateSite --data
  '{"site_id":"<id>","body":{"custom_domain":"<name>"}}'` (extra names go in `domain_aliases`). The exact
  operation names and their arguments are listed by `netlify api --list`.
- If the customer wants Netlify to answer the domain's DNS, create the zone (`createDnsZone`), then tell them
  the nameservers to set at their registrar; the site's records are created for it. If the DNS is elsewhere,
  the record is a `CNAME` to `<site>.netlify.app` for a subdomain, and the bare name needs the `A` record
  Netlify names for the account: give exactly that once, then poll `Resolve-DnsName <name>`.
- After the name resolves, request the certificate (`provisionSiteTLSCertificate`) and prove it (`core`
  section 8, step 4). Redirect the other form (`www` or bare) with a redirect rule in `netlify.toml`.
- Never register or transfer a domain, or change nameservers, without the customer's word.

## 11. Scaling

Functions scale with traffic by themselves; nothing to size. What limits it is the plan's function
duration (synchronous functions are short; background functions run longer), its monthly build, bandwidth
and function-invocation allowance, and the database's connection limit (reuse one client per function
instance, keep the pool small). To grow: move long work to background functions, place the functions near
the data, and move to the plan whose quota is short (the customer's decision, with the price).

## 12. Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the pages do not already settle (see `core` section 12):

1. Which Netlify team (account slug) should own the site (`netlify teams:list`)?
2. What is the site called? (It becomes `<name>.netlify.app`; ask again if the name is taken.)
3. Which region should the functions run in (near the database)? The site's function region is a
   setting the CLI can change through `netlify api updateSite`.
4. Should the GitHub repository be linked for continuous deployment (every push builds and publishes),
   or should releases be made only with the CLI?
5. Are deploy previews for pull requests and branch deploys wanted, and should previews be password
   protected?
6. Is there a custom domain, and should Netlify manage its DNS or should the customer add records at
   their registrar?
7. Should variables differ between production and previews, and which are secrets?
8. Are forms, identity, scheduled functions or background functions part of the specification and needed?
