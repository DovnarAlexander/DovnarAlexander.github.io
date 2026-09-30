---
title: "Beanstalk moved onto EKS. Touch the cluster and it stops looking after it"
date: 2026-09-30
slug: beanstalk-cluster-mode
excerpt: "Elastic Beanstalk Cluster Mode runs your apps on a shared EKS cluster you may not modify: change it and the service stops maintaining it. What the docs say, what it costs, and what to borrow."
tags: [AWS, Kubernetes, PlatformEngineering, EKS, DevOps]
---

# Beanstalk moved onto EKS. Touch the cluster and it stops looking after it

On September 17 AWS launched Cluster Mode for Elastic Beanstalk. Several applications share one Amazon EKS cluster in your account. Nodes come from EKS Auto Mode, source code is built into images with Cloud Native Buildpacks in CodeBuild, and you interact with none of it directly. You give Beanstalk code, a Dockerfile, or an image in ECR, and it does the rest.

Read the launch post and it sounds like a friendlier EKS. Read the documentation and it turns out to be something more interesting: an internal developer platform, built by AWS, with its rules written down and enforced. I build platforms like this for clients, so the rules are the part I read first.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">Elastic Beanstalk · Amazon EKS</span><h3 class="ds-title">Touch the cluster, lose the platform</h3><p class="ds-body">Beanstalk Cluster Mode, read from the docs rather than the launch post.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">What AWS built</span><h3 class="ds-title">Code in, shared EKS out</h3><p class="ds-body">Buildpacks in CodeBuild, Auto Mode nodes, several apps on one cluster in <em>your</em> account.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">not yours</span><h3 class="ds-title">What you don't choose</h3><p class="ds-body">The cluster, its Kubernetes version, node capacity, add-ons, access. Your subnet set picks the cluster.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The rule</span><h3 class="ds-title">Touch it and it walks away</h3><p class="ds-body">Drift detected: no maintenance, no new environments, failed updates until you revert.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">contrast</span><h3 class="ds-title">Same contract, two enforcers</h3><p class="ds-body">Argo CD <code>selfHeal</code> reverts your edit. Beanstalk stops maintaining the cluster.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The bill</span><h3 class="ds-title">$0.03672 an hour, undiscounted</h3><p class="ds-body">Auto Mode fee on a $0.306 c6a.2xlarge. Savings Plans and Spot don't touch it. Below $500 a month, AWS says Standard.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">Read the docs</span><h3 class="ds-title">No immutable, no traffic splitting</h3><p class="ds-body">The launch blog lists both. The architecture docs say rolling or all at once.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">A platform is a promise</h3><p class="ds-body">About what you're not allowed to touch. AWS just wrote theirs down.</p></section>
</div>
</div>
</details>

## What you hand over, and what you don't get to choose

The interface is small on purpose. Application configuration lives in the `aws:elasticbeanstalk:eks:*` option namespaces, and the classic `aws:autoscaling:*` namespaces do not apply. This is the example straight from the architecture docs:

```bash
aws elasticbeanstalk update-environment \
    --environment-name my-cluster-env \
    --option-settings \
        Namespace=aws:elasticbeanstalk:eks:environment,OptionName=service-port,Value=8080 \
        Namespace=aws:elasticbeanstalk:eks:environment,OptionName=memory,Value=1Gi \
        Namespace=aws:elasticbeanstalk:eks:environment,OptionName=load-balancer-type,Value=ALB \
        Namespace=aws:elasticbeanstalk:eks:environment:autoscaling,OptionName=min-replica,Value=3 \
        Namespace=aws:elasticbeanstalk:eks:environment:autoscaling,OptionName=max-replica,Value=3 \
        Namespace=aws:elasticbeanstalk:eks:environment:deployment,OptionName=strategy,Value=RollingUpdate \
        Namespace=aws:elasticbeanstalk:eks:environment:deployment:strategy:rolling,OptionName=max-surge,Value=25% \
        Namespace=aws:elasticbeanstalk:eks:environment:deployment:strategy:rolling,OptionName=max-unavailable,Value=0
```

Anyone who has written a Deployment will recognise `memory: 1Gi`, `maxSurge` and `maxUnavailable` under the Beanstalk names. What you configure is the application. Everything under it is fixed:

| Setting | Who decides |
|---|---|
| Which cluster the environment runs on | the set of VPC subnets you pass |
| Kubernetes version | Beanstalk picks the newest it supports at cluster creation; fixed for the life of the cluster |
| Node capacity | EKS Auto Mode |
| Cluster infrastructure access | service-managed, only through the Beanstalk API, CLI or console |
| Add-on versions | pinned by Beanstalk, updated during a later environment create or update |

The subnet rule is the one that shapes everything else. Environments in the same account with the same subnet set share a cluster, and a new subnet set gets a new cluster, which takes about ten minutes the first time. You cannot change the subnets or the cluster, node and observability roles of an existing environment afterwards. Beanstalk rejects the update:

```text
Changes to EKS cluster configuration (subnets and IAM roles) are not currently supported for an existing environment. Please revert these option settings to continue.
```

The documented way out is a new environment with the settings you want and a CNAME swap. So the isolation boundary between tenants is decided once, at creation, by picking subnets. The multi-tenancy docs are candid that the in-cluster controls "do not make a shared cluster equivalent to separate clusters," and recommend separate subnet sets for different end customers, untrusted code, and compliance-separated workloads.

## The rule: touch the cluster and it walks away

The cluster lives in your account. Nothing stops you from opening it in the EKS console. The docs describe what happens if you change it:

```text
ERROR  Cluster drift detected for environment 'my-cluster-env'. <what changed>. Service will skip cluster maintenance for this environment.
```

While the cluster is drifted:

<div class="viz-label">what drift costs you</div>
<div class="timeline">
<div class="tl-step tl-warn"><span class="tl-text">Someone changes the cluster <b>outside Beanstalk</b>, in the console or with a script.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">Beanstalk detects drift and <b>stops maintaining</b> the cluster, including add-on updates.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">No new environments are placed on it, and <b>updates to running environments fail</b>.</span></div>
<div class="tl-step"><span class="tl-text">You <b>revert the change</b>. Beanstalk re-evaluates on the next operation and picks the cluster back up.</span></div>
</div>

Drift is recoverable, and the event names what changed, which is decent of it. What caught my attention is the shape of the rule.

## Same contract, two enforcers

Every Kubernetes platform I have built has the same unwritten rule: application teams do not `kubectl apply` into the cluster by hand. Our baseline makes it written and enforced. Deployments go through Argo CD, and every application syncs with self-heal and prune on:

```yaml
syncPolicy:
  automated:
    prune: true
    selfHeal: true
```

A manual edit gets reverted to whatever is in Git. The platform repairs the drift and carries on.

<div class="viz-label">two ways to enforce "don't touch"</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">GitOps platform</span><span class="vc-note">Manual edit is <em>reverted</em>. The platform owns the fix and keeps running. You find out from the sync history.</span><span class="vc-tag">repairs</span></div>
<div class="viz-card accent-err"><span class="vc-name">Beanstalk Cluster</span><span class="vc-note">Manual edit is <em>detected</em>. The platform stops maintaining the cluster and fails updates until you undo it.</span><span class="vc-tag">refuses</span></div>
</div>

These are different bets. Self-heal assumes the platform always knows the desired state and can put it back. Beanstalk assumes it cannot safely reason about a cluster someone else has modified, so it declines to own it. For a provider operating clusters inside many customer accounts, that is the defensible choice. Automatically reverting a change a customer made on purpose, inside the customer's own account, would be a worse surprise.

Both make the same point. A no-touch rule that is only a request in a wiki is a convention, and people route around conventions the first time something is on fire. Self-heal plus prune is what turns "we use Git" into a guarantee. Beanstalk's drift rule does the same job the other way round.

> A platform is a promise about what you're not allowed to touch. AWS just wrote theirs down.

## Where the launch post and the docs disagree

The launch blog lists "all-at-once, rolling, immutable, and traffic-splitting deployments with automatic rollback on failure." The architecture docs describe two strategies for Cluster environments, `RollingUpdate` (the default) and `Recreate`, which the console shows as all at once. Immutable deployments appear in the same table in the Beanstalk Standard column only. InfoQ caught the same mismatch in its coverage.

If you run a release process built on immutable deployments or weighted traffic shifting on Standard today, plan for the documented behaviour, not the launch post, until AWS reconciles the two.

## What it costs

Beanstalk itself adds no charge. You pay for what it creates, and some of that is easy to miss:

| Line item | What the pricing says |
|---|---|
| EKS cluster | $0.10 per cluster per hour in standard support |
| EKS Auto Mode fee | per instance, on top of EC2; example: $0.03672/hr on a c6a.2xlarge that costs $0.306/hr |
| Discounts | Savings Plans, Reserved Instances and Spot reduce the EC2 part only, never the Auto Mode fee |
| Load balancers | each load-balanced environment gets its own Application Load Balancer |
| Free Tier | not eligible |

That Auto Mode example works out to about 12% on top of on-demand compute, and the gap widens as your EC2 discount grows, because the fee does not shrink with it. AWS is upfront about the break-even: the launch post recommends staying on Beanstalk Standard for single applications, Windows and IIS, apps that cannot be containerised, and workloads under $500 a month. The savings come from many applications sharing nodes. One app on its own cluster is the expensive way to run it.

One question I could not answer from the docs. The Kubernetes version is fixed "for the life of the cluster," and EKS standard support for a version runs 14 months, after which the cluster fee goes from $0.10 to $0.60 an hour under extended support. The docs do not say what Beanstalk does when that window closes. I would want that answer before putting anything long-lived on it.

## What I would take from it

<div class="viz-label">three things worth stealing</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">enforce the contract</span><span class="fs-role">no-touch that repairs or refuses, not a wiki page</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">isolation at creation</span><span class="fs-role">decide the tenant boundary before the first app lands</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">show the price</span><span class="fs-role">what the platform costs per app, on the page</span></div>
</div>

The first is the one most internal platforms skip. The second is the one that hurts later: moving a tenant to its own cluster after the fact is a migration, on Beanstalk and on your own platform alike. The third is rare enough that AWS publishing a "don't use this under $500 a month" line deserves credit.

## Where lock-in starts

The workload is portable. It is a container image in ECR, and if Beanstalk built it from source, the Buildpacks output is still just an image. What does not travel is the configuration. Replicas, ports, rollout strategy and scaling triggers live in `aws:elasticbeanstalk:eks:*` option settings, not in Kubernetes manifests you could apply to another cluster. Paul Pollack from AWS told InfoQ that "you can take over management of your application's resources if you ever need to." That is the exit, and I would test it before depending on it.

For a team with a portfolio of stateless web services, no platform team, and no appetite for running Kubernetes, this is a reasonable deal with honest terms. For a team that already runs a GitOps platform on EKS, it is mostly a well-written spec of what they built.

---

Would you run production on a cluster you are not allowed to `kubectl` into? And if you already run a platform, how do you enforce "don't touch": revert, refuse, or ask nicely?
