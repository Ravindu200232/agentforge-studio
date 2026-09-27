---
name: aws-ecs
description: Deploy this project to AWS ECS Fargate behind a load balancer, image built in the AWS cloud (never locally), HTTPS through CloudFront, circuit-breaker rollback.
---

# Deploy to AWS ECS (Fargate)

The application runs as containers on Fargate behind an Application Load Balancer; the image is built
in AWS (CodeBuild) and stored in ECR; CloudFront gives the public HTTPS address. There is no Docker on
this computer and none is used here: the Dockerfile is source code that AWS builds. Read
`core/SKILL.md` and `aws/SKILL.md` first; this page is what is specific to ECS.

This target is not free-tier: the load balancer and Fargate tasks bill by the hour. Say the estimate in
the plan and ask if the customer wants the cheaper single-instance target instead.

## 1. Container source in the repository

- `Dockerfile`: multi-stage; install from the lockfile; build; a small runtime stage on a slim Node
  image running as a non-root user, only production dependencies (or the framework's standalone
  output), `EXPOSE <port>`, `HEALTHCHECK`, `CMD` the project's real start command.
- `.dockerignore`: `.agentforge`, `.git`, `node_modules`, `.next`, tests and reports, `.env*`.
- `buildspec.yml`: log in to ECR, `docker build`, tag with the git commit and `latest`, push.
  Secrets are never build arguments.

## 2. What is built

Stack `<app>-<env>` in `deploy/aws/ecs.yml` (split into `network`/`service` templates when that is
clearer):

- an ECR repository (image scanning on push, lifecycle rule keeping the last ten images);
- a CodeBuild project (privileged mode for the Docker build, its own role, logs) reading source from
  an S3 object;
- a cluster, a task execution role (pull image, write logs, read this application's secrets) and a task
  role for the application itself (nothing unless it needs it);
- a task definition: Fargate, `awsvpc`, CPU and memory of the size the customer chose, the image,
  container port, `awslogs` to a log group with retention, environment for plain configuration, and
  `secrets` with `valueFrom` pointing at Secrets Manager;
- an Application Load Balancer, target group with the health check path, listener on 80;
- a service in the default VPC's subnets (or the customer's): desired count of at least 1,
  `deploymentConfiguration` with `deploymentCircuitBreaker: {enable: true, rollback: true}`, minimum
  healthy 100 percent and maximum 200 percent so a release never drops capacity;
- security groups: the load balancer accepts 80 from the CloudFront origin-facing prefix list, the tasks
  accept the container port only from the load balancer;
- a CloudFront distribution in front of the load balancer (see `aws/SKILL.md` section 5).

## 3. First release: image in the cloud

1. Local gate (`core` section 7).
2. Create the stack once with the ECR repository and CodeBuild project (so the image exists before
   the service starts), or deploy with the service at desired count 0 and raise it after the first
   image. A service whose image does not exist crash-loops.
3. Zip the source (without `.agentforge`, `node_modules`, `.env*`), upload it to S3, and run
   `aws codebuild start-build --project-name <name> --source-location-override <bucket/key>
   --source-type-override S3`. Follow it with `aws codebuild batch-get-builds --ids <id>` until it is
   `SUCCEEDED`; on failure read the build's log stream, fix the source, build again.
4. Deploy or update the stack with the image tag (the commit) as a parameter.
5. `aws ecs wait services-stable --cluster <c> --services <s>`. If the circuit breaker tripped
   (`aws ecs describe-services` shows a rolled-back deployment), read the stopped task reason
   (`aws ecs describe-tasks`, `aws ecs list-tasks --desired-status STOPPED`) and the log group, fix the
   cause, release again.

## 4. Later releases

Rebuild the image with a new tag, register a new task-definition revision with that tag
(`aws cloudformation deploy` with the new parameter does this), and let ECS roll it. Never use a
mutable `latest` as the deployed tag.

## 5. Proving it live

Follow `core` section 10 against the CloudFront address. Also confirm the target group is healthy
(`aws elbv2 describe-target-health`), the running task count equals the desired count, and the log
group has the requests you just made.

## 6. Rolling back and removing

- The circuit breaker rolls back a release that never became healthy. For a release that is healthy
  but wrong: update the service to the previous task-definition revision
  (`aws ecs update-service --cluster <c> --service <s> --task-definition <family>:<previous>`), wait
  for stability, re-check.
- Teardown is `aws cloudformation delete-stack` and emptying the ECR repository and buckets, only
  when the customer asks; a load balancer running idle still bills.

## 7. Record

The studio's live command-line monitors (the Deploy panel's navigation: what this target's own command line tool can show) are built from `run.json`, and a monitor is offered only when the values it needs are recorded. So write exactly these keys, with these names: `host.region`, `host.stack_name`, `host.cluster`, `host.service`, `host.task_definition`, `host.target_group_arn`, `host.log_group`, `host.secret_name` (the Secrets Manager path this application's secrets live under), `host.repository_name`, `host.build_project`, `host.distribution_id`. Record each as soon as you know it.

In `run.json`: account id, region, stack name and outputs (cluster, service, repository, load balancer,
distribution id, the HTTPS address), the image tag and commit deployed, task-definition revision, CPU
and memory, the build id, the checks and results, the monthly cost estimate, and the rollback and
teardown commands.

## 8. Scaling

Scale the service, not the task: `aws application-autoscaling register-scalable-target
--service-namespace ecs --scalable-dimension ecs:service:DesiredCount --resource-id
service/<cluster>/<service> --min-capacity <min> --max-capacity <max>`, then `aws application-autoscaling
put-scaling-policy --policy-type TargetTrackingScaling` on `ECSServiceAverageCPUUtilization` (and, when the
load balancer fronts it, `ALBRequestCountPerTarget`). Use the minimum and maximum the customer agreed to, at
least two tasks in two zones when availability matters. A bigger task is a new task-definition revision.
Remember that maximum tasks times each task's pool must stay under the database's connection limit.

## 9. Questions to ask the customer

These are prompts, not a script: write each question yourself for this project and ask only what the
project, an earlier answer and the pages do not already settle (see `core` section 12 and `aws/SKILL.md`
for the general ones):

1. How much CPU and memory per task (for example 0.25 vCPU and 0.5 GB up to 1 vCPU and 2 GB)? State the
   price of the choice.
2. How many tasks should run (one is the cheapest; two across zones survive a failure), and should the
   service scale automatically between a minimum and a maximum on CPU or request load?
3. Should the tasks run in public subnets with public addresses (cheapest, no fixed outbound address) or
   in private subnets behind a NAT gateway (a fixed outbound address for the database allow-list, extra
   monthly cost)?
4. Load balancer only, or CloudFront in front of it (needed for free HTTPS without a domain)?
5. How many images should the repository keep, and should image scanning block a release on findings of
   a chosen severity?
6. Should the release wait for a manual approval between the image build and the rollout?
