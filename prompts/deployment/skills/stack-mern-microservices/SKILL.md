---
name: stack-mern-microservices
description: Deploy a MERN microservices application as real, separate instances - one Fargate task per package on AWS ECS, Cloud Map service discovery, only the gateway public, images built in the cloud never locally. AWS EC2 and Azure alternatives.
---

# Deploying a MERN microservices application

Read this page after `core/SKILL.md` and the page for the chosen target (AWS EC2, AWS ECS or Azure App
Service - this stack needs real server hosting and is not offered on Vercel, Netlify or GitHub). It says
what is particular to a workspace of **genuinely separate services**: `client/` (a Vite React SPA),
`packages/gateway/` (the one public door) and `packages/<name>/` (one bounded context each, added from
`scaffold/service/`). Each one is deployed as its own instance or container - that is the point of this
stack, and it is why it exists alongside `vite-mongo`, which is the same idea with exactly one service.

## What to read in the project

Root `package.json` (the `packages/*` and `client` npm workspaces - read `packages/` to see which
services actually exist; the base scaffold ships only `gateway`), `packages/gateway/src/config.js` (the
`<NAME>_URL`/`<NAME>_PORT` environment variable each service is reached through - this is already
environment-driven, never a hardcoded address, which is exactly what makes separate-instance deployment
possible with no code change), `packages/gateway/src/app.js` (which paths it proxies where, and that it
serves the built client), each `packages/<name>/src/{app.js,config.js,db.js}`, the root `Dockerfile` and
`.dockerignore`, `.env.example`, `scripts/seed.mjs`, and `.agentforge/PLUGIN.md` when a sign-in or
upload plugin was selected.

## How the pieces fit, deployed

- **Only the gateway is public.** Every service is reachable only from the gateway - nothing else ever
  gets a public address, a load balancer, or an inbound security-group rule from the internet.
- **Each service gets its own real instance** (an ECS Fargate task, or an EC2 instance, one per
  package) - not a thread, not a child process, not a shared container. This is what "separate
  instances" means for this stack, and it is true of `packages/gateway` too: the gateway is itself one
  more instance, the one with a public listener in front of it.
- **Service discovery replaces `127.0.0.1`.** Locally, `CATALOG_PORT` (an internal port on the same
  machine) is enough. Deployed, the gateway needs a real address for each service running on its own
  instance - that address is handed to it as `<NAME>_URL`, already exactly how `config.js` reads it.
  Nothing in the application code changes between local development and a real multi-instance
  deployment; only which environment variable value is supplied does.

## Recommended: AWS ECS Fargate with Cloud Map

The root `Dockerfile` builds one image per package (`--build-arg SERVICE=packages/<name>`), **built in
AWS CodeBuild, never with a local `docker build`** - follow `aws-ecs/SKILL.md` sections 1-2 once per
package that exists in `packages/`, with these changes from a single-service app:

1. **One ECR repository, many tags.** Push each package's image as `<package>-<commit>` to one shared
   repository rather than creating a repository per package - fewer resources, same isolation (each
   package's images are just a different tag prefix). `buildspec.yml` takes the package path as a
   variable so one CodeBuild project builds any of them.
2. **One Fargate task definition per package**, sized for that package's own load (a gateway proxying
   requests needs far less CPU than a service doing real work) - follow `aws-ecs/SKILL.md` section 2 once
   per package, in the same cluster.
3. **AWS Cloud Map (ECS Service Connect)**, one private DNS namespace for the cluster. Each service's
   ECS service registers itself (`catalog.internal`, for example), and the gateway's task definition sets
   `CATALOG_URL=http://catalog.internal:4001` (the service's container port) - this is the whole
   mechanism; no other wiring is needed because `proxyTo()` already just calls whatever URL it is given.
4. **Only the gateway's ECS service sits behind the Application Load Balancer** and CloudFront
   (`aws-ecs/SKILL.md` section 2, applied to the gateway's task only). Every other service's security
   group allows inbound **only** from the gateway's security group, on that service's container port -
   no target group, no listener rule, no public DNS name for it at all.
5. **Health**: every package answers `/health` identically (the gateway's own readiness, or a service's
   `src/app.js` route) - one ALB target-group health check and one ECS task health check path works
   for all of them.
6. **Scale each service independently** (`aws-ecs/SKILL.md` section 8, once per package) - the actual
   payoff of this architecture: a service under real load scales out on its own without touching the
   gateway or any other service.
7. **Release order**: deploy or update backend services before the gateway on a first release, so the
   gateway's first requests already have somewhere to proxy to; Cloud Map registration means order does
   not matter on a routine redeploy.
8. **Record**: the keys `aws-ecs/SKILL.md` section 7 lists, once per package (a list in `run.json` keyed
   by package name - cluster, service, task definition, log group, image tag - plus the one shared ECR
   repository, CodeBuild project and Cloud Map namespace).

## Alternative: AWS EC2, one instance per package

Cheaper for a small number of services, more to operate by hand. Follow `aws-ec2/SKILL.md` once per
package: the service's own small instance, no Elastic IP and no CloudFront for anything but the
gateway's instance (the others get no public address at all - a private-subnet security group open only
to the gateway's instance's security group, on the service's port). The gateway's `<NAME>_URL` is then
that service's private IP or private DNS name. No Docker is involved in this path; each instance runs
`node packages/<name>/src/server.js` under systemd exactly as `aws-ec2/SKILL.md` describes for a
single-service app.

## Alternative: Azure

One App Service (or Container App) per package, in the same VNet, with VNet integration so services
reach each other by private address instead of the public internet; only the gateway's app gets a public
hostname and a custom domain. Follow `azure/SKILL.md` once per package for the resource and release
steps; the `<NAME>_URL` environment variable on the gateway's app is the other services' private FQDNs.

## The MongoDB connection

`MONGODB_URI` is asked for and verified for real before it is accepted (`"check": "mongodb"`, see
`stack-vite-mongo/SKILL.md`'s identical section) - never a loopback address. Each service may use its
own database name within the one real cluster the deployment was given (a separate database per bounded
context is the usual pattern here); the connection string's host is the same real, internet-reachable
cluster for all of them. List the fixed outbound address of whichever target was chosen (NAT gateway,
Elastic IP, or VNet gateway) on the Atlas cluster's Network Access list.

## What "live" means for this stack

Beyond `core` section 10: the gateway's public address serves the built client's own content; a request
that needs a service (for example `/api/products`) is actually forwarded and answered by that service
running on its own instance, not a 503 ("Upstream service unavailable" is the honest failure, never a
silent empty 200); a service is confirmed unreachable from the internet directly (only the gateway's
public address is live); a full round trip through the real UI (sign in, create something, read it back)
works against the real cluster; and each instance's own logs show it is the one that actually handled
the request (proof the services are truly separate, not one process pretending to be several).

## Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the skill pages do not already settle. One at a time, recommendation
first, and let "you decide" be an answer:

1. ECS Fargate with Cloud Map (recommended - independent scaling, no servers to patch, image built in
   the cloud) or one EC2 instance per service (cheaper for few, low-traffic services, no Docker at all)?
   State the trade-off and the estimated monthly cost of each.
2. How many packages exist under `packages/` right now, and does the customer expect more before
   launch (more services, more task definitions/instances to size and price)?
3. Per-service CPU/memory (Fargate) or instance size (EC2), and whether each should scale automatically.
4. Is there already a MongoDB Atlas cluster connected for this project, or should one be created now?
5. Which region should the cluster and every instance run in?
6. Should the production database start empty, with only required reference data, or with demo data?
7. Does the customer have a custom domain for the gateway's public address?
8. Which environment variables in `.env.example` should be set now, and which are left for the customer?
