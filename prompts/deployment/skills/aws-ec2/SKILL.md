---
name: aws-ec2
description: Deploy this project to one AWS EC2 instance with nginx and systemd, delivered through S3 and SSM, HTTPS through CloudFront.
---

# Deploy to AWS EC2

One small Linux instance with a fixed public address, nginx in front of the application, the
application under systemd, releases delivered as an artifact through S3 and executed over Systems
Manager (no SSH, no key pair). HTTPS comes from CloudFront. Read `core/SKILL.md` and
`aws/SKILL.md` first; this page is what is specific to EC2.

## 1. What is built

A CloudFormation stack `<app>-<env>` in `deploy/aws/ec2.yml` creating:

- a security group: 80 from the CloudFront origin-facing prefix list only, nothing on 22, all egress;
- an IAM role and instance profile: `AmazonSSMManagedInstanceCore`, read on the release bucket, read on
  this application's secrets, CloudWatch Logs write for its own log group;
- an instance from the latest Amazon Linux 2023 image (resolve it from the SSM public parameter
  `/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64`, or the `arm64` one for
  `t4g` sizes), the size the customer chose, an encrypted gp3 root volume, IMDSv2 required, tagged;
- an Elastic IP (one fixed address for the database allow-list) associated with it;
- a private S3 bucket for release artifacts (block public access, versioning on);
- a CloudWatch log group with retention;
- a CloudFront distribution in front of the instance's public DNS name (see `aws/SKILL.md` section 5).

Ask the customer for the size only if the plan has no answer; the default is the smallest size that
is free-tier eligible in the account and region, and never grow it on a failure.

## 2. First boot (user data, kept in the template)

Install the Node.js LTS the project's `engines` asks for, nginx and the SSM agent (present on the
image); create a non-login system user `app`; create `/opt/<app>/releases` and `/etc/<app>/`; write the
nginx site (proxy to `127.0.0.1:<port>`, forward `Host`, `X-Forwarded-For`, `X-Forwarded-Proto`,
gzip, sensible timeouts, a `/healthz`-style pass-through); install the systemd unit:

```
[Service]
User=app
WorkingDirectory=/opt/<app>/current
EnvironmentFile=/etc/<app>/env
ExecStart=/usr/bin/node server.js        # the project's real start command
Restart=always
NoNewPrivileges=true
```

Confirm before continuing that the instance is registered with SSM:
`aws ssm describe-instance-information --filters Key=InstanceIds,Values=<id>` shows `Online`.

## 3. Build and package (on this machine)

Local gate first (`core` section 7). Then produce the smallest runnable artifact for the framework
(for Next.js, the standalone output with `.next/static` and `public` copied beside `server.js`),
create `release-<git short sha>-<timestamp>.tar.gz`, and upload it:
`aws s3 cp <file> s3://<bucket>/releases/<file>`. Do not include `.agentforge`, tests, `.env*` or
development dependencies. Native modules must be built for Linux: if the project has any, build the
artifact on the instance during the release (install with the lockfile) instead of shipping local
`node_modules`.

## 4. Release over SSM

Send one command document to the instance (`aws ssm send-command --document-name
AWS-RunShellScript --instance-ids <id> --parameters file://<params.json>`; keep the script in the
repository as `deploy/aws/release.sh`) that:

1. downloads the artifact from S3 to a new `releases/<id>` directory and unpacks it;
2. writes `/etc/<app>/env` (mode 600, owner root) from the secrets in Secrets Manager, without
   echoing them;
3. switches the `current` symlink to the new release atomically and restarts the service;
4. waits for the local health route to answer (retry for up to a minute);
5. on failure, points `current` back at the previous release, restarts, and exits non-zero;
6. keeps the last five releases and removes older ones.

Follow it: `aws ssm wait command-executed`, then `aws ssm get-command-invocation --command-id <id>
--instance-id <id>` for the exit code and the output (standard error included). A non-zero code is a
failed release, already rolled back by the script; diagnose from the output, fix, release again.

## 5. Proving it live

Follow `core` section 10 against the CloudFront address. Also: `aws ssm send-command` a read-only check
(`systemctl is-active <app>`, `curl -s localhost:<port>/<health>`, the last 50 lines of
`journalctl -u <app>`) and confirm the log group receives lines.

## 6. Rolling back and removing

- Bad release: the script rolled back if the health check failed; otherwise run the rollback script
  through SSM (switch `current` to the previous release id, restart, health-check) and re-check.
- Tear down with `aws cloudformation delete-stack` only when the customer asks; empty the bucket first
  only then. Tell them the address is released.

## 7. Record

The studio's live command-line monitors (the Deploy panel's navigation: what this target's own command line tool can show) are built from `run.json`, and a monitor is offered only when the values it needs are recorded. So write exactly these keys, with these names: `host.region`, `host.stack_name`, `host.instance_id`, `host.bucket`, `host.log_group`, `host.secret_name` (the Secrets Manager path this application's secrets live under), `host.distribution_id`. Record each as soon as you know it.

In `run.json`: account id, region, stack name and outputs (instance id, Elastic IP, bucket,
distribution id, the HTTPS address), instance size, release id and commit deployed, the SSM command
ids, the checks and results, the monthly cost estimate, and the rollback and teardown commands.

## 8. Scaling

One instance is a fixed size. To grow later, on the customer's word: change the size (`aws ec2
stop-instances`, `aws ec2 modify-instance-attribute --instance-type Value=<type>`, `aws ec2 start-instances`;
a few minutes of downtime, and the Elastic IP keeps the address), or, when one machine is not enough, move to
a launch template and an Auto Scaling group behind a load balancer: a different layout that is proposed and
planned, never done silently. Say in the plan how many concurrent users the chosen size comfortably holds
(estimate memory per process and per connection), when it would need to grow, and that snapshots and a CPU or
status-check alarm are recommended (`aws cloudwatch put-metric-alarm`).

## 9. Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the pages do not already settle (see `core` section 12 and `aws/SKILL.md`
for the general ones):

1. Which instance size, and which processor family (x86 `t3` or Arm `t4g`; Arm is cheaper, and native
   modules must have Arm builds)? State what is free-tier eligible in the account.
2. How large should the disk be, and should nightly snapshots (AWS Backup or a lifecycle policy) be kept?
3. Administration through SSM only (recommended, port 22 closed), or is a key pair and SSH wanted?
4. Should the operating system apply security updates automatically?
5. Should a stopped or crashed instance be replaced automatically (an auto-recovery alarm)?
6. Should the Elastic IP be kept when the deployment is removed?
