---
name: aws
description: Foundations for every AWS deployment with the AWS CLI: identity and region, infrastructure as code, tags, least privilege, secrets, HTTPS without a domain, cost, cleanup.
---

# AWS foundations

Read this page together with the page for the chosen AWS target (`aws-ec2` or `aws-ecs`) and with
`core/SKILL.md`. It holds what both AWS targets share. Everything is done with the `aws` command line
tool the customer signed in to; `aws <service> <command> help` is the truth for the installed version.

## 1. Identity, profile, region

- `aws --version`. The machine facts in the plan name the profile the customer signed in with; put
  `--profile <profile> --region <region>` on every command (or set `AWS_PROFILE` and `AWS_REGION` for
  the command). Never rely on a default profile.
- `aws sts get-caller-identity` proves the sign-in and shows the account id and principal. Record the
  account id and the principal in the run record, not any key. Browser sign-in credentials are
  short-lived: if a command answers "expired token" or "unable to locate credentials", stop and ask
  the customer to sign in again from Settings -> Integrations, then continue.
- The region is the customer's choice (ask when it matters: latency to the database, data residency,
  price). Every resource in one deployment lives in one region. Say it in the plan.
- Do not create IAM users, access keys or long-lived credentials, and do not assume roles the plan did
  not name.

## 2. Infrastructure is code, in the repository

- Write the infrastructure as CloudFormation under `deploy/aws/` in the project (template,
  parameters file without secrets, and a short `README` for what it creates), so it is reviewed,
  committed and repeatable. Validate before use: `aws cloudformation validate-template --template-body
  file://<template>`.
- Create or update with `aws cloudformation deploy --template-file <t> --stack-name <app>-<env>
  --capabilities CAPABILITY_NAMED_IAM --parameter-overrides Key=Value ... --tags app=<name> env=<env>
  managed-by=agentforge --no-fail-on-empty-changeset`. It creates a change set, so a redeploy changes
  only what differs. Stack outputs (`aws cloudformation describe-stacks --query
  "Stacks[0].Outputs"`) carry the addresses and ids later steps use.
- When a stack fails, read the cause before anything else: `aws cloudformation describe-stack-events
  --stack-name <name> --query "StackEvents[?contains(ResourceStatus,'FAILED')]"`. Fix the template,
  deploy again. A stack in `ROLLBACK_COMPLETE` from its first attempt is deleted only if this run
  created it and the customer has been told; anything else is never deleted.
- Tag every resource `app`, `env`, `managed-by`. Name resources from the application and the
  environment so they are findable and cannot collide with anything else in the account.

## 3. Least privilege and network

- Roles are created by the stack, scoped to this application's resources, with named actions and
  resource ARNs; no `*:*`, no `AdministratorAccess`. Compute gets an instance or task role and no
  access keys. If the signed-in identity lacks a permission, that is a question for the customer: say
  exactly which action and resource; never broaden a policy to get past it.
- Security groups open only what the traffic needs. SSH (port 22) stays closed; administration is
  through Systems Manager (SSM). The origin of a public application accepts traffic only from the
  CDN in front of it (the managed prefix list `com.amazonaws.global.cloudfront.origin-facing`).
- Private data stays private: a database, a bucket for release artifacts (block public access on), a
  secret.

## 4. Secrets

- Runtime secrets live in Secrets Manager (or SSM Parameter Store as SecureString) under a path for
  this application, and the compute role may read exactly those. Create them from a temporary file
  outside the project (`--secret-string file://<temp>`), from variables in the environment, delete the
  file, and never pass a secret as a visible argument. On a redeploy, update in place and keep existing
  generated values (session or signing keys).
- The application reads them at start (task-definition `secrets`, or an environment file written by
  the release script with mode 600). They never appear in templates, logs, tags or outputs.

## 5. HTTPS with or without a domain

A public address must be HTTPS. Without a domain the reliable way is a CloudFront distribution in
front of the origin: its default `https://<id>.cloudfront.net` name has a valid certificate at no
cost. Configure it with the origin protocol `http-only` to the origin's public DNS name, the cache
policy disabled for dynamic routes (or only static asset paths cached), all HTTP methods allowed,
cookies, query strings and the `Host`-relevant headers forwarded as the application needs, and viewer
protocol `redirect-to-https`. A distribution takes several minutes to deploy: `aws cloudfront wait
distribution-deployed --id <id>`. With a customer domain, use an ACM certificate (in `us-east-1` for
CloudFront) validated by a DNS record the customer creates, and a record pointing the domain at the
distribution or load balancer; say which records.

## 6. Database access

A hosted database usually allows connections only from listed addresses. Say what the deployed
application will connect from: an instance with an Elastic IP has one fixed address to allow;
containers in public subnets do not (allowing every address needs strong credentials and the
customer's explicit agreement; a NAT gateway with an Elastic IP gives one address at a monthly cost).
The plan states which and asks when the customer has to change their database's allow-list.

## 7. Cost, monitoring, cleanup

- State an approximate monthly cost in the plan and what is free-tier eligible in that account and
  region; do not exceed the size the customer chose and never scale up on a failure.
- Logs go to CloudWatch Logs with a retention period (14 to 30 days). Add a simple alarm only when
  asked.
- Provide the exact teardown command in the run record (`aws cloudformation delete-stack ...`) and
  never run it unless asked. Empty a bucket only when told to.

## 8. Proving it live

Follow `core` section 10 against the HTTPS address (CloudFront or the customer's domain), and also
check the origin's own health route through the platform (target group health, or the instance's
local health request through SSM). A response served by the CDN's cache is not proof of the origin:
call a dynamic route with a cache-busting query string.

## 9. Domain

Use the customer's own domain when they have one (`core` section 8); the CloudFront address works meanwhile.
The certificate for a CloudFront distribution must be issued in `us-east-1` whatever the deployment's region.

- Where is its DNS? `aws route53 list-hosted-zones-by-name --dns-name <domain>`. A hosted zone in this account
  means every step below can be done with the tools; none means the customer creates two records.
- Request the certificate: `aws acm request-certificate --domain-name <name> --validation-method DNS --region
  us-east-1` (add the `www` or bare form as a subject alternative name when both are wanted). Read the
  validation record from `aws acm describe-certificate`, create it with `aws route53
  change-resource-record-sets` (or hand it to the customer), then `aws acm wait certificate-validated`.
- Put the names and the certificate on the distribution through the stack (parameters for the alias names and
  the certificate ARN in `deploy/aws/`), deploy it, and wait `aws cloudfront wait distribution-deployed`.
- Point the name at the distribution: an alias `A` and `AAAA` record in the hosted zone to the distribution's
  domain name (hosted zone id `Z2FDTNDATAQYW2`), or a `CNAME` the customer creates for a subdomain. Redirect
  the form the customer did not choose.
- Prove it (`core` section 8, step 4). Never register or transfer a domain, or edit a record this run did
  not create, without the customer's word.

## 10. Scaling

The target's own page says what scales and how. Common to both AWS targets: tag and name everything so
the cost can be read per application, keep the database's connection limit in mind (instances or tasks
times each one's pool), and put a cost alert on the account (`aws budgets create-budget`) when the customer
asked for one.

## 11. Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the pages do not already settle (see `core` section 12), together with the
questions on the target's page:

1. Which AWS region? (Say the price and latency consequence: it must be near the database and users.)
2. HTTPS through the free CloudFront address, or through the customer's own domain (which needs an ACM
   certificate and a DNS record they create)?
3. Which network: the account's default VPC, or a dedicated VPC created by the stack?
4. Which monthly budget, and should a cost alert (AWS Budgets) be created at that amount?
5. How long should logs be kept (14, 30 or 90 days)?
6. Which tag values (owner, cost centre) does the customer want on every resource?
7. Where does the database allow connections from, and can the customer add the address this deployment
   will connect from?
