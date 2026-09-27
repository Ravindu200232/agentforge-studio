---
name: stack-mern-microservices
description: How a workspace of services behind one gateway is deployed (AWS EC2, AWS ECS or Azure only): the instance layout, service discovery, per-service databases, health of the whole, and the questions to ask the customer.
---

# Deploying a MERN microservices workspace

Read this page after `core/SKILL.md` and the page for the chosen target. It says what is particular to a
workspace of several Node services behind one public gateway, with a React client and MongoDB. Only
**AWS EC2, AWS ECS and Azure App Service** deploy this stack: Vercel, Netlify and GitHub Pages run one
application, not a set of cooperating services, so they are not offered. If the customer asks for
another target, say why and offer these.

## What to read in the project

The root `package.json` (workspaces, scripts, `engines`), `packages/*/package.json` and each
`packages/<name>/src/` (`server.js`, `config.js`, `db.js`, models, routes), the gateway's `config.js`,
`proxy.js` and `app.js` (which paths it proxies to which service, how it serves the built client),
`client/` (Vite config, build output `client/dist`), `scripts/` (`start-all`, `dev-all`, `seed`,
`port-guard`), `.env.example`, and the specification's list of bounded contexts. Make a table from what
you read: for each process, its name, its internal port variable (`<NAME>_PORT`, `<NAME>_URL`,
`SERVICE_PORT`), the database it uses and the routes the gateway sends to it. That table is the
foundation of the plan.

## How the pieces fit

- The **gateway** is the only public component. It owns the public port (`PORT`), serves the built
  client (`client/dist`), and proxies `/api/...` to services by address read from configuration
  (`<NAME>_URL`, or `<NAME>_PORT` on the same host). It never holds domain logic.
- Each **service** listens on an internal port (`SERVICE_PORT`) and is never exposed to the internet.
- `npm run build` builds the client bundle the gateway serves; there is no build step for the services.
- Two ways of starting it exist in the project: `npm start` runs the gateway alone (right where each
  service is started by something else), and `npm run start:all` (`scripts/start-all.mjs`) starts every
  service and the gateway as one process tree, giving each service an internal port and telling the
  gateway where it is, and taking the whole tree down if one process dies so the host restarts it.
- The gateway's `/ready` says only that the gateway process is up. It says nothing about the services
  behind it, so it is not a health check of the application.

## The layout is the customer's decision: ask

The right shape depends on cost, isolation and the customer's tolerance for complexity. Do not pick it
silently. Ask, one question at a time, recommending the smallest that satisfies the specification:

**EC2**
1. *One instance for everything* (gateway and every service under systemd, one unit per process, or the
   whole tree as one unit through `start:all`): cheapest, simplest, one Elastic IP, one database
   allow-list entry. All the processes share one machine's memory and fate. Or *one instance per
   service* plus a gateway instance: isolation and independent restarts, several instances to pay for
   and patch, private networking between them, and each service's address given to the gateway through
   its `<NAME>_URL`. Ask which; the recommendation is one instance unless the specification asks for
   independent scaling or isolation.
2. If one instance: the size. Estimate memory as about 150 MB per Node process, plus the operating
   system and the web server, plus headroom, and say the number; never exceed the size the customer
   chose without asking.

**ECS**
1. *One ECS service per microservice* (each with its own task definition, desired count, health check and
   scaling; the gateway service behind the public load balancer, the others behind an internal one or a
   service-discovery name), or *one task running every container* (the gateway and services as
   containers of one task, talking over localhost), or *one container running the whole tree*
   (`start:all`). State the cost and complexity of each and recommend one task with a container per
   process unless independent scaling is required.
2. Service discovery for the per-service option: Cloud Map service names or an internal load balancer;
   the gateway gets each address as `<NAME>_URL`.

**Azure App Service**
1. *One web app running the whole tree* (`start:all` as the start command; one plan, one address, the
   simplest), or *one web app per service plus a gateway web app* in the same plan (independent
   deployment and restart; the services' addresses are public unless access restrictions or virtual
   network integration make them private, and the gateway gets each as `<NAME>_URL`). Recommend one web
   app unless the customer wants independent releases.

**All targets**
3. *Databases*: one database per service in one cluster (each service gets its own database name,
   inside the customer's cluster) or one cluster per service (more isolation, more cost). The database
   name is never left out of a connection string, and no service may read another's database.
4. *Scaling and availability*: one copy of each process, or more than one for the gateway and busy
   services, and whether availability across zones matters. More copies mean the services must be
   stateless and share the signing secret.
5. *Names*: what the deployment, the stack and each service's resources are called.

## Making it work

- **Internal addresses and ports.** Every service's address reaches the gateway through
  configuration, not code. Give each service a unique internal port (`INTERNAL_PORT_BASE` or the
  per-service variables). Nothing but the gateway is in a public security group, load balancer listener
  or firewall rule: services accept connections only from the gateway's security group (or the private
  network), never from the internet.
- **Secrets shared across processes.** If the gateway and services verify the same tokens, they share
  one signing secret, generated once, stored once in the target's secret store, and injected into each
  process. It is kept across releases. Each service reads its own database connection string; never share
  one credential between services that the customer chose to isolate.
- **Startup order.** Services before the gateway; a service that is down is a 503 at the gateway, never a
  200. Each process restarts on failure (systemd `Restart=always`, ECS `essential` containers and a
  restart policy, App Service's own supervision through the tree-exit behaviour of `start:all`).
- **Build.** Install from the root lockfile, run `npm test` for every workspace, `npm run build` for the
  client, and package the workspace with the client's `dist` and only production dependencies. Container
  images (ECS) are built by the cloud build, one image for the whole tree or one per service, as the
  layout says.
- **Seeds.** `scripts/seed.mjs` may write development data: read it, and run against production only
  what the customer chose (see `core` section 6), per service database.

## What "live" means for this stack

A gateway that answers 200 is not proof. Beyond `core` section 10:

- the public address serves the client, and the gateway's `/ready` answers;
- **every service is reached through the gateway** by a real request to one of its routes, over the
  public address, that returns data from that service's database (list the routes from the gateway's
  proxy table, and call one per service);
- a service made unavailable produces the gateway's 503 (this is only observed when it is safe to do so,
  never by stopping production processes; read the code path instead and say so);
- each service's logs and the gateway's logs show no errors during those requests;
- no service port answers from the internet: try each internal port on the public address or the
  instance's public name and confirm it is refused.

A `health` route on the gateway that calls each service and reports them separately is the right thing
to add if the project has none; the plan names it as a step.

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle, after the layout questions above.
One at a time, recommendation first, and let "you decide" be an answer:

1. Where is the production MongoDB (one cluster or several), and are its connection strings saved in
   Settings?
2. Which region, given where the database and the users are?
3. Should each production database start empty, with only required reference data, or with demo data?
4. Does the customer have a custom domain for the gateway?
5. What may the whole deployment cost per month? (Say the estimate for the chosen layout.)
