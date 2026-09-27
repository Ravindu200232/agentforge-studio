---
name: azure
description: Deploy this project to Azure App Service (Linux) with the Azure CLI: resource group, plan, web app, settings, zip release, logs, slots, live proof.
---

# Deploy to Azure App Service

A Linux App Service web app runs the built Node.js application on a managed plan, with an HTTPS
address `https://<app>.azurewebsites.net` and a certificate included. Everything here is done with the
`az` command line tool the customer signed in to (`az login`). Follow `core/SKILL.md` for the rules
that apply to every target. `az <group> <command> --help` is the truth for the installed version, and
`az webapp list-runtimes --os linux` lists the runtime strings it accepts.

## 1. Identity and subscription

- `az --version`, `az account show` (subscription id and name, tenant, signed-in user). The plan
  names the subscription; select it with `az account set --subscription <id>` and use `--subscription`
  on commands when more than one exists. Do not create a service principal or a secret.
- Names: the web app name is global (`<app>.azurewebsites.net`), lowercase letters, digits and hyphens.
  Check it is free (`az webapp list --query "[?name=='<name>']"` only covers this subscription; a
  creation error tells you the name is taken). If it is taken, ask; do not append a suffix silently.

## 2. Resources (all tagged `app`, `env`, `managed-by`)

1. Resource group: `az group create --name <rg> --location <region> --tags ...`. A region close to the
   database and the users; the customer chooses.
2. Plan: `az appservice plan create --name <plan> --resource-group <rg> --is-linux --sku <sku>`. The
   customer chooses the size; do not raise it on a failure. `F1` is free but has no Always On and tight
   quotas; `B1` is the smallest that is comfortable for a small production application; slots need `S1`
   or above. State the monthly price in the plan.
3. Web app: `az webapp create --resource-group <rg> --plan <plan> --name <app> --runtime "<runtime from
   list-runtimes matching the project's Node version>"`.
4. Hardening on the app: `az webapp update --https-only true`, `az webapp config set --min-tls-version
   1.2 --ftps-state Disabled --always-on true` (Always On needs `B1` or above),
   `az webapp identity assign` when the application will read from Key Vault.

Reuse what exists on a redeploy (`az webapp show`), never a second group, plan or app.

## 3. Application settings and start command

- Settings from the `core` section 6 list: `az webapp config appsettings set --resource-group <rg>
  --name <app> --settings @<file>` where the file is a JSON array of `{"name","value","slotSetting"}`
  written **outside the project** from the environment variables the studio provides, deleted straight
  after. Never pass a secret as a visible `--settings KEY=value` argument. Add `WEBSITE_RUN_FROM_PACKAGE`
  only when the plan chooses it, and `SCM_DO_BUILD_DURING_DEPLOYMENT=false` when shipping build output.
  Bind the port the platform gives: the application must listen on `process.env.PORT` (App Service sets
  it) and `0.0.0.0`.
- Start command: `az webapp config set --resource-group <rg> --name <app> --startup-file "<the
  project's real production start command>"`. For a Next.js standalone build that is `node server.js`
  from the folder that holds it.
- Health check path: configure it with the flag your `az webapp config set --help` shows (or generic
  configuration `healthCheckPath`), pointing at the cheap health route; add a minimal route if none exists.
- Key Vault: only when the customer chose it; secrets are referenced with `@Microsoft.KeyVault(...)` and
  the app's managed identity gets `get` on secrets only.

## 4. Build and release

- Local gate first (`core` section 7). Build on this machine, then package what runs: for Next.js the
  standalone output with `.next/static` and `public` copied beside `server.js`, plus the production
  `package.json` when the runtime installs dependencies; zip with the files at the root of the archive,
  excluding `.agentforge`, tests, `.env*` and development dependencies.
- Release: `az webapp deploy --resource-group <rg> --name <app> --src-path <zip> --type zip`. It waits
  for the deployment to finish and prints the status. Native modules must be built for Linux: build on
  the runtime (`SCM_DO_BUILD_DURING_DEPLOYMENT=true` with the lockfile) when the project has any.
- If it fails or the site shows the default page or 5xx: `az webapp log config --resource-group <rg>
  --name <app> --application-logging filesystem --level information`, then `az webapp log tail
  --resource-group <rg> --name <app>` (and `az webapp log download`) while requesting the site; read
  the startup error, fix the source or the setting, release again. Confirm the start command, `PORT`,
  the Node version and the file layout of the zip before changing anything else.

## 5. Slots and rollback

- With `S1` or above, release to a `staging` slot (`az webapp deployment slot create`, deploy with
  `--slot staging`), run the live checks there, then `az webapp deployment slot swap --slot staging
  --target-slot production`. Swapping back is the rollback. Say in the plan whether slots are used.
- On `B1` there are no slots: keep the previous zip as an artifact and roll back by deploying it again
  (`az webapp deploy` with the earlier package). Say so.
- Deleting the group (`az group delete`) is destructive and only when the customer asks.

## 6. Database access

A hosted database usually allows only listed addresses: `az webapp show --query outboundIpAddresses`
(and `possibleOutboundIpAddresses`) gives what to allow. The plan says which addresses the customer must
add on their database and asks them to confirm it is done.

## 7. Prove it live

Run `core` section 10 against `https://<app>.azurewebsites.net`: routes, health route, sign-in and a
write/read-back through the real database, a refused request, and the application log for errors.
Check the first request after a cold start too: a slow first response is expected, a failure is not.

## 8. Record

The studio's live command-line monitors (the Deploy panel's navigation: what this target's own command line tool can show) are built from `run.json`, and a monitor is offered only when the values it needs are recorded. So write exactly these keys, with these names: `host.resource_group`, `host.app`, `host.plan`, `host.subscription`, `host.location`. Record each as soon as you know it.

In `run.json`: subscription id and name, resource group, plan and size, app name, location, the
runtime, the URL, the setting names (never values), the zip and commit deployed, the checks and
results, the monthly cost estimate, and the rollback and teardown commands.

## 9. Domain

Use the customer's own domain when they have one (`core` section 8); `<app>.azurewebsites.net` works
meanwhile. A custom domain needs a plan above `F1`.

- Read what App Service will ask the DNS to say: `az webapp show --resource-group <rg> --name <app> --query
  "{ip: inboundIpAddress, verification: customDomainVerificationId}"`. A subdomain needs a `CNAME` to
  `<app>.azurewebsites.net` and a `TXT` record `asuid.<name>` with the verification id; the bare name needs
  an `A` record to that address and the same `TXT` record.
- If the domain's DNS is an Azure DNS zone in the subscription, create those records yourself (`az network dns
  record-set cname|a|txt set-record`); otherwise give exactly them to the customer once and poll
  `Resolve-DnsName <name>` until they resolve.
- Bind the name: `az webapp config hostname add --resource-group <rg> --webapp-name <app> --hostname <name>`,
  then the free managed certificate: `az webapp config ssl create --resource-group <rg> --name <app>
  --hostname <name>` and `az webapp config ssl bind --resource-group <rg> --name <app> --certificate-thumbprint
  <thumbprint> --ssl-type SNI`. Keep `--https-only true`.
- Prove it (`core` section 8, step 4). Never buy or transfer a domain, or change nameservers, without the
  customer's word.

## 10. Scaling

Scale up (a bigger plan) with `az appservice plan update --resource-group <rg> --name <plan> --sku <sku>`;
scale out (more instances) with `az appservice plan update ... --number-of-workers <n>`, or automatically:
`az monitor autoscale create --resource-group <rg> --resource <plan> --resource-type Microsoft.Web/serverfarms
--min-count <min> --max-count <max> --count <start>` and `az monitor autoscale rule create --condition
"CpuPercentage > 70 avg 5m" --scale out 1` (and the matching scale-in rule). The free and shared tiers cannot
scale out, the basic tier only manually up to three, standard and above automatically. Instances share
nothing: sessions and files must not live in one instance's memory or disk. State the limits and the price
of each step in the plan, and never move up a tier on a failure.

## 11. Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the pages do not already settle (see `core` section 12):

1. Which subscription, when the account has more than one (`az account list`)?
2. A new resource group (its name) or an existing one?
3. Which location?
4. Which App Service plan size: `F1` (free, limited), `B1`, `B2`, `S1` (adds slots and autoscale) or
   `P1v3`? State the monthly price and what the choice allows (Always On, slots).
5. What is the web app called (it becomes `<name>.azurewebsites.net`)?
6. Should a staging slot and a swap release be used (needs `S1` or above)?
7. Should Application Insights be added for monitoring, and how long should logs be kept?
8. Should secrets live in Key Vault with a managed identity, or as application settings?
9. Is there a custom domain, with a managed certificate (the customer creates the DNS records)?
10. Should the app scale out automatically, and to how many instances at most?
