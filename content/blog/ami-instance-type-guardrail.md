---
title: "The node that boots, bills, and never joins"
date: 2026-09-09
slug: ami-instance-type-guardrail
excerpt: "Karpenter picks the instance type from one file and the AMI from another, and nothing checks that the two agree. EC2 now lets an AMI owner declare which instance types it supports, turning fifteen minutes of silence into a rejected launch."
tags: [Kubernetes, AWS, Karpenter, EKS, PlatformEngineering]
---

# The node that boots, bills, and never joins

My 90-second Kubernetes troubleshooting workflow starts with `kubectl get pods -o wide`. Status, then describe, then logs. It works because it assumes the pod is somewhere. It has no step for the case where the node never showed up at all.

That case is the one I keep coming back to, because it is the quietest. An EC2 instance starts, the meter starts with it, and nothing in the cluster reports a problem. There is no `CrashLoopBackOff` to grep for, and no event on a pod, because there is no pod. What you have is a `Pending` pod somewhere and an instance in the EC2 console that looks perfectly healthy from the outside.

On September 4, AWS shipped a small feature that closes one of the common ways this happens.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">The worst node failure isn't a crash</h3><p class="ds-body">It's an instance that boots, starts billing, and never joins the cluster.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The loop</span><h3 class="ds-title">Launch, boot, silence, terminate, repeat</h3><p class="ds-body">Karpenter waits <strong>15 minutes</strong> for registration, gives up, kills the instance, and launches another one.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">the gap</span><h3 class="ds-title">Two files, no handshake</h3><p class="ds-body">The <code>NodePool</code> picks the instance type. The <code>EC2NodeClass</code> picks the image. Karpenter matches architecture and nothing else.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">new</span><h3 class="ds-title">InstanceTypeSpecification</h3><p class="ds-body">Two lists on the AMI: <code>SupportedInstanceTypes</code> and <code>UnsupportedInstanceTypes</code>. Unset means everything, so nothing changes until you opt in.</p></section>
<section class="deck-slide"><span class="ds-kicker">One command</span><h3 class="ds-title">replace-image-instance-type-specification</h3><p class="ds-body">Wildcards work. <code>CopyImage</code> keeps the setting. Running instances are untouched.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The payoff</span><h3 class="ds-title">Silence becomes an error you can read</h3><p class="ds-body"><code>InvalidParameterCombination</code> at the API, in the second the launch happens, instead of 15 minutes of nothing.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The catch</span><h3 class="ds-title">Karpenter's fallback list has nine codes</h3><p class="ds-body">This one isn't among them. Don't expect the graceful retry you get for insufficient capacity.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Compatibility became a property of the image</h3><p class="ds-body">It used to be a comment in your <code>NodePool</code> that nobody enforced.</p></section>
</div>
</div>
</details>

## Where the gap actually is

Karpenter splits the decision across two objects, and that split is the whole story.

The `NodePool` describes what kind of capacity you will accept. Instance family, generation, architecture, capacity type, zone. It is a set of constraints, deliberately loose, because loose constraints are what let Karpenter find cheap capacity.

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: gpu
spec:
  template:
    spec:
      requirements:
        - key: karpenter.k8s.aws/instance-family
          operator: In
          values: ["g5", "g6"]
      nodeClassRef:
        group: karpenter.k8s.aws
        kind: EC2NodeClass
        name: gpu
```

The `EC2NodeClass` describes the machine image and the rest of the EC2-level configuration.

```yaml
apiVersion: karpenter.k8s.aws/v1
kind: EC2NodeClass
metadata:
  name: gpu
spec:
  amiSelectorTerms:
    - id: ami-1234567890abcdef0
```

Two objects, and usually two different files. Nothing validates that the image in the second one can actually run on the instance types allowed by the first one. This is not an oversight I am inferring; the Karpenter documentation states the limit directly. Karpenter works out which architecture a custom AMI is compatible with, and then:

> Unless using an alias, Karpenter cannot detect requirements other than architecture.

Architecture is the easy half. A `g5` instance and a plain AL2023 image are both `amd64`, so the arch check passes and Karpenter launches. The GPU driver that the workload needs is simply absent, and there is no field anywhere in which that fact is written down.

## How it fails, minute by minute

<div class="viz-label">the zombie loop</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">A <b>Pending</b> pod needs GPU capacity. Karpenter creates a NodeClaim and launches an instance.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">EC2 starts the instance. It is <b>Running</b>, it is healthy, and it is <b>billable</b>.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">The bootstrap does not complete. Nothing ever calls the API server. <b>No Node object appears.</b></span></div>
<div class="tl-step tl-crash"><span class="tl-text">Fifteen minutes pass. Karpenter's registration TTL expires, it deletes the NodeClaim and <b>terminates the instance</b>.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">The pod is still Pending, so Karpenter <b>launches another one</b>. Nothing was learned. Nothing was logged as an error.</span></div>
</div>

Fifteen minutes is not my number, it is the documented behaviour: if registration fails to succeed within that window, Karpenter removes the NodeClaim and deletes the underlying instance, creating another one if it is still needed. That is the correct design. A node that never registers is useless, and leaving it running would be worse. But it means the symptom you eventually notice is a pod that has been `Pending` for an hour, and the evidence keeps deleting itself every fifteen minutes.

The tell is in `kubectl get nodeclaims`, where the `Launched` condition is true and `Registered` is not. Karpenter's lifecycle has three stages, and knowing which one you are stuck at tells you where to look:

<div class="viz-label">where it stopped</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">Launched</span><span class="fs-role">EC2 accepted it</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">Registered</span><span class="fs-role">joined as a Node</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">Initialized</span><span class="fs-role">ready for pods</span></div>
</div>

Stuck between `Launched` and `Registered` means the instance exists and the cluster has never heard from it. From there you are reading EC2 console output, which is exactly the debugging experience everyone is trying to avoid.

## What EC2 shipped

The new attribute lives on the AMI and is called `InstanceTypeSpecification`. It holds two lists.

| Field | Effect |
|---|---|
| `SupportedInstanceTypes` | only these instance types may launch the AMI |
| `UnsupportedInstanceTypes` | every instance type except these may launch the AMI |

The evaluation rules are worth reading once, carefully, because "both lists set" is not the union you might assume:

<div class="viz-label">how EC2 evaluates it</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">Not set</span><span class="vc-note">Every instance type is allowed. This is the default, so nothing changes for AMIs you don't touch.</span><span class="vc-tag">default</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">Supported only</span><span class="vc-note">An allowlist. Only the listed types launch; everything else is blocked.</span><span class="vc-tag">allowlist</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Unsupported only</span><span class="vc-note">A denylist. Everything launches except the listed types.</span><span class="vc-tag">denylist</span></div>
<div class="viz-card accent-err"><span class="vc-name">Both</span><span class="vc-note">The type must be <em>in</em> Supported <strong>and</strong> <em>not in</em> Unsupported. Both conditions, not either.</span><span class="vc-tag">watch</span></div>
</div>

You set it with a single command:

```bash
aws ec2 replace-image-instance-type-specification \
  --image-id ami-1234567890abcdef0 \
  --instance-type-specification \
  '{"SupportedInstanceTypes": ["g5.*", "g6.*"]}'
```

Wildcards are supported in both lists. `t3.*` matches every size in the family, `*.12xlarge` matches that size across all families, `*xlarge` matches anything xlarge or larger. So the allowlist for a GPU image is two entries, not forty.

You can mix the two lists to carve out a hole: allow the families, then subtract the size that does not work.

```bash
aws ec2 replace-image-instance-type-specification \
  --image-id ami-1234567890abcdef0 \
  --instance-type-specification \
  '{"SupportedInstanceTypes": ["t3.*", "a2.*"], "UnsupportedInstanceTypes": ["t3.micro"]}'
```

Reading it back comes from `describe-images`, which now returns the field when it is set:

```json
{
    "InstanceTypeSpecification": {
        "SupportedInstanceTypes": [
            {"InstanceType": "t3.*"},
            {"InstanceType": "a2.*"}
        ],
        "UnsupportedInstanceTypes": [
            {"InstanceType": "t3.micro"}
        ]
    }
}
```

And a launch that violates it fails at the API, immediately:

```text
An error occurred (InvalidParameterCombination) when calling the
RunInstances operation: This AMI does not support the specified
instance type. Check DescribeImages for InstanceTypeSpecification,
and try again.
```

> A fifteen-minute silence became a one-line rejection. That is the entire value of this feature.

## The parts that will bite you

Four behaviours are worth knowing before you set this on anything shared.

**It replaces the whole specification.** The action is called `ReplaceImageInstanceTypeSpecification` for a reason. There is no "add one type" call. To change anything you send the complete updated specification, which means whatever automation you write has to read the current state first or it will silently drop entries.

**It only affects new launches.** Instances already running on a now-forbidden type keep running. This is good for safety and bad for your assumptions: setting the specification is not a way to find existing violations, only to prevent new ones.

**Launch templates and Auto Scaling groups can start failing.** Anything that references the AMI with a hardcoded instance type will break at its next scale-out, not at the moment you set the specification. On a shared AMI, that failure lands in someone else's account and someone else's on-call rotation. AWS recommends verifying compatibility before setting a specification on a shared AMI, and that is not boilerplate advice.

**`CopyImage` preserves it.** Copy an AMI to another region and the restriction comes with it. Usually what you want. Occasionally a surprise when the new region does not offer the instance families you allowlisted.

Only the AMI owner can set or change the attribute. It is available in all AWS Regions at no additional cost.

## The honest caveat, and it matters for Karpenter

Here is the part I would want to know before rolling this out on a cluster.

Karpenter maintains a set of EC2 error codes that mean "this instance type is temporarily unfulfillable, mark it unavailable and try a different one." That set has nine entries: `InsufficientInstanceCapacity`, `MaxSpotInstanceCountExceeded`, `VcpuLimitExceeded`, `UnfulfillableCapacity`, `Unsupported`, `InsufficientFreeAddressesInSubnet`, `MaxFleetCountExceeded`, `SpotMaxPriceTooLow`, and a reserved-capacity code.

`InvalidParameterCombination` is not one of them.

That does not make the feature useless, and I want to be precise about what it does and does not buy you. What you get for certain is a loud, immediate, greppable failure at launch time instead of a silent instance burning money for fifteen minutes. That alone is worth the change, because the failure moves from "invisible" to "in the logs."

What you should not assume is the second half: that Karpenter will treat the rejection as a signal, mark the type unavailable, and gracefully pick a compatible one. The fallback machinery keys off that error-code set, and this code is not in it. Verify the behaviour in your own cluster before you build a runbook that depends on it.

Which leads to the thing I would actually do. Set the specification on the image, because a guardrail that lives with the artifact travels everywhere the artifact goes, including into the launch templates and pipelines you forgot about. Then go fix the `NodePool` requirements so they never ask for an incompatible type in the first place. The AMI attribute is a backstop for the mistake. It is not a substitute for not making it.

## What to do this week

<ul class="checklist">
<li>List your custom and golden AMIs, and write down which instance families each one was actually built for</li>
<li>For every EC2NodeClass pinning a specific AMI, compare it against the instance families its NodePool allows</li>
<li>Set <code>SupportedInstanceTypes</code> with wildcards on the images where the answer is narrower than the NodePool</li>
<li>Check for launch templates and Auto Scaling groups referencing those AMIs before you set anything on a shared image</li>
<li>Alert on NodeClaims where <code>Launched</code> is true and <code>Registered</code> is not, because that gap is invisible from the pod side</li>
</ul>

That last one is the durable fix. The AMI attribute closes one specific cause of a node that never joins. Bad user data, a missing instance profile, a security group that cannot reach the API server, and a subnet with no route will all produce exactly the same fifteen minutes of nothing. The alert catches all of them.

---

What has produced a node-never-joined for you, and how long did it take to find? Mine hid behind a pinned AMI and an instance family that was wider than the image it pointed at.
