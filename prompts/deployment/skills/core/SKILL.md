---
name: core
description: The rules every deployment follows, whatever the project, stack or target: read first, prove the tools, the customer's own name on the repository, README, environment and database, domain, scaling, verification, evidence, rollback, and how to ask.
---

# Deployment core

Read this page first, then the page for the chosen target and the page for the project's stack. Where
they differ, the target's page wins for that target's own commands; this page wins for everything about
the customer, secrets, names and proof. Nothing here is specific to one application: read the project to
learn what it is, and apply these rules to it.

A deployment is finished when the running application at its public HTTPS address has been used and
behaves the way the specification says, not when a command exits 0. The bar is that nothing you know of
is left broken, nothing is a placeholder, every claim in the record was checked by a command or a
request you ran, and the customer can redeploy, roll back and understand it without you. If a part
cannot reach that bar, it is reported as not done, with the reason, never as done.

## 1. Read before anything else

Deploying is planned from what the project really is. Read, in this order:

1. The specification handoff in `.agentforge/srs/handoff/` (`app.md`, `builder.md`, `sitemap.md`):
   what the application is called and does, its roles, pages and routes, its data and the environment
   it needs.
2. The build record `.agentforge/build/report.json` and the test records under `.agentforge/qa/`: what
   was built, which commands passed, which gaps were declared. A declared gap is a deployment risk.
3. The application itself: `package.json` (name, author, scripts, engines, framework, package manager
   and lockfile), the framework config, `.env.example`, `README.md`, any `Dockerfile`, `vercel.json`,
   `netlify.toml`, workflow files, and whatever a previous run left in `.agentforge/deploy/`.
4. What already exists remotely and locally: `git status`, `git remote -v`, `git log --oneline -10`,
   `git config user.name`, and any provider link file (`.vercel/`, `.netlify/`). A project that was
   deployed before is redeployed to the same place, never duplicated.

## 2. Prove the tools before you rely on them

Every provider is used through its own command line tool, signed in by the customer. Before the first
provider command, confirm from this machine, and record what you saw:

- the tool is installed (`<tool> --version`);
- it is signed in, and as whom (the tool's own whoami/status command);
- the account has the permission the plan needs (scopes, role, region, quota) when the tool can say.

If the tool is missing or not signed in, that is not something to route around. Stop and ask (see
section 12): say which tool, and what the customer does (install it, sign in from Settings ->
Integrations) and that you will continue when they say so. Never sign in for them, never create an
account or an access key, never look for a token in files.

## 3. Secrets and safety

- A credential, token, key or connection string never appears in a file you write, a commit, a log, a
  README, a command you show, or your reply. Refer to variables by name.
- Values reach a provider from the environment or on standard input, never as a visible command
  argument. Your commands run with the project's own Supabase project already in the environment
  (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` - the machine facts say which
  project), and every other value the customer gave when a question asked for it, by its own name.
  Test that a variable is set without printing it (`if ($env:NAME) { ... }`).
- A value only the customer has (an administrator's first email and password, a mail key, a
  third-party token, or a different production Supabase project's values) is asked for with a
  question that carries `variable` (its exact NAME, for example `ADMIN_PASSWORD`) and `secret`. The
  studio shows a private box on that question, stores it outside the conversation and tells you it is
  saved; you never see it. It is never asked for in words, and a chat message that carries a secret is
  refused. A secret that was pasted somewhere it should not have been is treated as exposed: tell the
  customer to change it at its source.
- The `.agentforge` folder is the studio's own record (conversation, logs, plans). It is never
  published to a repository or a host: it is in `.gitignore` and in the host's ignore file. If the
  customer wants the specification in the repository, copy the reviewed documents into `docs/`.
- `.env`, `.env.local`, keys, `node_modules`, build output, test reports and local databases are never
  committed or uploaded.
- Never force-push, never rewrite history, never delete a remote branch, never delete or change
  anything this run did not create, never widen a permission to make a command pass, never turn off a
  protection (deployment protection, branch protection, a firewall rule) without the customer saying so.
- Never run destructive development seeds or reset scripts against a production database. Production
  data starts empty or deliberately seeded, and only as the customer chose.
- Docker is not available on this computer. Anything that needs a container image is built by the
  provider's cloud build (CI runner or the provider's own build service), never locally.

## 4. Whose name is on it

Everything published carries the customer's name, not the tool's.

- **The owner** of the repository and of the host project is the account the customer's tools are signed
  in to (or an organization or team they choose). Ask which when the account reaches more than one.
- **The author of every commit** is the customer: `git config user.name` and `user.email` when set;
  when unset, the signed-in GitHub account's display name and its own noreply address
  (`<id>+<login>@users.noreply.github.com`), set for this repository only; when that is not known
  either, ask. Never invent an identity, and never put AgentForge, the studio, an agent or an AI model
  as author, committer or co-author, in a commit trailer, in `package.json` (`author`), in a licence or in
  the README, unless the customer asks for it. If `package.json` carries a placeholder name or author, fix
  it from the specification and the customer's answer.
- **The application's name** in the README, the repository description and the host project is the
  name the specification gives it; the repository and host names are short, lowercase and hyphenated
  from it unless the customer chose others. If a name is taken, ask; never silently add a suffix.

## 5. The repository, its README and its commits

Unless the customer chose otherwise, a deployment leaves the project in a GitHub repository, so the
code is owned, reviewable and rebuildable by someone else.

- **Files.** A `.gitignore` for the stack (plus `.agentforge/`, `.env*` except `.env.example`, build
  output, test reports); `.env.example` naming every variable with a comment saying what it is and no
  value; a licence only if the customer asked.
- **README: ask whether it is wanted** (recommend yes), and when one already exists whether to keep it,
  improve it or replace it. When wanted it is written for a stranger who has only the repository, from
  the specification and the actual code, not from memory: what the application is and who it is for;
  the features, by role; the stack; the folder layout in a few lines; prerequisites; local setup and the
  exact commands; a table of environment variables (name, purpose, required, where it is set; never a
  value); how to run the tests; how it is deployed and how to redeploy; the live address; and known
  limitations taken from the build report's gaps. Every command in it was run, or is marked untested.
  Demo accounts appear only if the specification defines them as fictitious and the customer chose to
  seed them. When it is not wanted, none is written and nothing else changes.
- **Commits.** Real history, not one dump. Conventional Commit messages (`feat:`, `fix:`, `docs:`,
  `ci:`, `chore:`, `build:`), a short imperative subject and a body when the why is not obvious. Split
  by concern in a sensible order: project scaffold, the application by area, tests, documentation,
  CI and deployment configuration. Each commit builds. Never `--no-verify`. Before every commit, look
  at what is staged and check that no secret is in it.
- **Push.** Default branch `main`, no force. If the token lacks a permission the push needs (for
  example to add a workflow file), that is a question for the customer, not a reason to drop the file
  silently.
- **CI.** When the customer wants it and the token allows it: one workflow that installs from the
  lockfile, runs the tests and the production build on every push and pull request, with no secrets in
  it, and it passes. Do not make the workflow the thing that deploys unless the plan says so. The
  scaffold's own `.github/workflows/quality.yml`, when present, already reads what it needs as
  repository secrets (`${{ secrets.NAME }}`) rather than embedding them - read that file for the exact
  names it expects and set each one as a real repository secret (`gh secret set NAME --repo owner/repo`,
  the value piped in or read from a file, never typed where it would be echoed or logged) from the same
  values already connected for this deployment, before or immediately after the push that first adds the
  workflow. That push runs it automatically: check its result (`gh run list --workflow=quality.yml
  --limit 1`, then `gh run view <id> --log-failed` on a failure) the same way every other check on this
  page is treated - a failing run is a real defect to repair from its log, not something to leave red and
  call the deployment done.

## 6. Environment and database

- Build the list of variables the deployed application needs from `.env.example`, the code
  (`process.env`, `import.meta.env`) and the specification. Classify each: public (shipped to the
  browser), server secret, or plain configuration. Only variables meant for the browser may carry the
  framework's public prefix.
- Generate secrets the application needs (session or signing keys) with a cryptographic random source
  on the machine and hand them straight to the provider; keep them out of files and replies. On a
  redeploy, keep the existing values; rotating a session key signs everyone out.
- A production database is required to be reachable from the host over the internet, with
  authentication and TLS. A connection string that points at this computer (`localhost`, `127.0.0.1`)
  is never a production value. If no reachable database is saved, ask for it (section 12); do not
  deploy an application that cannot reach its data and call it finished. Give the database its own name
  for this application, and say when the string names none.
- If the specification gives users no way to create the first account, an empty database is unusable:
  ask how the first administrator is created and carry it out with the application's own idempotent
  means, using values the customer gave through a question. The administrator's email and name are the
  customer's own: ask for each, one question each, and never make up an address or a domain. Never leave
  the customer with a credential they cannot read: a host's sensitive variables cannot be read back, so
  either they type the password themselves (the private box), or you generate one and hand it over in a
  way you can really do (a file on this computer outside the project, its path told, to be read once and
  changed), or the application forces a change at first sign-in. Say which in the plan.
- Run only what the application needs to start clean: indexes, migrations and required reference data,
  through the application's own idempotent scripts. Say what you ran.

## 7. Build and gate

Before the first upload, on this computer: install from the lockfile, run the tests, and run the
production build with the production environment names present. A failing test or build is fixed in
the code (see the repair page), never bypassed and never uploaded anyway. If tests were declared as
gaps in the build report, say so in the run record.

## 8. The domain

Ask whether the customer has a domain they want it served on (recommend the provider's own address
when they have none: it is free, HTTPS and immediate). When they do, connect it yourself as far as the
tools go, so that the customer's part is at most one DNS change:

1. Ask for the exact name they want as the main address (`app.example.com`, or the bare domain), and
   whether the other form (`www`, or the bare name) should redirect to it.
2. Find out where its DNS is answered (`Resolve-DnsName -Type NS <domain>` or `nslookup -type=NS`): at
   the same provider you deploy to, at a DNS service your signed-in tools can manage (the target's page
   says which), or at a registrar only the customer can change.
3. Where you can manage the DNS, do it with the tools: add the domain to the host, create exactly the
   records it asks for, and the certificate's validation records, and nothing else. Where you cannot,
   add the domain to the host anyway, then tell the customer the exact records (type, name, value) to
   create, one message, and wait; then poll (`Resolve-DnsName`, a few minutes apart) until they resolve.
4. Wait for the certificate to be issued, then prove it: the domain answers over HTTPS with a certificate
   valid for that name, serves the application, and the redirect between forms works.
5. Record it in `run.json` (`domain`: the name, where its DNS is, the records created or asked for, the
   certificate state) and use the domain as `url` once it passes, keeping the provider address as a
   fallback in the evidence.

Never buy a domain, transfer one, change nameservers or edit a record this run did not create without
the customer's word. If the domain cannot be finished (DNS not yet changed), the deployment is still
reported live at the provider address, with the domain listed as the one open step and exactly what is
left.

## 9. Scaling and capacity

Ask what the customer expects (a handful of users, steady business use, a launch with spikes, growth
later) and size for it, not for the largest case. Say in the plan: what the chosen size handles, what
scales by itself on this target and what does not, the limits that will bite first (function time
limits, database connection limits, instance memory, free-plan quotas), and exactly how to scale up
later with this target's tools. Turn on the target's own autoscaling where the customer chose it and it
exists, with a minimum and a maximum they agreed to. Never scale up on a failure, and never past the
size or cost the customer chose without asking. Check that the database tier and its connection limit
suit the scale you promised.

## 10. Prove it live

After the release command finishes, the deployment is checked as a user would use it, from this
computer, against the public HTTPS address (and the domain, when there is one):

- the home page answers with the expected status, over TLS with a valid certificate, and its
  content is the application (not a platform default or error page);
- a health route answers (the application's own, or a minimal one the plan adds);
- every public route in `sitemap.md` answers, and every protected route refuses an anonymous visitor
  the way the specification says (redirect to sign-in or a 401/403), not with a server error;
- the main journey of each role in the specification is exercised through the running application's
  own interface or API (sign in, create the main record, read it back, sign out) using an account the
  customer allowed for this, and the data lands in the production database;
- a request that must be refused is refused (wrong role, bad input);
- the platform's logs for the deployment show no errors during those requests.

Record each check in `run.json` `checks` and `evidence` with the URL, the status and what was seen. A
check that fails is a bug to fix: read the logs, repair the source or configuration, redeploy, and run
every check again from the start. Stop after three repair rounds with the same failure and report it
honestly. Never mark the run LIVE on a partial pass, and remove any test data you created in the
production database that the customer did not ask for.

## 11. Rollback and cost

Know the way back before you release: how to return to the previous good release with this target's
tools, and say it in the plan. If the release fails after traffic moved, roll back first, then
diagnose. State what the deployment costs while it runs and how to remove it; never remove anything
without being asked.

## 12. How to ask

The customer customizes everything about a deployment by answering you: there is no form. Every skill
page (this one, the target's, the stack's) ends with the questions its subject lets the customer decide.
Those lists are what to think about, not a script to read out. For this project and this situation:
collect what applies, drop what the project, the machine facts, an earlier deployment record or an
earlier answer already settle, add what the lists do not cover but this project needs, and write each
question yourself, in plain words, naming the real thing (the application's own roles, pages, data and
the actual account names you measured) instead of a generic template.

Ask like a careful engineer, not an interviewer: one question at a time, the one that matters most
first, with two to four concrete options and your recommendation first, saying in one sentence what the
answer changes. "You decide" is always a valid answer: it turns your recommendation into a stated
assumption in the plan. Never ask what you can read or check, never ask twice. Ask at the moment you
need the answer, in the plan or, when something turns up while carrying it out, then.

What to cover, whenever it applies (each is a decision the customer may make, and none is assumed
silently):

1. Which account, team or organization it goes to, when the signed-in tool can reach more than one.
2. What the application, the repository and the host project are called.
3. Whose name is on the commits and the repository (the signed-in account's, or another name and
   email), and whether the repository is private or public, with or without a licence.
4. Whether a README is wanted, and what to do with one that exists.
5. Which region, given where the database and the users are.
6. Which production database, and what it starts with: empty, the required reference data, or demo data
   (never default to demo accounts on a public address); and how the first administrator is created.
7. Whether there is a domain to connect (section 8).
8. What traffic to expect and how it should scale (section 9), and what it may cost per month.
9. Whether it continues from the repository (a CI workflow, deployment on every push) or is a single
   release.
10. When a previous deployment exists: the same place and settings again, or something different.

A redeploy does not ask again what a previous run recorded and the customer has not changed: it says
"same as last time" in the plan and reuses it.

## 13. Shell

On Windows your commands run in Windows PowerShell 5.1: there is no `&&` or `||` (chain with `;` and
check `$LASTEXITCODE`), environment variables are `$env:NAME`, paths with spaces are quoted, and a native
tool's messages on standard error may be shown as errors: judge a command by its exit code and its
output, not by the colour. On other systems it is a POSIX shell. Commands that would wait for a keypress
or a browser are never used: pass the tool's non-interactive flags. Run long commands in the foreground
with a timeout that fits them and read their whole output.

## 14. The record

Everything you do is written to `.agentforge/deploy/`: `events.jsonl` (one line per stage start and
finish), `run.json` (state, URL, domain, repository, artifacts, checks, evidence, security notes, the
rollback instruction) and, when you cannot continue without the customer, `question.json`. The Deploy
panel and the chat are built from those files, so what they say must be true.
