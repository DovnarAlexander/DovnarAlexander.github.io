---
title: "EKS can roll back an upgrade now. Read the fine print before you trust it."
date: 2026-07-23
slug: eks-version-rollback
excerpt: "EKS can now revert a control-plane upgrade from N to N-1 within 7 days, but the kubelet skew rule means only a phased upgrade keeps that rollback within reach."
tags: [AWS, EKS, Kubernetes, DevOps, Platform Engineering]
---

# EKS can roll back an upgrade now. Read the fine print before you trust it.

For years the honest answer to "what's our EKS rollback plan?" was a shrug. A control-plane upgrade was one-way. If version N+1 broke a workload, your options were to fix forward under pressure or stand up a whole blue/green cluster and cut traffic over, at roughly double the running cost for the duration.

On July 1, 2026 AWS shipped Version Rollback, and the shrug goes away. You can now revert an EKS control plane from N to N-1 in place, within a 7-day window, at no extra charge. That's a genuinely good change.

It's also narrower than the word "rollback" makes it sound. The feature has a shape, and if your upgrade process doesn't already match that shape, the safety net isn't there when you reach for it. Here's the contract.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">Your EKS rollback is not an undo button</h3><p class="ds-body">Version Rollback shipped July 1. It reverts the control plane in place, N to N-1. What it doesn't touch is the part that bites.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">scope</span><h3 class="ds-title">What actually rolls back</h3><p class="ds-body">Control plane on <strong>every</strong> cluster. Data plane only on <strong>Auto Mode</strong>. On node groups you roll the nodes back by hand.</p></section>
<section class="deck-slide ds-err"><span class="ds-tag">the trap</span><h3 class="ds-title">The skew check seals the exit</h3><p class="ds-body"><code>kubelet</code> can't be newer than the control plane. Recycle your nodes to N+1 and a control-plane-only rollback is blocked.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">the fix</span><h3 class="ds-title">Upgrade in two steps, not one</h3><p class="ds-body">Control plane first. Bake for a week. Then the data plane. The rollback lives in that gap.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">IaC</span><h3 class="ds-title">The Terraform timeout bite</h3><p class="ds-body">Rollback gets 7 days by default; your apply times out at 24h. Set <code>--rollback-config timeoutMinutes</code> or a healthy rollback reads as failed.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">takeaway</span><h3 class="ds-title">It rewards the slow upgrade</h3><p class="ds-body">The phased path everyone skipped for years is now the one that keeps a rollback attached.</p></section>
</div>
</div>
</details>

## What actually rolls back

The word "rollback" quietly implies "the whole cluster goes back." It doesn't. Two different things are in play, and only one of them is fully automatic.

<div class="viz-label">two planes, two rules</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">Control plane</span><span class="vc-note">Reverts on <em>every</em> cluster, N to N-1, in place. This is the part AWS actually operates for you.</span><span class="vc-tag">automatic</span></div>
<div class="viz-card accent-err"><span class="vc-name">Data plane</span><span class="vc-note">Auto-reverts only on <em>EKS Auto Mode</em>. On managed node groups and self-managed nodes, you roll the nodes back yourself.</span><span class="vc-tag">your job</span></div>
</div>

On Auto Mode, EKS is smart about ordering: it rolls the worker nodes back first, then the control plane, and it respects your NodePool disruption budgets, PodDisruptionBudgets, and `karpenter.sh/do-not-disrupt` annotations while doing it. On everything else, the API reverts the control plane and hands you the nodes.

That split is the whole story, because of one Kubernetes rule that most upgrade runbooks never had to think about.

## The skew trap

Kubernetes enforces a version skew between the control plane and the kubelet on each node. A kubelet may run several minor versions *behind* the API server, but it must never run *ahead* of it. On EKS 1.28 and above that tolerated gap is three minor versions behind, zero ahead.

Now walk through a normal upgrade with that rule in mind.

<div class="viz-label">how the escape hatch closes</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">You upgrade the <b>control plane</b> to N+1. So far, fully reversible.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">You upgrade the <b>node group</b>. Nodes recycle and the kubelet comes up on N+1.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">You try a <b>control-plane-only rollback</b> to N. The kubelet is now newer than the control plane you're asking for.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">The <b>skew check refuses</b>. To roll the control plane back, you'd have to roll the nodes back too.</span></div>
</div>

This is why the rollback rewards a habit, not a button. If you upgrade the control plane and the data plane in the same maintenance window, by the time anything looks wrong the kubelet has already moved to N+1 and the control-plane rollback path is closed. The feature is still technically present; you've just made yourself ineligible for it.

## The upgrade that keeps its net

The way to actually keep the rollback available is the phased upgrade that Kubernetes documentation has quietly recommended for years and most teams compressed away to save a maintenance window.

<div class="viz-label">the contract</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">Control plane</span><span class="fs-role">upgrade to N+1</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">Bake ~7 days</span><span class="fs-role">rollback stays open</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">Data plane</span><span class="fs-role">recycle nodes</span></div>
</div>

Upgrade the control plane on its own. Let it run against your real workloads for a few days while the rollback window is open and every node is still on N. If a controller, an admission webhook, or a removed API version surfaces a problem, you revert the control plane and nothing on the data plane has moved. Only once you're confident do you recycle the nodes to N+1, and at that point you're committing on purpose.

Before it lets you revert, EKS runs a set of readiness checks and will flag anything that would make the older API server reject your running workloads.

<div class="viz-label">rollback readiness checks</div>
<div class="card-grid">
<div class="viz-card accent-cyan"><span class="vc-name">API compatibility</span><span class="vc-note">Are the API versions and fields your workloads use still valid under the N-1 schema?</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">Version skew</span><span class="vc-note">Would the rollback put the control plane behind a newer kubelet?</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">Add-on compatibility</span><span class="vc-note">Do your EKS add-on and kube-proxy versions support the target minor?</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">Cluster health</span><span class="vc-note">Is the cluster in a state where a rollback can safely complete?</span></div>
</div>

There's a `--force` flag that bypasses the readiness *insights* if you want to override a warning. Worth knowing what it does and doesn't do: it skips the advisory checks, but it does **not** override disruption budgets or pod-level disruption controls. Force is for "I've read the warning and I accept it," not for "make the impossible happen."

## The Terraform timeout bite

Here's the edge that will catch IaC users specifically, and it has nothing to do with Kubernetes.

By default, EKS gives a rollback operation up to 7 days to finish before it marks the operation as failed. That's a sane default for a human clicking through the console. It is a terrible default for a Terraform apply, which times out at 24 hours, or CloudFormation, which gives up at 36. Your IaC tool will declare a rollback failed and start unwinding while EKS is still happily rolling back.

The fix is a single field. Cap the rollback's own timeout under your IaC tool's timeout:

```bash
aws eks update-cluster-version \
  --name prod \
  --kubernetes-version 1.33 \
  --rollback-config timeoutMinutes=1440
```

`timeoutMinutes=1440` is 24 hours, which sits comfortably inside a default Terraform apply. Pick a number that fits whatever timeout your pipeline actually runs with, and the two systems stop fighting.

> The rollback rewards the upgrade you did in two steps, not the one you rushed into a single window.

## What this doesn't do

A few limits worth stating plainly, because "rollback" oversells all of them:

<div class="viz-label">the boundaries</div>
<div class="card-grid">
<div class="viz-card accent-warn"><span class="vc-name">One minor only</span><span class="vc-note">N to N-1. Multi-version rollbacks aren't supported. You can't unwind two upgrades at once.</span><span class="vc-tag">watch</span></div>
<div class="viz-card accent-warn"><span class="vc-name">7 days, then gone</span><span class="vc-note">Both the rollback and the readiness insights expire 7 days after the upgrade. Past that, it's blue/green again.</span><span class="vc-tag">watch</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Previous version must still be supported</span><span class="vc-note">You can only roll back to a version EKS still supports. Upgrading off an expiring release closes the door.</span><span class="vc-tag">watch</span></div>
</div>

None of this makes the feature less useful. It makes it a specific tool with a specific shape, and the shape happens to match good upgrade hygiene: go one minor at a time, separate the planes, don't sit on end-of-life versions.

## What I'd actually change

If your EKS upgrades already look like "bump the control plane and the node group in the same Terragrunt run, on a Saturday," this release is the nudge to split them. Not because the tooling forces you to, but because the rollback only exists in the space between the two steps.

Concretely, on the clusters I run this means: control plane upgrade as its own change, a bake period measured in days with real traffic on it, Karpenter disruption budgets kept tight so a data-plane recycle can't stampede, and a `--rollback-config` timeout that matches the pipeline instead of the default. The habit isn't new. What's new is that the habit now comes with a parachute, and rushing the upgrade is the one way to leave it on the ground.

I still reach for a careful, phased upgrade on production EKS. For the first time, being careful also means being able to undo.

*What's your current EKS rollback plan, honestly? Fix-forward, blue/green, or something you've never had to test? I'm curious how many teams have actually rehearsed the revert.*
