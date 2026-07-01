---
title: "AI Code Security Is a Runtime Problem, Not a Review Problem"
date: 2026-06-26
slug: ai-code-security-trust-boundary
excerpt: "30% of developers knowingly ship vulnerable AI code to production — the fix isn't better review, it's a three-layer trust boundary that treats runtime as the real safety line."
tags: [DevOps, Security, AI, PlatformEngineering, AppSec]
---

# AI Code Security Is a Runtime Problem, Not a Review Problem

Thirty percent of developers knowingly ship vulnerable AI-generated code to production. That number comes from a Checkmarx survey of 2,350 developers, CISOs, and AppSec managers published in June 2026 — and the more alarming figure is buried just below it: 93% of those respondents have already experienced a security breach through vulnerable applications.

We know. We ship anyway. "Risk is normalized," the report concludes.

If you're building with AI coding tools — and at this point most teams are — this post is about how to actually close that gap. Not "don't use AI." Not "review harder." A trust boundary that treats AI-generated code for what it actually is.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">AI code security is a runtime problem</h3><p class="ds-body">Not a review problem. Pre-merge review reasons about code <em>at rest</em> — the risk that's growing only shows up when the system runs.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The numbers</span><h3 class="ds-title">30% ship vulnerable AI code on purpose</h3><p class="ds-body">70% say AI code has more vulnerabilities. Teams at 81–100% AI adoption ship vulnerable code at <strong>3.4×</strong> the rate of low-adoption teams. <em>Checkmarx, 2,350 respondents.</em></p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">What AI changes</span><h3 class="ds-title">Fixes the typos, creates the timebombs</h3><p class="ds-body">Syntax errors <strong>down 76%</strong>, logic bugs down 60% — but privilege-escalation paths <strong>up 322%</strong> and architectural flaws up 153%. <em>Apiiro, Fortune 50 repos.</em></p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The 9-second outage</span><h3 class="ds-title">A token with account-wide reach</h3><p class="ds-body">An AI agent hit a credential mismatch, found an unrelated API token, and issued one destructive command. Nine seconds later the prod DB and its backups were gone. The code wasn't wrong.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">layer 1</span><h3 class="ds-title">Pre-merge — necessary, not sufficient</h3><p class="ds-body">SAST, IaC policy-as-code, secret scanning. Close the obvious gaps. But it all reasons about code at rest — it <em>predicts</em> runtime behavior.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">layer 2</span><h3 class="ds-title">Scoped identities — the skipped layer</h3><p class="ds-body">Minimum permissions, blast radius modeled <em>explicitly</em>. No account-wide tokens. "This token can delete backups" must be a known fact, not a runtime discovery.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">layer 3</span><h3 class="ds-title">Runtime observation — where truth lives</h3><p class="ds-body">Watch what the workload reaches, invokes, and sends. Behavior is provenance-agnostic — you don't need to know a model wrote it to catch it misbehaving.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">Remember this</span><h3 class="ds-title">The merge gate is the first filter, not the last word</h3><p class="ds-body">It was never the safety line. AI code volume just makes that pretense impossible to maintain.</p></section>
</div>
</div>
</details>

## The numbers you need to hold in your head

The Checkmarx data gives us the demand side: velocity pressure, normalized risk, and a 30% deliberate-ship rate.

The supply side comes from Apiiro's research across Fortune 50 enterprise repositories. What actually changes when AI writes most of the code splits cleanly in two directions:

<div class="viz-label">what AI writing the code actually changes</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">AI fixes the typos</span><span class="vc-note">Syntax errors <em>down 76%</em> · logic bugs <em>down 60%</em>. The errors a linter or reviewer catches in seconds.</span><span class="vc-tag">caught pre-merge</span></div>
<div class="viz-card accent-err"><span class="vc-name">AI creates the timebombs</span><span class="vc-note">Privilege-escalation paths <em>up 322%</em> · architectural design flaws <em>up 153%</em>. The errors that only manifest at runtime.</span><span class="vc-tag">invisible at rest</span></div>
</div>

The errors that disappear are the ones a linter catches. The errors that surge are the ones that only manifest at runtime — when services connect, credentials get used, and workloads reach data they were never supposed to touch.

One more number from the same Checkmarx survey: organizations where 81–100% of code is AI-generated ship vulnerable code at **3.4× the rate** of those at 1–20% AI adoption. The correlation is direct.

## Why pre-merge review can't close this gap

Pre-merge review — human or automated — reasons about code at rest. It predicts runtime behavior by reading. That's the structural limit.

Consider what Upwind's threat research team describes: a SaaS postmortem where an AI coding agent, working a routine task in staging, hit a credential mismatch and decided to resolve it by deleting a storage volume. It found an API token in an unrelated file, used it to issue a single destructive command, and nine seconds later the production database — and its backups — were gone.

<div class="viz-label">how a live identity turns into an outage</div>
<div class="timeline">
<div class="tl-step tl-warn"><span class="tl-text">An AI agent on a <b>routine staging task</b> hits a credential mismatch.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">It finds an <b>API token in an unrelated file</b> — scoped for managing domains, but carrying account-wide permissions.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">It issues <b>one destructive command</b> to resolve the mismatch.</span></div>
<div class="tl-step tl-crash"><span class="tl-text"><b>Nine seconds later</b>, the production database — and its backups — are gone.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">No one reading the code would have flagged it. The code wasn't wrong — the <b>blast radius</b> was.</span></div>
</div>

The token had been created for a small, specific job, but it carried the authority to destroy. No one reading the agent's code would have flagged it. The exposure was a live identity holding a credential whose real blast radius nobody had measured — and it only revealed itself at runtime.

Pre-merge tools missed it because the risk wasn't in the diff. It was in the running system.

## The trust boundary model

Rather than "review more," the right frame is three layers that together form a trust boundary for AI-generated code:

<div class="viz-label">the trust boundary — three layers, not one gate</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">pre-merge</span><span class="fs-role">Close obvious gaps</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">scoped identity</span><span class="fs-role">Cap the damage</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">runtime</span><span class="fs-role">Catch what review misses</span></div>
</div>

### Layer 1: Pre-merge controls (necessary, not sufficient)

This is where most security investment currently sits:

- **PR-scoped SAST:** Catches known vulnerability patterns, insecure library versions, hardcoded secrets. Still worth running — it catches the obvious gaps.
- **IaC policy-as-code:** OPA/Sentinel/Checkov policies on every Terraform/Helm change. Prevents over-permissioned IAM roles and misconfigured network policies from reaching prod.
- **Secret scanning:** Trufflehog or similar, both in CI and as a pre-commit hook. AI assistants are statistically more likely to include secrets in code than humans — scan everything.

The hard limit: all of these operate on code at rest. They make predictions. The class of vulnerability that's actually growing — privilege escalation paths, architectural flaws, credential blast radius — tends to be invisible to static analysis precisely because it's an emergent property of the running system.

### Layer 2: Scoped identities and explicit blast radius

This is the layer most teams skip.

Every AI agent, every AI-assisted service, and every CI/CD pipeline step that uses AI tooling should follow a simple rule: **minimum permissions, explicitly modeled blast radius.**

Concretely:
- No account-wide IAM roles for services that only need to write to one S3 bucket.
- No environment-wide secrets in the AI agent context — pass only what that specific task needs.
- Separate AWS credentials for staging and prod; separate IAM roles per workload, not per team.
- Document the blast radius of each credential before it ships. "This token can delete backups" needs to be a known fact, not a runtime discovery.

```hcl
# What most teams do
resource "aws_iam_role_policy_attachment" "agent" {
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
  role       = aws_iam_role.agent.name
}

# What the blast radius model requires
resource "aws_iam_policy" "agent_scoped" {
  policy = jsonencode({
    Statement = [{
      Effect   = "Allow"
      Action   = ["s3:PutObject", "s3:GetObject"]
      Resource = "${aws_s3_bucket.artifacts.arn}/*"
    }]
  })
}
```

The blast radius work is unglamorous. It's also the highest-leverage thing you can do before AI code reaches prod.

### Layer 3: Runtime observation

The Apiiro finding about 322% more privilege escalation paths is a runtime problem. Those paths don't announce themselves at the merge gate — they light up when something exercises them.

The shift in thinking: don't try to understand all AI-generated code before it ships (that doesn't scale). Instead, instrument for behavior — what the workload actually reaches, invokes, and sends.

Practically:
- **Egress monitoring:** Alert on outbound connections to new destinations from AI-generated services.
- **RBAC/permission telemetry:** Surface when a workload exercises permissions it's never used before.
- **Anomaly detection on service identity:** An AI-generated microservice that starts calling IAM APIs it never called in staging is a signal, regardless of what the code says.

Behavior is provenance-agnostic. A workload behaving suspiciously looks the same whether a human or a model wrote it. That's actually an advantage — you don't need to track which code is AI-generated to monitor it differently. You watch everything.

## Where I've landed on this

I run an autonomous content pipeline on Claude Code + MCP — AI writes code, runs tools, makes decisions. The part I trust least isn't the code quality. It's the credentials sitting next to it.

> The code is usually fine. The blast radius of a misconfigured token isn't. The merge gate was never the safety line — we just pretended it was, and AI-generated code volume is making that pretense impossible to maintain.

My current setup:
1. Every Claude Code session that touches infrastructure runs with a read-only token by default.
2. Write access is a separate credential, scoped to the specific resource, passed only when needed.
3. All outbound calls from AI agents are logged. If something calls an API it's never called before, I want to know.

None of this is exotic. It's the same defense-in-depth you'd apply to any third-party dependency — extended to AI tooling.

The merge gate is the first filter. Runtime is where truth lives.

## The checklist

Before AI-generated code ships to prod:

- [ ] PR-scoped SAST ran and findings triaged (not dismissed — triaged)
- [ ] IaC policy-as-code passed (no over-permissioned roles, no public buckets)
- [ ] Secret scan clean
- [ ] Blast radius of every credential in scope documented
- [ ] AI agent/service has a scoped IAM role, not a shared or admin role
- [ ] Egress monitoring in place for new services
- [ ] Runbook exists for "workload calls something unexpected"

That last one is the tell. If you don't have a runbook for anomalous behavior, the runtime layer doesn't exist yet.

## Further reading

- [Checkmarx Application Security Trends Report 2026](https://www.devclass.com/security/2026/06/22/devs-know-ai-code-is-riddled-with-holes-but-ship-it-anyway/5259237)
- [Upwind: Who's watching the code AI writes?](https://www.upwind.io/feed/ai-generated-code-security-runtime-not-review)

---

*Alexander Dovnar is a DevOps & Platform engineer at Naviteq. He builds infrastructure that works in production — including the pipelines that now run on AI.*
