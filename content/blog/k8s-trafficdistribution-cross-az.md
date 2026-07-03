---
title: "One field in Kubernetes 1.34 vs your cross-AZ bill"
date: 2026-07-03
slug: k8s-trafficdistribution-cross-az
excerpt: "Kubernetes 1.34's traffic-distribution change reads as a networking refinement — it's also a one-field lever on the AWS cross-AZ data-transfer charge you're probably still paying."
tags: [Kubernetes, AWS, FinOps, PlatformEngineering, DevOps]
---

# One field in Kubernetes 1.34 vs your cross-AZ bill

Kubernetes 1.34 landed with the usual sweep of release-notes coverage, and the traffic-distribution change got filed where these always get filed: under "networking refinements." Lower latency, less bandwidth, same-node routing for DNS caches. All true.

It's also a FinOps lever, and almost nobody is reading it that way. Because on AWS, "keep traffic in the same zone" isn't just a latency win — it's money you stop handing to the cross-AZ data-transfer meter.

Here's the honest version of what changed, what didn't, and how to actually use it.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide ds-err"><span class="ds-kicker">The charge</span><h3 class="ds-title">Cross-AZ, every hop</h3><p class="ds-body">3 AZs "for HA" + default routing = <code>$0.01/GB</code> each way, all day.</p></section>
<section class="deck-slide"><span class="ds-kicker">The knob</span><h3 class="ds-title">One line on the Service</h3><p class="ds-body"><code>trafficDistribution: PreferSameZone</code>. kube-proxy used to spread blind to cost.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">Be honest</span><h3 class="ds-title">In-zone isn't new</h3><p class="ds-body"><code>PreferClose</code> is GA since 1.31. 1.34 adds a clearer name + <code>PreferSameNode</code>.</p></section>
<section class="deck-slide"><span class="ds-kicker">Safety</span><h3 class="ds-title">A preference, not a pin</h3><p class="ds-body">No local endpoint? Traffic falls back cross-zone. HA intact.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Stop paying to leave the zone</h3><p class="ds-body">It won't fix a bad topology — it stops the tax on traffic that never needed to cross.</p></section>
</div>
</div>
</details>

## The charge nobody put on the slide

Spread your workloads across three Availability Zones — the default advice for resilience — and you've also signed up for a running cost. Inside AWS, data crossing an AZ boundary costs **$0.01/GB in each direction**. A request from a pod in `us-east-1a` to a Service endpoint that happens to live in `us-east-1b` pays on the way out and on the way back.

> On AWS, "keep it in the same zone" is a latency optimization *and* a line-item on your bill.

For a chatty internal architecture — service mesh, sidecars, high-QPS internal APIs — that's not a rounding error. And historically, kube-proxy made it worse by design: it load-balanced a Service's traffic across *all* healthy endpoints equally, in every zone, with no awareness that some of those endpoints were on the expensive side of an AZ boundary.

## What 1.34 actually changed (and what it didn't)

This is where most write-ups overclaim, so let me be precise. Keeping traffic in-zone is **not** new. The `trafficDistribution` field with value `PreferClose` has been GA since Kubernetes 1.31. If you're on 1.31+ you could already ask for zone-local routing.

What KEP-3015 does in 1.34 (beta, and its feature gate is on by default) is two things: it gives `PreferClose` a clearer name, and it adds a sharper tool.

<div class="viz-label">the three values, honestly</div>
<div class="card-grid">
<div class="viz-card accent-warn"><span class="vc-name">PreferClose</span><span class="vc-note">GA since 1.31. Keep traffic in the caller's zone. Now <em>deprecated</em> in favor of the clearer name.</span><span class="vc-tag">old</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">PreferSameZone</span><span class="vc-note">Same semantics as PreferClose, unambiguous name. The one to reach for on zone-spread services.</span><span class="vc-tag">1.34</span></div>
<div class="viz-card accent-ok"><span class="vc-name">PreferSameNode</span><span class="vc-note">Prefer an endpoint on the <em>same node</em> as the caller. Zero cross-AZ and zero cross-node hop.</span><span class="vc-tag">1.34</span></div>
</div>

`PreferSameNode` is the genuinely new capability. It's built for workloads where a local replica exists on every node — a node-local DNS cache, a per-node sidecar, a DaemonSet-shaped service. In those cases you don't just avoid crossing zones; you don't leave the node at all.

## Using it

The change is a single field on the Service:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: internal-api
spec:
  selector:
    app: internal-api
  trafficDistribution: PreferSameZone   # or PreferSameNode
  ports:
    - port: 8080
```

That's the whole change. kube-proxy on each node now prefers endpoints in its own zone (or on its own node) and only reaches across when it has to.

### The safety net that makes it shippable

The reason you can set this without a 3 a.m. incident is that it's a **preference, not a pin**.

<div class="viz-label">how it degrades</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">Local endpoint healthy</span><span class="fs-role">stay in-zone → cut cost</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">Local endpoints gone</span><span class="fs-role">fall back cross-zone</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">Availability preserved</span><span class="fs-role">no dropped traffic</span></div>
</div>

If the zone-local endpoints are unhealthy or simply absent, traffic routes to another zone as it always did. You cut cost when there's a local option and keep availability when there isn't. That asymmetry is exactly what you want from a cost optimization: it never trades away uptime to save a dollar.

### Where it bites

Two honest caveats:

- **It only helps if endpoints are actually distributed.** If all replicas of a Service sit in one zone, `PreferSameZone` does nothing useful for callers elsewhere — and can create hotspots. Pair it with a sane spread of replicas.
- **`PreferSameNode` needs a replica per node to be worth it.** It shines for DaemonSet-style workloads and node-local caches; for a 3-replica Deployment on a 40-node cluster, most nodes have no local endpoint and you're back to zonal or cross-zonal routing.

## Where I've landed

This is a small feature with an unglamorous payoff, which is exactly why it's worth a second look. It won't rescue a badly spread architecture, and it isn't a substitute for measuring your data-transfer costs in the first place. But for the very common case — services spread across AZs for resilience, chatting all day, paying cross-AZ on traffic that had a perfectly good local endpoint — it turns a silent recurring charge into a one-line decision.

Read the 1.34 networking notes again with the invoice open next to them. The "refinement" everyone skimmed is a cost knob.

---

Are you setting `trafficDistribution` on your Services, or letting kube-proxy spread across zones by default? And has anyone actually put a number on their cross-AZ line? I'd love to hear real before/after figures — I collect these.
