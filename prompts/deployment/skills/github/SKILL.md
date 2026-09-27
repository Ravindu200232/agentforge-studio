---
name: github
description: Publish this project to GitHub with the GitHub CLI: repository, README, meaningful commits, CI, optional Pages, verified by cloning and building it fresh.
---

# Publish to GitHub

Delivery to GitHub means the project becomes a repository other people can read, clone, build, review
and continue from, with its history and its documentation. It is also the first step of every other
target, so `core/SKILL.md` section 5 (repository, README, commits) is the standard here. Everything is
done with `git` and the `gh` command line tool the customer signed in to. `gh <command> --help` is the
truth for the installed version.

## 1. Identity and permission

- `gh --version`, `gh auth status`: the account, and the token's scopes. Pushing workflow files needs
  the `workflow` scope, and creating a repository needs `repo`. If a scope the plan needs is missing,
  stop and ask the customer to add the permission from Settings -> Integrations (an "Add the
  permission" button opens the browser); never work around it by dropping the workflow silently.
- Owner: the signed-in account unless the customer chose an organization (`gh repo create <org>/<name>`).
- `git config user.name` / `user.email`; when unset, use the account's own noreply address
  (`<id>+<login>@users.noreply.github.com`) for this repository only.

## 2. Prepare the working tree

- `git status` first. If a repository already exists here, keep its history and remote; do not
  re-initialize. Otherwise `git init -b main`.
- Files per `core` section 5: `.gitignore` (including `.agentforge/` and every `.env*` except the
  example), `.env.example`, `README.md` written from the specification and the real code, a `docs/`
  folder only if the customer wants the specification published.
- Look for secrets before staging anything: search the tree for connection strings with passwords,
  private keys, access-key patterns and tokens, and check `git ls-files` afterwards for `.env`,
  `node_modules`, build output and reports. A hit is fixed (moved to the environment, file ignored)
  and reported; a secret that was ever committed is rotated by the customer, not hidden by rewriting
  history.

## 3. Create the repository

- Name and visibility from the plan. `gh repo view <owner>/<name>` first: if it exists and is not
  this project's, ask.
- `gh repo create <owner>/<name> --private|--public --description "<one line from the
  specification>" --source . --remote origin` (without `--push` when the commits are not made yet).
- Topics that describe the stack: `gh repo edit --add-topic <topic>`.

## 4. Commits and push

Make the history described in `core` section 5: several Conventional Commits in a sensible order, each
one building. Look at `git diff --cached --stat` and the file list before every commit. Then
`git push -u origin main` (no force, ever). If the push is rejected, read why (permission, protected
branch, large file over 100 MB, secret scanning) and fix the cause.

## 5. CI (when the plan includes it)

`.github/workflows/ci.yml`: trigger on push and pull request to `main`; `actions/checkout`,
`actions/setup-node` with the Node version from `engines` and dependency caching, `npm ci`, the
project's test command, the production build with placeholder environment values that are not
secrets; least-privilege `permissions: contents: read`; pin third-party actions to a major version or
commit. No deployment credentials in it. After the push, follow the run: `gh run list --limit 3`,
`gh run watch <id>`, and on failure `gh run view <id> --log-failed`: fix the cause and push again
until the run is green. A red workflow is a defect of the delivery.

## 6. Optional: Pages and releases

- GitHub Pages hosts static output only. Use it only when the application is static (or has a static
  export that the specification accepts), through a workflow using the official Pages actions;
  enable with `gh api -X POST repos/<owner>/<name>/pages -f build_type=workflow`. A server-rendered
  application with a database is not a Pages application: say so and do not fake it.
- `gh release create v<version> --generate-notes` when the customer wants a tagged release.
- Branch protection, required reviews and Dependabot configuration (`.github/dependabot.yml`) are
  suggestions in the plan, applied only when the customer agrees.

## 7. Prove it

- `gh repo view <owner>/<name> --json url,visibility,defaultBranchRef,pushedAt`; the remote `main`
  commit equals the local one (`git ls-remote origin main` against `git rev-parse HEAD`).
- The latest workflow run for that commit succeeded.
- A fresh clone builds: clone into a temporary folder outside the project, `npm ci`, run the tests
  and the production build there. This proves nothing needed is missing from the repository. Delete
  the temporary clone afterwards.
- The README renders (headings, tables, code fences) and every command in it was run or is marked
  untested; the repository contains no `.agentforge`, no `.env`, no secret.

## 8. Roll back and remove

- A bad commit is reverted with a new commit (`git revert`); history is never rewritten and the
  default branch is never force-pushed.
- Changing visibility or deleting a repository is destructive and only when the customer asks.

## 9. Record

The studio's live command-line monitors (the Deploy panel's navigation: what this target's own command line tool can show) are built from `run.json`, and a monitor is offered only when the values it needs are recorded. So write exactly these keys, with these names: `repository.url` (the address of the repository), `repository.visibility`, `repository.default_branch`. Record each as soon as you know it.

In `run.json`: the repository URL (that is the `url` for this target unless Pages is enabled), owner,
visibility, default branch, the commit list (hash and subject), the workflow run id and result, the
Pages address if any, the checks and results, and the revert instruction.

## 10. Domain

A repository is not served on a domain. Only when the customer chose GitHub Pages for a static site (see
above) can it have one: `gh api -X PUT repos/<owner>/<repo>/pages -f cname=<name>`, a `CNAME` record at the
customer's DNS to `<owner>.github.io` (or the four `A` records GitHub documents for the bare name), and
HTTPS enforced once the certificate is issued (`-F https_enforced=true`). Give the records to the customer
once and poll `Resolve-DnsName`. Otherwise, say that a domain belongs to the target that serves the
application.

## 11. Scaling

A repository does not scale. If the customer uses Actions minutes or storage heavily, say what the
account's plan allows.

## 12. Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the pages do not already settle (see `core` section 12):

1. Which owner: the signed-in account or an organization it belongs to?
2. What is the repository called, and is it private or public?
3. What is its one-line description, and which topics should it have?
4. Which licence, if any?
5. Should a CI workflow be added (needs the `workflow` permission on the token), and should it run the
   tests only or also the production build?
6. Should the default branch be protected (pull request and passing checks required)? It is applied only
   when the customer agrees, and it changes how later pushes work.
7. Should Dependabot version and security updates be turned on?
8. Should a first tagged release be created?
9. Should the specification and the design records be published in `docs/`, or kept out of the
   repository?
