---
title: "Karpenter 1.14 makes headroom an object, and the docs are wrong about it"
date: 2026-09-02
slug: karpenter-capacity-buffer
excerpt: "Karpenter 1.14 replaces the pause-pod headroom hack with a CapacityBuffer resource, but the concept page documents an API version the CRD does not serve and disagrees with it on how the buffer is sized."
tags: [Kubernetes, Karpenter, AWS, FinOps, PlatformEngineering]
---

# Karpenter 1.14 makes headroom an object, and the docs are wrong about it

For years, the way you kept spare capacity in a Kubernetes cluster was to lie to it. You deployed a pile of pods that did nothing, gave them a negative priority class so anything real could evict them, and sized the pile by hand until the start latency looked acceptable. Everyone called them balloon pods, or pause pods, or ballast. Everyone knew it was a hack. Everyone shipped it anyway, because the alternative was waiting for a node.

Karpenter 1.14 makes it a resource. That is the headline. The more useful part is the fine print, and in this case the fine print contradicts the documentation in two places.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The hack</span><h3 class="ds-title">Empty pods holding a seat</h3><p class="ds-body">A Deployment of pause containers on a negative priority class. Sized by hand, invisible to the NodePool.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">The object</span><h3 class="ds-title">CapacityBuffer</h3><p class="ds-body">Point it at a live workload with <code>scalableRef</code>, size it as a <code>percentage</code>, cap it with <code>limits</code>.</p></section>
<section class="deck-slide"><span class="ds-kicker">The seam</span><h3 class="ds-title">Consolidation had to learn</h3><p class="ds-body">Buffer nodes are excluded from empty consolidation. Drift, expiry and underutilized still run.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The catch</span><h3 class="ds-title">The docs say v1alpha1</h3><p class="ds-body">The shipped CRD serves <code>v1beta1</code> and nothing else. The documented example does not apply.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The second catch</span><h3 class="ds-title">Two different buffers</h3><p class="ds-body">Docs: <code>min(max(replicas, percentage), limits)</code>. CRD field doc: the minimum of the two.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">Caveats</span><h3 class="ds-title">Volumes and lag</h3><p class="ds-body">PVC and ephemeral volumes are stripped from virtual pods. Replica changes take up to 30 seconds.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Not insurance</h3><p class="ds-body">A buffer is a decision to pay for empty nodes in exchange for start time.</p></section>
</div>
</div>
</details>

## What the hack actually did

The mechanism is worth restating, because the new object inherits its physics.

<div class="viz-label">the balloon-pod cycle</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">ballast sits</span><span class="fs-role">empty pods occupy real nodes</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">real pod arrives</span><span class="fs-role">preempts the negative priority</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">starts immediately</span><span class="fs-role">ballast reschedules, pulls a node</span></div>
</div>

The workload never waits for EC2, because someone already paid for the node. That is the whole trick, and it is a good trick. The problems were all operational.

The pile had to be sized by hand, and re-sized whenever the workload it protected changed shape. It reported as utilization, so every dashboard overstated how busy the cluster was. And it lived entirely outside the NodePool that governed everything else about your capacity, which meant two systems with opinions about node count and no shared vocabulary.

## The object

`CapacityBuffer` is namespaced, and you describe the buffer either by a PodTemplate or by pointing at something that already exists.

```yaml
apiVersion: autoscaling.x-k8s.io/v1beta1
kind: CapacityBuffer
metadata:
  name: api-headroom
  namespace: default
spec:
  scalableRef:
    kind: Deployment
    name: api
  percentage: 20
  limits:
    cpu: "32"
```

That is the shape I reach for first, because it removes the sizing problem instead of moving it. The buffer is defined as a proportion of a workload that already scales, so when the workload grows the headroom grows with it and nobody has to remember.

The fields, and what each one is actually for:

| Field | Meaning |
|---|---|
| `podTemplateRef` | Shape of one buffer chunk, from a PodTemplate in the same namespace |
| `scalableRef` | A Deployment, StatefulSet or ReplicaSet whose pod template defines the chunk |
| `replicas` | A fixed number of chunks |
| `percentage` | Chunks as a percentage of `scalableRef` replicas, rounded up to at least 1 |
| `limits` | A resource ceiling that caps how many chunks get created |

`podTemplateRef` and `scalableRef` are mutually exclusive, and the CRD enforces it with a validation rule. There is a second rule worth knowing before you write a template-based buffer: if you set `podTemplateRef`, you must also set `replicas` or `limits`, or the object is rejected.

## The consolidation seam

This is the part that tells you the feature was designed rather than bolted on, and it is the first question any Karpenter operator should ask. Buffer pods are virtual. They are not real pods. So what stops Karpenter from noticing an empty node and consolidating away the exact capacity you asked it to reserve?

<div class="viz-label">what each disruption reason does to a buffer node</div>
<div class="card-grid">
<div class="viz-card accent-err"><span class="vc-name">Empty consolidation</span><span class="vc-note">Blocked. The node is marked unconsolidatable with the reason <em>Node has buffer pods</em>.</span><span class="vc-tag">had to be</span></div>
<div class="viz-card accent-ok"><span class="vc-name">Underutilized</span><span class="vc-note">Runs normally. The replacement node has to fit the virtual pods.</span><span class="vc-tag">still works</span></div>
<div class="viz-card accent-ok"><span class="vc-name">Drift and expiry</span><span class="vc-note">Run normally. Your node hygiene is unaffected by holding a buffer.</span><span class="vc-tag">still works</span></div>
</div>

Without the first rule the feature would eat itself: reserve capacity, Karpenter sees nodes with no real pods, Karpenter deletes them. With it, the buffer survives while the rest of the disruption machinery keeps working, which is the correct trade.

## Where the docs and the CRD disagree

Now the part worth checking before you write any YAML.

The concept page on karpenter.sh documents the API as `autoscaling.x-k8s.io/v1alpha1`. The CRD in `kubernetes-sigs/karpenter` serves exactly one version, and it is not that one:

```bash
$ kubectl get crd capacitybuffers.autoscaling.x-k8s.io \
    -o jsonpath='{.spec.versions[*].name}'
v1beta1
```

The upstream bump to `v1beta1` merged on 9 July 2026, two days before the provider's 1.14.0 release. The docs page has not followed. Copy the documented manifest onto a 1.14 cluster and you get `no matches for kind "CapacityBuffer" in version "autoscaling.x-k8s.io/v1alpha1"`, which is a confusing error to receive from a feature you just installed.

The second disagreement is subtler and matters more, because it changes the size of your bill.

<div class="viz-label">the same two fields, two answers</div>
<div class="card-grid">
<div class="viz-card accent-warn"><span class="vc-name">The concept page</span><span class="vc-note">Chunk count is <code>min(max(replicas, percentage), limits)</code>. The <strong>larger</strong> of the two, then capped.</span><span class="vc-tag">docs</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">The CRD field doc</span><span class="vc-note">"If both are set, the <strong>minimum</strong> of the two will be used."</span><span class="vc-tag">shipped</span></div>
</div>

Set `replicas: 10` and `percentage: 20` against a 100-replica Deployment and one reading gives you 20 chunks of headroom while the other gives you 10. That is a factor of two on capacity you are paying for and not using.

I have not run the controller against both readings to see which one wins in practice, so I am not going to tell you which is right. I am going to tell you to check on your own cluster before you size anything:

```bash
kubectl explain capacitybuffer.spec.replicas
kubectl explain capacitybuffer.spec.percentage
```

`kubectl explain` reads the schema the API server is actually serving. It cannot be out of date the way a website can.

> The cluster ships the contract. The docs only describe it.

## The rest of the second half

Three more things live in the caveats, and all three are the kind you discover at the worst time.

<ul class="checklist">
<li>PVC-backed and ephemeral volumes in the pod template are stripped from the virtual pods. A buffer for a workload whose scheduling depends on volume topology is not reserving what you think it is.</li>
<li>The buffer controller requeues every 30 seconds, so a replica change on the tracked Deployment takes up to half a minute to reach the buffer. Fine for capacity planning, not fine as a reaction to a traffic spike.</li>
<li>Buffer pods are still subject to NodePool limits. Exhaust the CPU or memory ceiling on the NodePool and the buffer simply is not fulfilled, quietly, because there is nothing to fail.</li>
</ul>

That last one deserves an alert rather than a comment in a values file. A buffer that silently is not there is worse than no buffer, because the whole point was that you stopped thinking about start latency.

## Is it worth it

The honest framing has not changed since the balloon-pod era, and the new object does not soften it.

Reserved headroom is not a safety feature you enable. It is nodes you rent and deliberately leave empty, so that the next pod does not wait for EC2. The bill arrives whether the spike comes or not. What Karpenter 1.14 changes is that the decision is now written down in the same place as the rest of your capacity policy, sized against a real workload instead of a guess, and visible to the controller that manages your nodes rather than hidden in a Deployment nobody remembers owning.

That is a real improvement, and it is one less piece of infrastructure to babysit. It is not a discount.

A buffer is not insurance. It is a decision to pay for empty nodes in exchange for start time. Make it on purpose.

---

Running balloon pods today? I would genuinely like to know what number you landed on and how you picked it, because that figure is usually inherited rather than chosen. Come argue with me on [LinkedIn](https://www.linkedin.com/in/dovnaralex).
