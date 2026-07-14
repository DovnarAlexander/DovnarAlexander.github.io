---
title: "The half of your EKS bill nobody reads"
date: 2026-07-03
slug: eks-cross-az-cost
excerpt: "Everyone optimizing their EKS bill tunes compute and ignores the other half of the invoice: data transfer, hiding in a dozen tiny cross-AZ and NAT rows."
tags: [AWS, Kubernetes, FinOps, EKS, DevOps]
---

# The half of your EKS bill nobody reads

Karpenter v1.13.0 shipped on June 10, and my feed has been wall-to-wall EKS cost content ever since: consolidate your nodes, move stateless workloads to Spot, switch to Graviton, right-size everything. All of it is correct. All of it is about **compute**.

And compute is the right place to start. It's usually the biggest line on the bill and the one you have the most direct control over. But it's only half the invoice. The other half is data transfer, and it hides in plain sight: split across a dozen tiny rows nobody scrolls down to read. So it survives every cost review, quietly, for years.

This is the order I actually work a noisy EKS bill, and why the second half is the one that gets left on the table.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">Your EKS bill has two halves</h3><p class="ds-body">Everyone tunes <strong>compute</strong>. Almost nobody reads <strong>data transfer</strong>.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The quiet one</span><h3 class="ds-title">The chatter tax</h3><p class="ds-body">Two pods across AZs cost <code>$0.01/GB</code> — <em>each way</em>. Spread "for HA" pays it on every hop.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The rates</span><h3 class="ds-title">What each byte costs</h3><p class="ds-body">Cross-AZ <code>$0.01/GB</code> · NAT processing <code>$0.045/GB</code> · egress <code>~$0.09/GB</code>.</p></section>
<section class="deck-slide"><span class="ds-kicker">The order</span><h3 class="ds-title">Compute → cross-AZ → NAT</h3><p class="ds-body">Start with compute. Don't stop there.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Compute is the number you watch</h3><p class="ds-body">Data transfer is the number that watches <em>you</em>.</p></section>
</div>
</div>
</details>

## Half the invoice is compute. You already know that half.

Karpenter, Spot, and Graviton are genuinely the highest-leverage moves on most clusters, and I reach for them first:

- **Karpenter consolidation.** Bin-pack pods onto fewer, cheaper nodes and let idle capacity terminate. v1.13.0's changes are mostly operational (subnet-level IP tracking, configurable AMI/subnet refresh, custom IAM paths) rather than new cost levers, but the consolidation engine that makes Karpenter worth running has been there all along.
- **Spot for stateless.** Anything that tolerates interruption runs at a fraction of on-demand.
- **Graviton where the image is multi-arch.** ARM instances are cheaper per vCPU, and if your containers already build for `arm64`, the migration is mostly a node-pool change.

Do all of it. Then look at the number sitting one row down.

## The half nobody reads

Data transfer inside AWS isn't one charge. It's several small ones that only look small until you multiply them by "all your traffic, all the time."

> Compute is the number you watch. Data transfer is the number that watches you.

Here's what each byte actually costs on an EKS cluster in `us-east-1`:

| Line item | Rate | Where it comes from |
|---|---|---|
| Cross-AZ transfer | $0.01/GB **each direction** | pods, services, or storage talking across Availability Zones |
| NAT Gateway processing | $0.045/GB | any outbound byte routed through a NAT, on top of egress |
| Internet egress | ~$0.09/GB (first 10 TB) | traffic leaving AWS to the internet |

The trap is that these **compound**. A pod that pulls an image from the internet through a NAT Gateway in a different AZ can pay cross-AZ *and* NAT processing *and* egress on the same bytes.

### The chatter tax

The most common silent cost is intra-cluster traffic crossing AZ boundaries. You spread your workloads across three Availability Zones for resilience, which is a good instinct. But every time a pod in `us-east-1a` calls a service whose endpoint happens to land in `us-east-1b`, that round trip costs you $0.01/GB out and $0.01/GB back.

<div class="viz-label">what a single cross-AZ round trip costs</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">Pod in AZ-a</span><span class="fs-role">makes a call</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">crosses the AZ line</span><span class="fs-role">$0.01/GB out</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-err)"><span class="fs-probe">reply comes back</span><span class="fs-role">$0.01/GB back</span></div>
</div>

For a chatty microservice architecture (service mesh, sidecars, high-QPS internal APIs) this adds up to a real line on the bill. And most of it is invisible, because no single call is expensive. It's the aggregate that hurts.

## The order I actually work a bill

<div class="viz-label">first to last</div>
<div class="card-grid">
<div class="viz-card accent-cyan"><span class="vc-name">1 · Compute</span><span class="vc-note">Karpenter consolidation, Spot, Graviton. Biggest single lever — do it first.</span><span class="vc-tag">start here</span></div>
<div class="viz-card accent-warn"><span class="vc-name">2 · Cross-AZ</span><span class="vc-note">Measure intra-cluster traffic that crosses zones. Keep hot paths in-zone where safe.</span><span class="vc-tag">the quiet one</span></div>
<div class="viz-card accent-ok"><span class="vc-name">3 · NAT</span><span class="vc-note">Route S3/ECR/DynamoDB through VPC endpoints so image pulls and API calls skip the NAT meter.</span><span class="vc-tag">easy win</span></div>
</div>

The NAT step is often the fastest money you'll find. Gateway VPC endpoints for S3 and DynamoDB are free, and they take that traffic off the NAT Gateway entirely:

```hcl
# S3 traffic through a Gateway VPC endpoint:
# no NAT processing charge, no cross-AZ charge.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.us-east-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = aws_route_table.private[*].id
}
```

For ECR, interface endpoints do the same for image pulls. On a cluster that scales nodes up and down all day, that's a surprising amount of traffic to be paying NAT rates on.

## Where I've landed

A lot of the cross-AZ spread is there for "resilience" nobody actually measured. Sometimes the multi-AZ topology is load-bearing and the transfer cost is the price of staying up. Often it's a Helm chart default, a `topologySpreadConstraint` copied from a blog, and a bill nobody ever traced back to a specific decision.

I'm not arguing against multi-AZ. I'm arguing for **knowing what it costs you**, so it's a decision instead of an accident. Turn on cost allocation by AZ, look at the data-transfer line for one week, and see how much of it is workloads talking to themselves across a zone boundary they didn't need to cross.

Compute is where you start. It's just not where the bill ends.

---

When an EKS bill spikes, where do you look first: compute or the network? And what's the biggest data-transfer surprise you've traced back? I'll start: an internal service mesh spread across 3 AZs "for HA" that was paying cross-AZ on every single hop, all day, for traffic that never needed to leave the zone.
