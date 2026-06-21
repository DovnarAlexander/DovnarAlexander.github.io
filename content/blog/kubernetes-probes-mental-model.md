---
title: "Kubernetes probes are a mental model, not a checklist"
date: 2026-06-21
slug: kubernetes-probes-mental-model
excerpt: "What startup, readiness, and liveness each actually control — and why treating probes as three boxes to tick is how people take their own services down."
tags: [Kubernetes, DevOps, SRE, PlatformEngineering, CloudNative]
---

# Kubernetes probes are a mental model, not a checklist

Every few months "What job interviews taught me about Kubernetes" climbs the Hacker News front page again. It's a good read, and the section that always gets the most replies is the one on probes — because that's where the gap between "I can deploy a pod" and "I understand how Kubernetes keeps it alive" is widest.

I've sat on both sides of that interview. I've also cleaned up the production version of the same mistake. The pattern is identical: people treat `readinessProbe`, `livenessProbe`, and `startupProbe` as three boxes to tick, copy a snippet from a blog, and move on. Then Kubernetes does exactly what they told it to — and takes the service down on their behalf.

This post is the mental model I wish more people carried into both the interview and the cluster.

## The thing nobody says out loud: Kubernetes trusts you completely

Kubernetes does not know whether your application is healthy. It knows whether your *probe* says it's healthy. Those are not the same statement, and the entire failure surface lives in that gap.

If your probe is wrong, Kubernetes will enforce the wrong thing relentlessly. It has no "this looks like a misconfiguration" heuristic. A probe is an instruction, and Kubernetes follows instructions to the letter — even when following them destroys the workload.

So the first reframe: **a probe is not a health check you write for yourself. It's a command you hand to a control loop that will act on it without hesitation.**

## Three probes, three different contracts

The reason probes get confused is that all three "check if the app is okay." But what they *control* when they fail is completely different.

### Startup — "has the app initialized enough to be judged?"

The startup probe gates the other two. While it's running, liveness and readiness are suppressed. This is what protects slow-booting apps — Java Spring, .NET Core, anything that runs migrations on boot — from being killed before they ever finish starting.

If you've ever reached for a big `initialDelaySeconds` on a liveness probe to "give it time to start," you wanted a startup probe instead. `initialDelaySeconds` is a fixed guess; a startup probe is adaptive and stops as soon as the app is actually up.

### Readiness — "can it serve traffic right now?"

Readiness failure removes the pod from the Service endpoint list. **No restart.** Traffic stops flowing; the pod keeps running. When readiness passes again, traffic resumes.

This is the probe for *temporary* unavailability: cache still warming, a downstream dependency briefly slow, the pod under momentary load. You're telling Kubernetes "hold my requests for a second," not "I'm broken, recycle me."

### Liveness — "is it still functioning?"

Liveness failure restarts the container. It exists for one situation: the process is running but irreparably stuck — a deadlock, an infinite loop, a wedged event loop — and only a restart will recover it.

The cardinal rule follows directly: **a liveness probe must never depend on anything external.** If your liveness check hits the database and the database has a bad minute, Kubernetes will restart every replica of a perfectly healthy app. You converted a transient dependency blip into a self-inflicted, cluster-wide outage.

### The contract in one line

```
Startup → Readiness → Liveness
=
Initialize → Accept traffic → Stay healthy
```

- Startup controls *when* liveness becomes active.
- Readiness controls *traffic flow*.
- Liveness controls *restart behavior*.

Almost every probe incident I've seen comes from mixing those three responsibilities into one endpoint.

## The failure mode, concretely

Here's the classic. A liveness probe pointed at an endpoint that depends on a late-initializing or external resource:

```yaml
livenessProbe:
  httpGet:
    path: /health      # this handler also checks Postgres
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

Boot is slow, or Postgres hiccups. `/health` returns non-200. Kubernetes kills the container. It restarts, fails the same check, restarts again — and you're in `CrashLoopBackOff`. The app was never broken. The probe lied, and Kubernetes believed it.

## What a real readiness probe looks like

Readiness is the probe people get wrong most often, so it's worth being concrete. A good readiness probe is:

- **Lightweight.** No heavy DB scans, no expensive downstream calls. A probe that's too heavy becomes its own source of timeouts and makes the pod flap between `Ready` and `NotReady`.
- **Functional, not cosmetic.** Not just "return 200." Check the things that actually block serving: DB pool warmed, cache preloaded, migrations done, workers up.
- **Tolerant.** Use `failureThreshold` and `periodSeconds` so a one-off blip doesn't yank you out of rotation.

```yaml
readinessProbe:
  httpGet:
    path: /health/ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 3
```

Inside `/health/ready`, do quick checks of the dependencies that genuinely gate serving traffic, and return fast. Note the separate path from liveness — they answer different questions, so they get different endpoints.

## The interview answer, and the production answer

In an interview, the line that lands is: *liveness restarts, readiness reroutes, startup gates the other two.* That distinction alone tells the interviewer you understand operational reliability, not just `kubectl apply`.

In production, the same distinction is the difference between a graceful rollout and a 3 a.m. page. Get the separation right and you get zero-downtime deploys and services that ride out transient hiccups without anyone noticing. Get it wrong and Kubernetes will faithfully amplify your mistake across every replica.

If your liveness probe can fail because something *else* is down, it isn't a liveness probe — it's a blast radius.

---

What's the worst probe misconfiguration you've shipped — and what did it take down? Drop it below; I collect these. I'll start: a liveness probe on `/health` that pinged Postgres and turned a 90-second DB failover into a full cluster restart.
