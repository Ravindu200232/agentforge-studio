---
name: core
description: The rules every deployment follows, whatever the project, stack or target: the speed contract (no re-testing, one pass, one repair round, a smoke proof), the tools, secrets, the customer's own name, repository, environment and database, domain, scaling, rollback, and how to ask.
---

# Deployment core

Read this page first, then the page for the chosen target and the page for the project's stack. Where
they differ, the target's page wins for that target's own commands; this page wins for everything about
speed, the customer, secrets, names and proof. Nothing here is specific to one application: read the
project to learn what it is, and apply these rules to it.

A deployment is finished when the running application is live at its public HTTPS address and answers the
smoke checks of section 10, not when a command exits 0. The bar is that nothing you know of is left
broken, nothing is a placeholder, every claim in the record was checked by a command or a request you ran,
and the customer can redeploy, roll back and understand it without you. If a part cannot reach that bar, it
is reported as not done, with the reason, never as done.

## 0. The speed contract (it beats any slower instruction on any other page)

A deployment is a delivery, not another test run. The Studio built the application and tested it before
Deploy was offered (`.agentforge/build/report.json`, `.agentforge/qa/report.json`). Delivering it takes
minutes, not hours. Fast does not mean fewer safeguards, only fewer repeats: secrets stay out of every file
and reply, the customer's own name is on everything, the database is reachable, the address is HTTPS, the way
back is recorded and the record is true. Those are kept below; these are the rules that keep the run short:

1. **Do not test again.** Never run unit tests, end-to-end tests, accessibility, performance or security
   audits, lint, type checks, coverage or `npm audit`: not before the upload, not after a repair, not on a
   fresh clone. A failing result in the QA report is a risk to name in the plan, not a reason to run it
   again.
2. **Build once, where it is cheapest.** Vercel, Netlify and AWS ECS build in the provider's cloud: run no
   build on this computer. AWS EC2 and Azure need an artifact made here: reuse the Studio's own build output
   when it exists and is newer than the newest source file (compare timestamps: `.next/standalone`, `dist/`,
   `build/`), otherwise run the production build once. Install dependencies only when that build needs them
   and `node_modules` is missing.
3. **Read only what the deployment needs:** `package.json`, `.env.example`, the framework config, where the
   code reads environment variables, the health route and `sitemap.md`. Not the whole specification, not the
   tests, not every page's source. Never read a file twice.
4. **Decide, do not interview.** Ask at most three questions in total (section 12); every other choice is a
   default, stated in the plan.
5. **One pass.** Do the plan's steps once, in order, with the commands of the target page's *Fast path*.
   Batch them: every environment variable in one loop, every resource in one script. Start the slowest
   provider step first and do the local work while it runs (create the stack, build the artifact meanwhile,
   then wait for the stack). Do not narrate, re-plan or "double-check" what a command's exit code and output
   already showed.
6. **A smoke proof, not a test campaign** (section 10): at most six read-only requests, about two minutes.
7. **One repair round** (`deployment-repair`). A failed check is repaired once: the logs read once, the
   cause named, all related fixes made together, one redeploy, only the failed checks run again. If it still
   fails, stop and report `FAILED` with the cause and the evidence. There is no third attempt and no loop of
   "fix a little, redeploy a little".
8. **A wait has a budget.** DNS, a certificate, a CloudFront distribution, a cluster waking up: wait for the
   budget the target page names (ten to fifteen minutes in all), checking no more often than once a minute.
   When it is over, finish at the provider's own address and list what is left as the one open item, with the
   exact remaining step. A transient platform answer (429, 503, "not ready yet") is waited out for up to a
   minute and the same command is run again; that does not count as a repair.
9. **Reuse.** A project deployed before goes to the same place with the same settings and no new questions
   ("same as last time"); an environment that has not changed is not set again.

Time targets, from the first command to `LIVE`: Vercel, Netlify and GitHub about ten minutes; Azure about
fifteen; AWS EC2 about twenty-five and ECS about thirty-five, most of it the provider creating things. A run
far over its target is looping: stop, find which rule above was broken, and finish.

## 1. Read before anything else

Deploying is planned from what the project really is. Read, in this order, and no more than this:

1. The Studio's own record: `.agentforge/build/report.json` (what was built, the gaps it declared; a declared
   gap is a deployment risk), `.agentforge/qa/report.json` (what was tested; never re-run it),
   `.agentforge/srs/handoff/app.md` and `sitemap.md` (the application's name, roles and routes), and whatever
   a previous run left in `.agentforge/deploy/`.
2. The application's deployment surface: `package.json` (name, author, scripts, engines, framework, package
   manager and lockfile), the framework config, `.env.example`, any `Dockerfile`, `vercel.json`,
   `netlify.toml`, and the file that reads environment variables.
3. What already exists remotely and locally: `git status`, `git remote -v`, `git log --oneline -5`,
   `git config user.name`, and any provider link file (`.vercel/`, `.netlify/`). A project that was deployed
   before is redeployed to the same place, never duplicated.

## 2. Prove the tools before you rely on them

Every provider is used through its own command line tool, signed in by the customer. Before the first
provider command, in one call, confirm from this machine and record what you saw: the tool is installed
(`<tool> --version`), it is signed in and as whom (the tool's own whoami or status command), and the account
has the permission the plan needs (scopes, role, region, quota) when the tool can say.

If the tool is missing or not signed in, that is not something to route around. Stop and ask (see section
12): say which tool, and what the customer does (install it, sign in from Settings -> Integrations) and that
you will continue when they say so. Never sign in for them, never create an account or an access key, never
look for a token in files.

## 3. Secrets and safety

- A credential, token, key or connection string never appears in a file you write, a commit, a log, a
  README, a command you show, or your reply. Refer to variables by name. Values reach a provider from the
  environment or on standard input, never as a visible command argument. Your commands already have the
  project's own Supabase project (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`), the MongoDB
  connection (`MONGODB_URI`) when the stack uses one, and every value the customer gave through a question,
  each under its own name. Test that a variable is set without printing it (`if ($env:NAME) { ... }`).
- A value only the customer has is asked for with a question that carries `variable` (its exact NAME) and
  `secret`: the studio shows a private box, stores it outside the conversation and tells you it is saved; you
  never see it. It is never asked for in words, and a chat message that carries a secret is refused. A secret
  that was pasted somewhere it should not have been is exposed: tell the customer to change it at its source.
- `.agentforge/` (the studio's record), `.env*` files (except the example), keys, `node_modules`, build output,
  test reports and local databases are never committed or uploaded: they are in `.gitignore` and the host's
  ignore file.
- Never force-push, rewrite history, delete a remote branch, delete or change anything this run did not create,
  widen a permission to make a command pass, or turn off a protection (deployment protection, branch
  protection, a firewall rule) without the customer saying so. Never run a seed or reset script against a
  production database.
- Docker is not available on this computer: anything that needs a container image is built by the provider's
  cloud build, never locally.

## 4. Whose name is on it

Everything published carries the customer's name, not the tool's.

- **The owner** of the repository and of the host project is the account the customer's tools are signed
  in to. Ask which only when the account reaches more than one (one of the three questions).
- **The author of every commit** is the customer: `git config user.name` and `user.email` when set;
  when unset, the signed-in GitHub account's display name and its own noreply address
  (`<id>+<login>@users.noreply.github.com`), set for this repository only; when that is not known
  either, ask. Never invent an identity, and never put AgentForge, the studio, an agent or an AI model
  as author, committer or co-author, in a commit trailer, in `package.json` (`author`), in a licence or in
  the README, unless the customer asks for it. If `package.json` carries a placeholder name or author, fix
  it from the specification.
- **The application's name** in the README, the repository description and the host project is the
  name the specification gives it; the repository and host names are short, lowercase and hyphenated
  from it. If a name is taken, ask; never silently add a suffix.

## 5. The repository, its README and its commits

Unless the customer chose otherwise, a deployment leaves the project in a private GitHub repository, so the
code is owned, reviewable and rebuildable by someone else. This is quick work, not a writing project.

- **Files.** A `.gitignore` for the stack (plus `.agentforge/`, `.env*` except `.env.example`, build output,
  test reports); `.env.example` naming every variable with a comment saying what it is and no value. No
  licence unless asked.
- **README.** Written once, short (about forty lines), from what the run already read: what the application
  is and who it is for, the stack, how to run it locally (the scripts in `package.json`), a table of
  environment variable names (never a value), how it is deployed and the live address, and the known
  limitations from the build report's gaps. Do not run commands to write it. An existing README that is
  not the template's placeholder is kept.
- **Commits.** Two or three Conventional Commits, not one dump and not twenty: for example
  `feat: <application name>`, `chore: deployment configuration`, `docs: README`. A short imperative subject.
  Before each, look at `git diff --cached --stat` and search the staged files once for secrets (connection
  strings with passwords, private keys, token patterns). Never `--no-verify`.
- **Push.** Default branch `main`, no force. If the token lacks a permission the push needs, that is a
  question for the customer, not a reason to drop the file silently.
- **CI** only when the customer asked for it and the token allows it: one workflow that installs from the
  lockfile and builds, with no secrets in it. Push it and move on: do not wait for its run, and do not add
  tests to it. A workflow the scaffold already carries is left as it is.

## 6. Environment and database

- Build the list of variables the deployed application needs from `.env.example` and the code
  (`process.env`, `import.meta.env`). Classify each: public (shipped to the browser), server secret, or plain
  configuration. Only variables meant for the browser may carry the framework's public prefix.
- Generate secrets the application needs (session or signing keys) with a cryptographic random source
  on the machine and hand them straight to the provider; keep them out of files and replies. On a
  redeploy, keep the existing values; rotating a session key signs everyone out.
- The production database is the one the build ran on, reachable from the host over the internet: the
  project's own Supabase project, or the MongoDB database the Studio hands to your commands as `MONGODB_URI`
  (the stack page says which). Both were seeded by the build, so the application's accounts and data already
  exist: do not ask how the first administrator is created and do not seed again. Never ask the customer for
  a database address or connection string. A connection string that points at this computer (`localhost`,
  `127.0.0.1`) is never a production value; if there is none reachable, that is a stop with a reason, not a
  question about the string.
- Run only what the application needs to start clean (indexes, migrations), through its own idempotent
  scripts, and only if the build did not already.

## 7. Build (and no gate)

There is no test gate (section 0, rules 1 and 2). The only commands run before the release are the ones the
target's *Fast path* lists: for a cloud-built target nothing at all, for EC2 and Azure the production build
once, reusing the Studio's output when it is current. A build that fails is repaired in the code (see the
repair page); it is never bypassed and never uploaded anyway.

## 8. The domain

Only when the customer has a domain they want it served on (the default is none: the provider's own address is
free, HTTPS and immediate). Then connect it as far as the tools go, so the customer's part is at most one DNS
change: take the exact main name and which form (`www` or bare) redirects to it; find where its DNS is answered
(`Resolve-DnsName -Type NS <domain>`); where your signed-in tools can manage that DNS, create exactly the
records the host asks for and the certificate's validation records, otherwise add the domain to the host and give
the customer the exact records (type, name, value) in one message; wait for the certificate within the budget of
section 0, rule 8, and prove it (HTTPS with a certificate valid for that name, serving the application); record
`domain`, where its DNS is, the records and the certificate state in `run.json`, and use the domain as `url` once
it passes, keeping the provider address as a fallback.

Never buy a domain, transfer one, change nameservers or edit a record this run did not create without the
customer's word. If it cannot be finished inside the budget, the deployment is reported live at the provider
address with the domain as the one open step and exactly what is left.

## 9. Scaling and capacity

Size for the traffic the specification implies (a handful of users unless it says more), at the target's
smallest size that fits, free tier where one exists. Say in the plan, in a sentence each: what the size
handles, what scales by itself, the limit that bites first (function time limits, database connection limits,
instance memory, free-plan quotas), and the one command that scales up later. Never scale up on a failure,
and never past the size or cost chosen without asking.

## 10. The smoke proof

After the release command finishes, the deployment is checked from this computer against the public HTTPS
address (and the domain, when there is one) with **at most six read-only requests, about two minutes**, and
each is recorded in `run.json` `checks` and `evidence` with the URL, the status you expected and what you saw:

1. the home page: the expected status over TLS with a valid certificate, and content that is the
   application (not a platform default or error page);
2. the health route (the application's own, or the minimal one the plan adds);
3. one public route per area of `sitemap.md` that is not the home page (two at most);
4. one protected route requested anonymously: it refuses the way the specification says (redirect to
   sign-in, 401 or 403), never a server error;
5. one read from the database through the running application (an API route or a server-rendered page that
   lists real data): it proves the production database is reachable and holds the build's data.

No browser journeys, no sign-in, no write, no test data in production, no log reading unless a request fails.
The studio calls every URL in `checks` again by itself when you finish; make sure each is cheap and stable.
A request that fails is repaired once (`deployment-repair`); the run is `LIVE` only when all hold.

## 11. Rollback and cost

Know the way back before you release: how to return to the previous good release with this target's tools,
one command, recorded in `run.json`. If the release fails after traffic moved, roll back first, then
diagnose. State what the deployment costs while it runs and how it is removed; never remove anything without
being asked.

## 12. How to ask

The customer decides what only they can. There is no form, and there is no interview: **ask at most three
questions in total** (a private box for a secret value is not counted), one at a time, the most important
first, each with two to four concrete options and your recommendation first, saying in one sentence what the
answer changes. "You decide" is always a valid answer and turns your recommendation into an assumption. The
questions that may be worth asking, only when the project, the machine facts, an earlier deployment record and
an earlier answer do not already settle them:

1. Which account, team, organization or subscription, when the signed-in tool reaches more than one.
2. A choice that costs money on AWS or Azure (instance or plan size, one or two instances), with the price.
3. A value only the customer has that the specification needs (asked through the private box) or a domain the
   customer mentioned.

Every other choice is a default, stated in the plan under assumptions, and the customer changes it by asking:
names from the specification (short, lowercase, hyphenated); the signed-in account as owner and as the name on
the commits; a private repository; a short README; no CI workflow; the region nearest the database, else the
target's usual one; production only, with no previews or branch deploys; the smallest size that fits; no custom
domain; no budget alarm; the database the build ran on; the repository is not connected for continuous
deployment. The pages' own lists of questions are menus to take defaults from, never questions to ask in full.
Never ask what you can read or check, and never ask twice. A redeploy asks nothing a previous run recorded and
the customer has not changed: it says "same as last time" in the plan and reuses it.

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
