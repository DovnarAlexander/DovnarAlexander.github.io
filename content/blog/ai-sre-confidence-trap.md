---
title: "AI on-call is confident. That's exactly the problem."
date: 2026-07-23
slug: ai-sre-confidence-trap
excerpt: "AI advice made people less accurate but more confident, collapsing their willingness to say 'I don't know' from 44% to 3%. On-call, that eroded doubt is the danger, and read-only, approval-gated assistants are how you keep it."
tags: [DevOps, SRE, AI, Observability, Incident Response]
---

# AI on-call is confident. That's exactly the problem.

There's a new wave of AI-SRE tools that sit next to your on-call rotation, read your live systems, and tell you what's wrong. Some of them are genuinely good. I run assistants like this against real clusters. The technology isn't the thing I want to argue about.

What I want to argue about is a number from a study that came out this month, because it describes the exact failure mode these tools walk you into if you let them.

Researchers gave people access to AI advice and measured what happened to their answers. Accuracy dropped by roughly three times. Confidence went up by roughly two. And the share of people willing to say "I don't know" collapsed from 44% to 3%. The researchers deliberately used questions where the model tends to be wrong, so the point isn't "the AI was bad." The point is that people got more certain while getting less right.

If you do incident response, that last number should stop you cold.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide ds-err"><span class="ds-kicker">the study</span><h3 class="ds-title">3× less accurate, 2× more confident</h3><p class="ds-body">And the share of people willing to say "I don't know" fell from 44% to 3%. Confidence rose while accuracy dropped.</p></section>
<section class="deck-slide"><span class="ds-kicker">the mechanism</span><h3 class="ds-title">Confidence is not calibration</h3><p class="ds-body">A correct root cause and a hallucinated one read identically: fluent, specific, both citing a metric. That's the whole danger.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">3am</span><h3 class="ds-title">The instinct AI removes</h3><p class="ds-body">"I'm not sure, let me check the dashboard" is the thought incident response runs on. AI is very good at deleting it.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">read-only</span><h3 class="ds-title">Diagnose, don't act</h3><p class="ds-body">It reads status, logs, metrics. It doesn't touch prod. Diagnosis is cheap to undo, a prod action isn't.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">approval</span><h3 class="ds-title">A human in the loop</h3><p class="ds-body">Every state-changing action is gated. Nothing auto-executes on production. The gate protects your doubt, not the model's.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">takeaway</span><h3 class="ds-title">Use AI on-call. Keep "I don't know."</h3><p class="ds-body">The guardrails aren't distrust of the model. They're the design that keeps a human in the loop the study shows AI erodes.</p></section>
</div>
</div>
</details>

## The number that matters isn't accuracy

Everyone focuses on accuracy, because accuracy is easy to argue about. Your AI-SRE tool got the root cause right, or it didn't. Fine. But every tool is wrong sometimes, and a team that's paying attention catches wrong answers.

The failure that doesn't get caught is a different one. It's when the tool is wrong *and* fluent, and it quietly convinces you to stop checking. That's what the 44% to 3% collapse describes. It isn't that people trusted a specific wrong answer. It's that the mere presence of AI advice suppressed the habit of noticing what they didn't know.

On-call is built on that habit. The whole discipline is a series of "I'm not sure yet" moments held open long enough to look at the evidence. Remove the "I'm not sure," and you've removed the part that works.

## Confidence is not calibration

Here's the thing a fluent summary hides: the words carry no signal about whether they're true.

<div class="viz-label">two paragraphs, one appearance</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">A correct root cause</span><span class="vc-note">Fluent. Specific. Names the failing service and cites the metric that moved.</span><span class="vc-tag">right</span></div>
<div class="viz-card accent-err"><span class="vc-name">A hallucinated root cause</span><span class="vc-note">Fluent. Specific. Names a failing service and cites a metric. Also wrong.</span><span class="vc-tag">wrong</span></div>
</div>

A model that's guessing writes with the same fluency as a model that's right. There's no tremor in the prose when it's making things up. Human experts leak uncertainty through hedges, pauses, and "let me double-check." A confident paragraph of generated text leaks nothing. You cannot read calibration off fluency, and that's precisely the read your tired 3am brain wants to make.

## The 3am cascade

The dangerous path isn't exotic. It's the most natural thing in the world when you're woken up by a pager.

<div class="viz-label">how a good tool leads to a bad call</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">The <b>alert fires</b>. You're half awake and want it to be over.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">The assistant hands you a <b>confident root cause</b>, cleanly written.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">It's plausible, so you <b>skip "let me check the dashboard."</b></span></div>
<div class="tl-step tl-crash"><span class="tl-text">You <b>act on a fluent guess</b>, and now you're debugging two problems.</span></div>
</div>

Notice that nothing in this chain requires the tool to be bad. A good tool that's right 80% of the time still produces this exact cascade on the other 20%, because the 20% arrives wearing the same confident voice as the 80%.

## What actually protects you

The guardrails I put around an on-call assistant have almost nothing to do with how much I trust the model. They exist to protect my own doubt, by making sure the model can inform a decision without quietly making it.

Three rules, in order:

<div class="viz-label">the contract</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">Read-only</span><span class="fs-role">status, logs, metrics</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">Approval gate</span><span class="fs-role">nothing auto-runs on prod</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">Cite sources</span><span class="fs-role">a link you can open</span></div>
</div>

Read-only by default means the assistant can read status, logs, and metrics, and nothing else. Diagnostics are safe because they're cheap to undo. Any state-changing action is a separate class of thing.

Approval-gated means every action that touches production stops at a human. The assistant proposes "restart this deployment" and waits. Nothing runs on prod without someone saying yes. That single gate is what converts a confident wrong answer from an outage into a rejected suggestion.

Made to cite means an answer without a source I can open is worth less than an answer with one. "Latency is up because the cache is cold, see this Grafana panel" is checkable. "Latency is up because the cache is cold" is a vibe. The citation is what lets me re-insert the doubt the study says I'll otherwise skip.

In practice that looks less like trusting a black box and more like giving it a narrow, typed set of read-only capabilities and routing everything else through a person:

```yaml
assistant:
  mode: read-only            # diagnostics only, no write-back
  capabilities:
    - kube:get               # pods, events, describe
    - logs:read
    - metrics:query          # Prometheus / CloudWatch, read
  actions:
    restart, scale, rollback, delete:
      requires: human-approval   # proposed, never auto-executed
      audit: true                # who asked, what ran
```

The new generation of read-only AI-SRE agents is built on exactly this shape: a tool-calling agent driving a typed allowlist of read-only capabilities, building a root-cause hypothesis from live evidence, and proposing classified fixes that a human approves. That constraint isn't the model being humble. Humility is a property the model doesn't have. It's the design supplying the doubt the study shows the human will stop supplying.

## What AI may do, and what it may only suggest

The line I draw is about how expensive the action is to undo. Reading is reversible. Restarting a production service at 3am, on a hunch, is not.

| Action | AI does it | Human approves |
|---|---|---|
| Read status, logs, metrics | yes | |
| Cluster a noisy alert storm into one incident | yes | |
| Propose a root-cause hypothesis with evidence | yes | |
| Restart, scale, or roll back a production workload | | yes |
| Change IAM, delete data, touch secrets | | yes |

> A confident wrong answer is only dangerous if it can reach production without passing a human. The gate is the whole point.

## Use it, don't outsource your doubt

I'm not anti-AI on-call. The triage speed is real: clustering an alert storm into one incident, pulling the three relevant log lines out of ten thousand, drafting a first hypothesis while you're still finding your glasses. That's a real time-saver, and I use it.

The mistake is letting the tool's confidence stand in for your own judgment, because the study is clear about the cost. You accept a wrong answer, sure. Worse, you lose the reflex to ask whether it's wrong at all. Read-only defaults, approval gates, and forced citations aren't friction bolted on out of paranoia. They're the mechanism that keeps you in the loop the AI would otherwise smooth you out of.

Use AI on-call. Just don't let it talk you out of "I don't know."

*What does your team let an AI actually do during an incident, versus only suggest? I'm curious where people are drawing the read-only line right now.*
