---
title: "HPA scale-to-zero shipped. The CPU limit is the interesting part"
date: 2026-08-27
slug: hpa-scale-to-zero
excerpt: "Kubernetes 1.37 lets an HPA hold a workload at zero pods, but only on object and external metrics, and the reason why decides which of your workloads it is actually for."
tags: [Kubernetes, KEDA, FinOps, PlatformEngineering, DevOps]
---


# HPA scale-to-zero shipped. The CPU limit is the interesting part

Kubernetes 1.37 landed on 26 August, and one line in the release notes will change a few Helm charts: `HorizontalPodAutoscaler` scale-to-zero graduated to beta and is enabled by default. Set `spec.minReplicas: 0` and an idle workload can hold at zero pods.

The feature was first introduced in v1.16. It reached a default seven years later, and the reason for the delay is the same reason it still won't work on CPU. That constraint is not a limitation somebody forgot to lift. It is the whole shape of the problem, and it decides which of your workloads this is actually for.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">What shipped</span><h3 class="ds-title">Your HPA can hold zero pods now</h3><p class="ds-body">Kubernetes 1.37, beta, on by default. <code>spec.minReplicas: 0</code> and an idle workload costs nothing.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The dead end</span><h3 class="ds-title">CPU can never get there</h3><p class="ds-body">CPU and memory are scraped off running pods. Zero pods, zero samples, nothing left to scale on.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">the rule</span><h3 class="ds-title">Object and external metrics only</h3><p class="ds-body">Not a policy decision. It is simply where the number comes from: outside the pods, or inside them.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">candidates</span><h3 class="ds-title">Queues, batches, GPUs</h3><p class="ds-body">Work that arrives as a countable backlog. Not the frontend, where the metric dies with the traffic.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">the detail</span><h3 class="ds-title">ScaledToZero: True</h3><p class="ds-body">Tells you the autoscaler parked it, not that a human typed <code>replicas: 0</code> during an incident. Those used to look identical.</p></section>
<section class="deck-slide"><span class="ds-kicker">The honest boundary</span><h3 class="ds-title">KEDA does not retire</h3><p class="ds-body">Dozens of scalers out of the box, and the metric still has to arrive through the custom or external metrics API. The adapter stays.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">but</span><h3 class="ds-title">One job is now built in</h3><p class="ds-body">If KEDA runs in your cluster purely to zero out on queue depth, that is native behaviour in 1.37.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">Remember this</span><h3 class="ds-title">Scale-to-zero was never the hard part</h3><p class="ds-body">Getting a metric out of a workload that isn't running is.</p></section>
</div>
</div>
</details>

## Why CPU can't get there

An HPA that scales on CPU reads `metrics.k8s.io`, which is fed by samples taken from running pods. That API graduated to stable in this same release, after nearly nine years in beta.

Follow the arithmetic to its end. The last pod terminates. The sample stream stops. The HPA now has no observation to compare against a target, so there is no signal that could ever tell it to come back. The workload sits at zero forever, and it isn't the autoscaler's fault: you asked it to steer using a gauge that only exists while the engine is running.

<div class="viz-label">how a CPU-driven scale-to-zero would strand itself</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">Demand drops. The HPA scales the workload <b>down to its last pod</b>.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">That pod terminates. <b>The sample stream stops.</b></span></div>
<div class="tl-step tl-warn"><span class="tl-text">The HPA has <b>no observed value</b> to compare against its target.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">Nothing can ever raise the metric again, because raising it requires a pod.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">The workload is <b>stranded at zero</b>. Not a bug. A closed loop with no input.</span></div>
</div>

So the supported set follows directly from where the number lives:

| Metric type | Can reach zero | Where the value comes from |
|---|---|---|
| `Resource` (cpu, memory) | No | sampled from live pods |
| `Object` | Yes | read off a Kubernetes object |
| `External` | Yes | read off a queue, a broker, a bill |

Object and external metrics survive an empty deployment because they were never measuring the deployment. They were measuring the work waiting for it.

## Which workloads this is actually for

The release notes name three: queue consumers, batch jobs, GPU workloads. That list is tighter than it looks, and it is worth saying why rather than just repeating it.

Each of those has a backlog you can count from outside. SQS message count. Kafka consumer lag. Pending rows in a jobs table. The number exists whether or not anything is running, which is exactly the property scale-to-zero requires.

<div class="viz-label">two shapes of demand</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">Countable backlog</span><span class="vc-note">Queue depth, consumer lag, pending jobs. The number is <em>outside</em> the workload and survives zero replicas.</span><span class="vc-tag">scale to zero</span></div>
<div class="viz-card accent-err"><span class="vc-name">Arriving traffic</span><span class="vc-note">HTTP requests hitting a service. With zero pods there is nothing to receive the request that would prove demand exists.</span><span class="vc-tag">keep a floor</span></div>
</div>

A web frontend is the counter-example that makes the rule obvious. Requests do not queue up somewhere visible waiting for a pod to appear; they arrive at a service that has no endpoints and fail. Scale-to-zero there needs something in front holding the connection open, which is a different piece of infrastructure and a different conversation.

The GPU case deserves its own note, because that is where the money is. A GPU node that idles overnight bills like a GPU node that works overnight. If the trigger for that work is a queue rather than a request, this feature is aimed squarely at your invoice.

## The status condition nobody will put in a headline

Here is my favourite part of the change, and it is not the scaling.

While the HPA is holding a workload at zero, it records a condition in its status:

```yaml
status:
  conditions:
  - type: ScaledToZero
    status: "True"
```

Once the workload scales back up, that flips to `False` with reason `NotScaledToZero`.

Before this, a Deployment sitting at zero replicas had exactly one appearance in the API regardless of how it got there. The autoscaler deliberately parking an idle consumer and a human typing `kubectl scale --replicas=0` during an incident produced identical manifests.

That difference matters at 3 a.m. more than it matters at any other hour. "Will this come back on its own?" is the entire question, and until 1.37 the honest answer was to go read Slack history and hope somebody wrote it down.

> A workload at zero used to be a state. Now it's a state plus a reason, and the reason is the part on-call actually needs.

## Does this retire KEDA?

No, and I want to be careful here because the tempting version of this post is the one that says it does.

Our default stack puts KEDA at the event-driven layer for a reason: dozens of scalers out of the box, covering brokers and cloud services we would otherwise be writing glue for. None of that moves into core Kubernetes with this release.

More to the point, the metric still has to reach the HPA through the custom or external metrics API. Something has to publish it. Whether that is Prometheus Adapter, KEDA's own metrics API server, or something you maintain, the adapter does not disappear because `minReplicas` learned a new value.

<div class="viz-label">what actually changes</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">Genuinely simpler</span><span class="vc-note">KEDA installed for exactly one job, zeroing out on queue depth. That behaviour is now native.</span><span class="vc-tag">one less thing</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Unchanged</span><span class="vc-note">You still need an adapter to publish the metric, and KEDA's scaler catalogue still has no equivalent in core.</span><span class="vc-tag">keep it</span></div>
</div>

There is one operational rule that survives untouched and is worth repeating because it bites people: when KEDA scales a target, it manages the underlying HPA itself. Do not hand-write a second HPA against the same workload. Two controllers steering one replica count is a fight, not a configuration.

And a cost note from the same drawer: VPA and HPA on the same CPU or memory metric oscillate. VPA shrinks requests, the utilisation ratio spikes, HPA adds pods, and the loop thrashes. VPA alongside an HPA on a custom or external metric is fine, which happens to be the exact combination scale-to-zero requires anyway.

## Before you set it

A short pre-flight, in the order I would actually run it:

<ul class="checklist">
<li>Confirm the metric your HPA targets is <code>Object</code> or <code>External</code>, not <code>Resource</code></li>
<li>Confirm something publishes that metric when zero pods are running, and test it with the workload scaled down by hand</li>
<li>Measure the cold start, then check it against the SLO the workload actually carries</li>
<li>Check whether KEDA is already doing this job, and what else it is doing before you remove it</li>
<li>Alert on <code>ScaledToZero</code> staying <code>True</code> longer than the work pattern explains</li>
</ul>

The third item is the one that gets skipped. Reliability wins ties: a cold start you have not measured is a latency budget you have not spent yet. Queue consumers and batch jobs usually have room for it. Anything with a user waiting at the other end usually does not.

## The line worth keeping

Scale-to-zero has been available to Kubernetes users for years through KEDA, and it is a good sign that the pattern finally earned a default in core. But the seven-year wait was never about the scaling.

Getting to zero is easy. Knowing when to come back is the problem, and you cannot answer it with a gauge that only exists while something is running.

---

If you run KEDA today, the interesting question is not whether 1.37 replaces it. It's what your install is doing beyond scale-to-zero on a queue. For some clusters that list is long. For a few, it is empty, and that's a piece of infrastructure you get to delete. Which one is yours?
