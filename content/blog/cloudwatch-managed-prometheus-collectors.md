---
title: "CloudWatch came for your collector"
date: 2026-08-04
slug: cloudwatch-managed-prometheus-collectors
excerpt: "CloudWatch now scrapes Prometheus metrics from EKS, ECS, EC2, MSK and OpenSearch with no collector of yours in the path. The operational win is real. The cost just moved onto three separate meters."
tags: [AWS, Observability, Kubernetes, FinOps, DevOps]
---

# CloudWatch came for your collector

There's a category of release I've learned to pay attention to: the one where a piece of infrastructure you were running stops being necessary. Terraform 1.11 did it when S3-native locking made the DynamoDB lock table optional. One less thing to provision, manage and pay for.

On 31 July AWS did it to the OpenTelemetry Collector.

CloudWatch now supports managed Prometheus collectors: scraping metrics from EKS, EC2, ECS, MSK and OpenSearch without you deploying or operating any agent. You provide a scrape configuration and a connection to your resources. AWS handles provisioning, scaling and collection.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The change</span><h3 class="ds-title">The middle box disappears</h3><p class="ds-body">No self-managed OTel Collector between your workload and CloudWatch.</p></section>
<section class="deck-slide"><span class="ds-kicker">Two launches</span><h3 class="ds-title">16 June, then 31 July</h3><p class="ds-body">Native OTLP ingestion and PromQL first. Managed collectors six weeks later.</p></section>
<section class="deck-slide"><span class="ds-kicker">Discovery</span><h3 class="ds-title">Per service, built in</h3><p class="ds-body">Kubernetes SD on EKS, Cloud Map DNS on ECS, direct scraping on EC2, open endpoints on MSK and OpenSearch.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">Labels</span><h3 class="ds-title">150 vs 30</h3><p class="ds-body">OTLP metrics carry up to 150 labels. Custom metrics cap at 30 dimensions.</p></section>
<section class="deck-slide"><span class="ds-kicker">Free context</span><h3 class="ds-title">Enrichment you didn't instrument</h3><p class="ds-body">Account, Region, cluster ARN, namespace and resource tags attached on ingest.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The catch</span><h3 class="ds-title">Three meters, not one box</h3><p class="ds-body">Collector per hour, ingest per GB, PromQL per million samples scanned.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">Watch</span><h3 class="ds-title">Dashboards become queries with a price</h3><p class="ds-body">A 30-second refresh used to hit hardware you'd already bought.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Check which meter it moved to</h3><p class="ds-body">Deleting a component is a real win. The cost rarely deletes itself.</p></section>
</div>
</div>
</details>

## Two launches that only make sense together

The collector announcement on its own reads like an operational convenience. The interesting part is what landed six weeks earlier.

On 16 June, CloudWatch started ingesting OpenTelemetry metrics natively, over OTLP, queryable with PromQL. Three details in that launch matter more than the headline:

<div class="viz-label">what the June launch actually changed</div>
<div class="card-grid">
<div class="viz-card accent-cyan"><span class="vc-name">150 labels</span><span class="vc-note">OTLP-ingested metrics support up to 150 labels, against the 30-dimension ceiling on CloudWatch custom metrics.</span><span class="vc-tag">cardinality</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">PromQL, not a new dialect</span><span class="vc-note">A Prometheus-compatible query API, usable from Query Studio, Managed Grafana or anything speaking PromQL over SigV4.</span><span class="vc-tag">queries</span></div>
<div class="viz-card accent-ok"><span class="vc-name">Automatic enrichment</span><span class="vc-note">Account ID, Region, cluster ARN, namespace and Resource Explorer tags attached to every metric with no instrumentation.</span><span class="vc-tag">context</span></div>
</div>

That 30-dimension ceiling is the reason so many teams run a split pipeline: CloudWatch for AWS vended metrics, a Prometheus-compatible backend for anything with Kubernetes labels on it. Lifting it to 150 removes the technical reason for the split.

Managed collectors then remove the last self-run component on the path.

<div class="viz-label">the path, before and after</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-err)"><span class="fs-probe">Before</span><span class="fs-role">workload → your collector → CloudWatch</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">You owned</span><span class="fs-role">sizing, upgrades, scaling, on-call</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">After</span><span class="fs-role">workload → CloudWatch</span></div>
</div>

## What the collector actually does for you

Discovery is per service, and it's the part that would otherwise be your YAML:

| Service | Target discovery |
|---|---|
| EKS | Kubernetes service discovery |
| ECS | DNS-based discovery via AWS Cloud Map |
| EC2 | direct instance scraping |
| MSK, OpenSearch | open monitoring endpoints |

Metrics arrive in OpenTelemetry format and are queryable with PromQL alongside AWS vended metrics. EKS, MSK and OpenSearch get automatic dashboards. Everything is available for CloudWatch alarms.

The enrichment is the quiet win. Because CloudWatch attaches AWS resource context on ingest, a query like this works without a single custom label in your instrumentation:

```promql
sum by (aws_account_id, k8s_namespace_name)
  (kube_pod_status_phase{phase="Running"})
```

The `aws_account_id` label is added by the enrichment layer. On a multi-account estate, that's the query you previously built an exporter and a relabel config to make possible.

> The collector wasn't hard. It was just always yours to keep alive.

## Now check the meter

Here's where I stop cheering.

Removing a component removes operational cost. It does not remove cost. It changes its shape, and the new shape has three separate meters:

| What | How it bills |
|---|---|
| Managed collector | per hour |
| OTLP metric ingestion | per GB, 15 months of storage included, no separate charge for API calls or unique series |
| PromQL queries | per million samples scanned |

The first two are predictable. The third is the one to model before you migrate, because it prices a behaviour that used to be free at the margin.

A self-hosted VictoriaMetrics box has a cost you already paid. Whether a dashboard on the office TV refreshes every 30 seconds or every 5 minutes changes nothing on the invoice. Under per-query pricing, that refresh interval, multiplied by every panel, every dashboard and every alert evaluation, is a line item. Not necessarily a large one. But it's a variable where you used to have a constant, and variables are what surprise people at the end of the month.

The other practical caveats: managed collectors are available in all Regions where the CloudWatch OTLP endpoint exists, except Asia Pacific (New Zealand). And OTLP ingestion itself is in all commercial Regions except Middle East (UAE), Middle East (Bahrain) and Israel (Tel Aviv). Check your Region list before you write the migration ticket.

## Where I've landed

My default for a metrics stack is still self-hosted VictoriaMetrics with Grafana, shipped as versioned charts and reconciled by ArgoCD on day one of a cluster. Two reasons, both boring: it's portable across clouds, and its cost is a shape I can predict a year out.

That's a default, not a religion. We reach for a cloud-native backend on purpose when compliance demands it, when the operational cost of self-hosting at volume exceeds the managed bill, or when a client's footprint is single-cloud and native integration beats portability they'll never use.

This launch moves that last case. On an AWS-only estate, "we run our own collector" was defensible mostly because the alternative meant a split pipeline and a 30-dimension ceiling. Both of those arguments just expired.

If you're multi-cloud, keep your collector. If you're all-in on AWS, the honest question is no longer whether the managed path works. It's whether you've modeled what your dashboards cost per query.

---

Are you running a self-managed collector on AWS today, and what would it take for you to delete it? And if anyone has real numbers on PromQL query billing at dashboard scale, I want to see them.
