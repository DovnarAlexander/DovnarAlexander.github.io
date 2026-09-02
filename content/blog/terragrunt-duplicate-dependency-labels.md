---
title: "Terragrunt read one of your two dependency blocks and said nothing"
date: 2026-09-02
slug: terragrunt-duplicate-dependency-labels
excerpt: "Two dependency blocks sharing a label resolved silently to the last one for years; Terragrunt 1.1.4 adds a strict control that turns the shadowing into an error you can enforce in CI."
tags: [Terragrunt, Terraform, IaC, DevOps, PlatformEngineering]
---

# Terragrunt read one of your two dependency blocks and said nothing

There is a category of bug that does not crash, does not warn, and passes review. The tool reads your configuration, understands it differently than you do, and proceeds confidently. You find out weeks later, when something is running somewhere it should not be.

Terragrunt shipped one of those for years. Two `dependency` blocks with the same label parsed without complaint, and every reference to that label quietly resolved to whichever block happened to come last. Version 1.1.4, released on 27 August 2026, finally makes it say something.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide ds-err"><span class="ds-kicker">The config</span><h3 class="ds-title">Two regions declared, one read</h3><p class="ds-body">Two <code>dependency "vpc"</code> blocks. Every reference resolves to the last one.</p></section>
<section class="deck-slide"><span class="ds-kicker">The silence</span><h3 class="ds-title">Nothing anywhere</h3><p class="ds-body">Nothing on parse, nothing in plan, nothing in apply. The first block simply vanishes.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The class</span><h3 class="ds-title">Understood you differently</h3><p class="ds-body">Same shape as a plan that replaces prod because a resource address changed, not the resource.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">The fix</span><h3 class="ds-title">A strict control</h3><p class="ds-body">Warning by default in 1.1.4. An error with <code>--strict-control duplicate-dependency-labels</code>.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">The move</span><h3 class="ds-title">Put it in CI now</h3><p class="ds-body">Terragrunt's own guidance: run strict controls in non-prod so breakage surfaces before it is the default.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Loud versus quiet</h3><p class="ds-body">A crash tells you where it broke. A silent misread lets you ship it.</p></section>
</div>
</div>
</details>

## The configuration

Here is the whole bug. It fits on a screen, which is part of why it survived so long.

```hcl
dependency "vpc" {
  config_path = "../vpc-us-east-1"
}

dependency "vpc" {
  config_path = "../vpc-us-west-2"
}

inputs = {
  # Reads ../vpc-us-west-2. Always did.
  vpc_id = dependency.vpc.outputs.vpc_id
}
```

Read that as a reviewer. Two regions are declared. The intent is obvious and the syntax is valid. Nothing about it suggests that one of those blocks is decorative.

What actually happened is that HCL let the second block shadow the first, Terragrunt kept the last one it parsed, and `dependency.vpc` meant `us-west-2` from then on. The `us-east-1` block still ran its dependency, still got planned, still showed up in the graph. Its outputs just never reached anything.

<div class="viz-label">how it plays out</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">Someone adds a <b>second region</b> by copying the dependency block and changing the path.</span></div>
<div class="tl-step"><span class="tl-text">The label is <b>not changed</b>, because the label looked like a type, not an identity.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">Terragrunt parses both, keeps the last, and says <b>nothing</b>.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">Plan is clean. Review passes. The config <b>reads correctly</b> to a human.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">A resource lands in <b>the wrong region</b>, and now you are reading HCL at an unpleasant hour.</span></div>
</div>

## Why this shape is the dangerous one

I have written before about the other end of this category. On a client migration, `terraform plan` wanted to replace a production database. Nobody had typed `destroy`. The module had been swapped, the resource address had changed, and Terraform tracks resources by address rather than by what they are, so a changed address reads as delete-then-create. [The plan was correct](https://alex-dovnar.in/blog/terragrunt-migration-state-mv/). It was also one `apply` away from taking the database with it.

Same shape as this one. The tool did exactly what it was told. What it was told was not what anyone meant.

<div class="viz-label">two kinds of wrong</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">Loud failure</span><span class="vc-note">A crash, a failed apply, a validation error. It stops, and it tells you where. Annoying, cheap.</span><span class="vc-tag">safe</span></div>
<div class="viz-card accent-err"><span class="vc-name">Silent misread</span><span class="vc-note">Valid syntax, confident execution, different meaning. It passes review because there is nothing to see.</span><span class="vc-tag">expensive</span></div>
</div>

Loud failures are a solved problem. Every pipeline in the world catches those. The ones that cost real money are the configurations that are wrong and legible at the same time.

## The fix

Terragrunt 1.1.4 warns when it finds duplicate labels. If you want it to stop, there is a strict control:

```bash
terragrunt run plan --strict-control duplicate-dependency-labels
```

```text
/path/to/terragrunt.hcl: dependency vpc is declared more than once; every dependency needs an address of its own
```

The error names the address the blocks are fighting over, which is the useful half. Fixing it is mechanical: give every block a label of its own. If a configuration was relying on the shadowing, deliberately or otherwise, keep only the block that was winning and delete the rest, because that is what was running.

## Put the flag in CI before you need it

Strict controls in Terragrunt are a staged deprecation mechanism. A behaviour becomes a warning, then an error under strict mode, then eventually the only behaviour. The documentation's own recommendation is to enable strict controls in non-production pipelines so incompatibilities surface early, while you still get to choose when to deal with them.

<ul class="checklist">
<li>Add <code>--strict-control duplicate-dependency-labels</code> to the non-prod plan job first, not to prod.</li>
<li>Run it once across every unit. If nothing fires, the flag costs you nothing and stays as a guard.</li>
<li>If it fires, treat each hit as an audit question rather than a rename: which block was actually running, and is that the one you wanted?</li>
<li>Only then promote the flag to the production pipeline.</li>
</ul>

The point of the middle step is that renaming the label changes behaviour. A duplicate that has been shadowing since 2024 means half your configuration has been dead code, and the moment you give both blocks real labels, the previously-ignored one wakes up and starts feeding real values into real resources. That is a change, and it deserves a plan you read carefully.

> A crash tells you where it broke. A silent misread lets you ship it.

## Also in 1.1.4

One smaller change in the same release, worth knowing if you scaffold from the command line. `terragrunt scaffold` used to write `# TODO` placeholders for every input and leave you to fill them in, while scaffolding the same component from the Catalog TUI opened a form and collected the values properly. Now the command opens that same form.

| Context | Behaviour |
|---|---|
| Interactive terminal | Opens the form, lists the source's variables or `values.*` references |
| `--non-interactive` | Placeholders, exactly as before |
| `stdin` is not a terminal | Placeholders, exactly as before |
| Source asks for nothing | Skipped |

The CI-safety design is the part I appreciate. A scaffold running inside a pipeline, or driven by another program, behaves exactly as it did. Nobody's automation breaks because an interactive nicety was added.

---

Go grep your Terragrunt repos for duplicate dependency labels before the flag does it for you. If you find one, I would like to hear how long it had been there. Find me on [LinkedIn](https://www.linkedin.com/in/dovnaralex).
