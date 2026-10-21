---
title: "Lambda Web Functions: where they fit, and what the deploy command leaves outside your state"
date: 2026-10-21
slug: lambda-web-functions-iac
excerpt: "Lambda Web Functions run a plain Node.js HTTP server and bill active CPU, but the one-command CLI deploy creates a bucket and an IAM role outside any state file. When it costs less than Fargate, and how to model it with awscc while hashicorp/aws catches up."
tags: [AWS, Serverless, Terraform, PlatformEngineering, FinOps]
---

# Lambda Web Functions: where they fit, and what the deploy command leaves outside your state

AWS launched Lambda Web Functions on October 12, 2026. The pitch is simple: take the Node.js HTTP server you already run locally, deploy it with one command, and let Lambda scale it, spread it across Regions and bill you for active CPU instead of wall-clock time.

I went through the docs, the pricing page and the Terraform provider tracker, and ran what I could without touching a real account. The runtime model is good. The part that needs a decision before anyone ships it is ownership: the one-command deploy creates resources that no state file knows about, and deleting the function later doesn't clean them all up.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version, flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">One deploy, outside your state</h3><p class="ds-body">Lambda now runs a plain HTTP server. Its CLI also creates a bucket and a role.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">The model</span><h3 class="ds-title">Lambda has three shapes now</h3><p class="ds-body">Event Functions, Web Functions, MicroVMs. Web means an HTTP server, up to 128 requests per environment.</p></section>
<section class="deck-slide"><span class="ds-kicker">The code</span><h3 class="ds-title">It's just a server</h3><p class="ds-body">Listen on <code>AWS_LAMBDA_HTTP_ENDPOINT</code>. Runs locally as is, must listen within 10 seconds on Lambda.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The bill</span><h3 class="ds-title">Active CPU, always-on memory</h3><p class="ds-body">About 3.1x Fargate Arm per active vCPU-hour. Break-even near 32% average CPU, by my napkin math.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The leftovers</span><h3 class="ds-title">What deploy creates</h3><p class="ds-body"><code>delete-web-function</code> removes the function, revisions and endpoints. The role, bucket and log groups stay.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">IaC today</span><h3 class="ds-title">Terraform, today</h3><p class="ds-body">hashicorp/aws 6.69.1 rejects the resource type. awscc 1.106.0 validates. CloudFormation has all three.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">The split</span><h3 class="ds-title">Who owns what</h3><p class="ds-body">Terraform owns bucket, role, function, endpoint. CI ships a zip and a revision, then moves weights.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Deploys vs infrastructure</h3><p class="ds-body">Revisions are deploys. Functions and endpoints are infrastructure.</p></section>
</div>
</div>
</details>

## Lambda has three shapes now

The launch also renamed what we already had. Classic Lambda is now "Event Functions", and it sits next to two new shapes built on the same Firecracker isolation:

<div class="viz-label">three programming models, one service</div>
<div class="card-grid">
<div class="viz-card accent-cyan"><span class="vc-name">Event Functions</span><span class="vc-note">The handler you know. One request per environment, wall-clock billing. Queues, S3 events, EventBridge.</span><span class="vc-tag">existing</span></div>
<div class="viz-card accent-ok"><span class="vc-name">Web Functions</span><span class="vc-note">Your code listens on a port. Up to <em>128</em> concurrent requests per environment, billed on active CPU plus memory.</span><span class="vc-tag">new</span></div>
<div class="viz-card accent-warn"><span class="vc-name">MicroVMs</span><span class="vc-note">Stateful sandboxes with a lifecycle you manage, for running untrusted or user-generated code.</span><span class="vc-tag">new</span></div>
</div>

At launch, Web Functions run Node.js 24 (`nodejs24.x`) on Arm64 only, in five Regions: us-east-1, us-east-2, us-west-2, ap-northeast-1 and eu-west-1. Python, Java and .NET teams stay on Event Functions for now.

The 128 is a ceiling, not the default. `maxConcurrencyPerEnvironment` is a revision setting with valid values from 1 to 128 and a default of 64, and Lambda applies its own dynamic limit underneath it based on resource usage.

## It really is just a server

The only contract with the runtime is one environment variable. Lambda sets `AWS_LAMBDA_HTTP_ENDPOINT` to `host:port`, and your server must start listening there within 10 seconds of initialization. Here is the smallest version I could write, with no framework at all:

```javascript
import { createServer } from 'node:http';

const [host, port] = process.env.AWS_LAMBDA_HTTP_ENDPOINT.split(':');

createServer((req, res) => {
  res.writeHead(200, { 'content-type': 'application/json' });
  res.end(JSON.stringify({ path: req.url, pid: process.pid }));
}).listen(Number(port), host, () => {
  console.log(`listening on ${host}:${port}`);
});
```

Locally, you set the variable yourself:

```text
$ AWS_LAMBDA_HTTP_ENDPOINT=127.0.0.1:3000 node index.js
listening on 127.0.0.1:3000

$ curl -s http://127.0.0.1:3000/orders/42
{"path":"/orders/42","pid":37118}
```

That's the whole porting story for an Express, Hono or Fastify app: read the address from the variable instead of hardcoding 3000. Two things change in how you write the app, though. Many requests share one process, so the code has to be safe for concurrent use, which most Node servers already are. And on scale-down Lambda sends `SIGTERM` and gives the process up to one second before it terminates the environment.

The docs also make a point worth repeating: an **Active** revision and an **Active** endpoint don't prove your server started. Lambda doesn't check that anything is listening. After every deploy, send a real request.

## How you pay, and where Fargate still wins

Web Functions bill three things plus data transfer. In us-east-1 on Arm:

| Dimension | Price | Notes |
|---|---|---|
| Requests | $0.30 per 1M | every request |
| Active vCPU | $0.0000276944 per vCPU-second | only while your code is on the CPU |
| Memory | $0.0000036667 per GB-second | for as long as the environment exists, idle time included |

The active-CPU line is the selling point. A request waiting 150 ms on Postgres burns almost no CPU, and since one environment serves many requests at once, memory is shared across them too. AWS's own pricing example for an I/O-heavy API (10M requests a month, 200 ms each, 50 ms of it active CPU, about 300 MB) comes to $19.61 a month.

The first thing I'd want to know is whether a Fargate service should move. So I converted both price lists to hours, using the public us-east-1 prices for Fargate on Arm:

| Per hour | Web Functions | Fargate Arm | Ratio |
|---|---|---|---|
| vCPU | ~$0.0997 (active only) | $0.03238 (allocated) | ~3.1x |
| Memory (GB) | ~$0.0132 | $0.00356 | ~3.7x |

Fargate bills the vCPU you allocate, all the time. Web Functions bill the vCPU you use, at about 3.1 times the rate. So on the CPU line alone, the break-even sits at roughly 32% average utilization of the Fargate task: below it, Web Functions is cheaper; above it, keep the task. Memory pushes the other way at 3.7x, and requests add a line Fargate doesn't have.

This is napkin math on list prices, not a benchmark. It ignores Savings Plans on the Fargate side, the scale-to-zero on the Lambda side, and the fact that a Fargate service usually runs at least two tasks for availability. Put your own utilization numbers in before you decide anything.

## What one deploy command creates

The launch blog's demo is a single line, and the multi-Region version is one flag longer:

```bash
aws lambda-web deploy --name my-web-app --code ./my-app \
    --regions us-east-1,eu-west-1,ap-northeast-1
```

Here's what the "Creating a Web Function" page says the command does on the first run, and what `aws lambda-web delete-web-function` takes back later:

| Resource | deploy | delete-web-function |
|---|---|---|
| S3 bucket `awscli-lambdaweb-<account-id>-<region>-an`, versioned | creates or reuses | stays, with every package version |
| IAM role `awscli-lambdaweb-<name>` | creates or reuses | stays |
| Web Function | creates | removed |
| Revision | creates | removed |
| Endpoint `dev` (HomeRegion, `LatestRevision`) | creates | removed |
| CloudWatch Logs log groups | written by Lambda | stay |

Three more details from the docs that matter in a pipeline:

- When `deploy` creates a function without `--hello-world`, it waits for you to press Enter. In CI you pass `--create`, which means a CI job with broad IAM permissions can create roles and buckets on its own.
- The `--hello-world` starter endpoint accepts unauthenticated requests by default. `--auth-type IamAuth` turns on SigV4 (SigV4a for MultiRegion endpoints).
- Deleting an endpoint retires its domain name for good. Lambda never hands it to anyone again, including you.

These are sensible defaults for a five-minute demo. In an account where every role and bucket is supposed to have an owner and a line in a state file, they leave orphans behind.

<div class="viz-label">how a one-command deploy drifts away from IaC</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">A developer runs <b>deploy</b> to try it out. A bucket, a role, a function and an endpoint appear.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">The demo becomes the service. CI gets <b>--create</b> and the same command.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">Someone adds <b>--regions</b> and gets a MultiRegion endpoint, managed only from the home Region.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">The function is deleted. <b>The role, the bucket and the log groups stay</b>, and nothing records who made them.</span></div>
</div>

## The multi-Region rules you can't change later

`--regions` gives you a `MultiRegion` endpoint: one global domain, latency-based routing on a best-effort basis. The docs add constraints that are easy to miss in a one-liner:

<div class="viz-label">multi-Region constraints</div>
<div class="card-grid">
<div class="viz-card accent-err"><span class="vc-name">Fixed at creation</span><span class="vc-note">Endpoint type and target Regions can't be changed. A different Region list means a new endpoint and a new domain.</span><span class="vc-tag">immutable</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Home Region only</span><span class="vc-note">Replica Regions have no control plane. Every API call, even a read, goes to the home Region or fails.</span><span class="vc-tag">control plane</span></div>
<div class="viz-card accent-warn"><span class="vc-name">No auto-deploy</span><span class="vc-note"><code>LatestRevision</code> is HomeRegion-only. MultiRegion moves traffic only when you change revision weights.</span><span class="vc-tag">weights</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">Eventually consistent</span><span class="vc-note">Don't assume every Region runs the new revision until each <code>regionalEndpoints</code> entry says <code>Successful</code>.</span><span class="vc-tag">rollout</span></div>
</div>

The weights themselves are reasonable: one or two revisions, integers from 1 to 100 that sum to exactly 100. That's a canary without extra tooling, as long as something owns the weights.

## Where IaC support stands on October 21

Terraform can manage Web Functions today, just not through the provider most people use.

The `hashicorp/aws` provider doesn't have the resources yet. With the latest release, 6.69.1 from October 15:

```hcl
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.69.1"
    }
  }
}

resource "aws_lambdaweb_function" "app" {
  function_name = "orders-api"
}
```

```text
$ terraform validate
Error: Invalid resource type

  on main.tf line 10, in resource "aws_lambdaweb_function" "app":
  10: resource "aws_lambdaweb_function" "app" {

The provider hashicorp/aws does not support resource type
"aws_lambdaweb_function".
```

The feature request is issue #50429 (23 thumbs-up so far), and the implementation is PR #50452, open and waiting for review, with 47 acceptance tests passing according to its description.

CloudFormation already has three resource types: `AWS::Lambda::WebFunction`, `AWS::Lambda::WebFunctionRevision` and `AWS::Lambda::WebFunctionEndpoint`. Because the `awscc` provider is generated from the CloudFormation registry, it picked them up in 1.105.0 on October 7. This configuration passes `terraform validate` with awscc 1.106.0 (validated only, not applied; I didn't create anything in a real account):

```hcl
resource "awscc_lambda_web_function" "app" {
  function_name = "orders-api"
}

resource "awscc_lambda_web_function_revision" "current" {
  function_name = awscc_lambda_web_function.app.function_name

  build_config = {
    code_config = {
      s3_object = {
        bucket     = var.code_bucket
        key        = var.code_key
        version_id = var.code_version
      }
    }
    runtime_config = {
      runtime = "nodejs24.x"
    }
  }

  service_config = {
    execution_role_arn              = var.execution_role_arn
    max_concurrency_per_environment = 64
    timeout_seconds                 = 30
  }
}

resource "awscc_lambda_web_function_endpoint" "global" {
  function_name = awscc_lambda_web_function.app.function_name
  endpoint_name = "prod"
  endpoint_type = "MultiRegion"
  auth_type     = "ApplicationManaged"
  regions       = ["us-east-1", "eu-west-1", "ap-northeast-1"]

  revision_weights = [{
    revision_id = awscc_lambda_web_function_revision.current.revision_id
    weight      = 100
  }]

  scaling_config = {
    max_environments = 20
  }
}
```

```text
$ terraform validate
Success! The configuration is valid.
```

In the CloudFormation schema every revision property is immutable, and so are the endpoint's `EndpointType` and `Regions`. In practice: a code change replaces the revision resource, and a Region-list change replaces the endpoint and its domain.

One warning from the open aws provider PR is worth reading even before it merges. Its draft docs for `aws_lambdaweb_function` say that if the function's inline endpoint is MultiRegion or PerRegion, publishing a new revision doesn't move traffic, "even though the apply succeeds and the following plan is empty". The PR's answer is a separate endpoint resource whose weights reference the latest revision. That's the same split I'd make anyway.

> Revisions are deploys. Functions and endpoints are infrastructure.

## The split I'd use

Our Tech catalog rule for AWS is "no console-built foundations", and a CLI-built one isn't better. So the long-lived parts go in state, and CI only does what changes on every merge:

<div class="viz-label">who owns what</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">Terraform</span><span class="fs-role">bucket, role, function, endpoint, max_environments</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">CI</span><span class="fs-role">upload zip, create revision, wait for Active</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">Rollout</span><span class="fs-role">weights 90/10, then 100, or back</span></div>
</div>

It's the same contract many teams already use for ECS: Terraform owns the service, the pipeline owns the task definition revision. The awscc example above pins the revision in state, which works for a team that deploys through Terraform. If CI ships revisions on its own, take `revision_weights` out of the endpoint resource's ownership (or use `ignore_changes`) so the next plan doesn't roll traffic back.

A few things I'd put on the checklist before a first production Web Function:

<ul class="checklist">
<li>Create the code bucket with versioning in IaC, and don't add a lifecycle rule that expires noncurrent versions: a revision whose S3 object version is gone moves to Failed, and so does your rollback</li>
<li>Pass <code>--bucket-name</code> and <code>--execution-role-arn</code> if anyone uses the CLI at all, so it reuses your resources instead of creating defaults</li>
<li>Pick the endpoint type and Regions once; changing them means a new domain</li>
<li>Set <code>max_environments</code> as a cost and blast-radius cap; each environment uses 2 vCPUs from a 2,000-vCPU per-Region account quota</li>
<li>Size the database pool per environment, times <code>max_environments</code>; this is where RDS Proxy or pgBouncer earns its keep</li>
<li>Add a smoke request after every deploy, because Active doesn't mean listening</li>
</ul>

## Where I'd use it

For a Node.js API or an SSR frontend with spiky traffic and lots of waiting on downstream calls, this is the most interesting compute option AWS has shipped this year. Scale to zero, a real HTTP server, canary weights built in, and a CPU bill that ignores I/O wait.

For a steady service that keeps its CPU busy, or anything not written in Node, I'd stay on Fargate or EKS for now. And for any of them, I wouldn't let the deploy command be the thing that owns the function. It's a great demo, and a demo is all it should be.

---

Would you move a Fargate API onto this? Tell me its average CPU, and I'll tell you my guess.
