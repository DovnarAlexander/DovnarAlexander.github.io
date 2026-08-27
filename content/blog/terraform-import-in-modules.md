---
title: "Terraform 1.16 let import into modules. Read the review thread before you celebrate"
date: 2026-08-27
slug: terraform-import-in-modules
excerpt: "Terraform 1.16 allows import blocks inside modules, which fixes brownfield adoption and quietly moves review burden into every module version bump you approve."
tags: [Terraform, IaC, DevOps, PlatformEngineering, Cloud]
---


# Terraform 1.16 let import into modules. Read the review thread before you celebrate

Terraform 1.16 went GA on 26 August. The changelog line I had been waiting for is six words long:

> import: `import` blocks inside modules are now supported. (#38352)

For anyone dragging brownfield infrastructure under IaC, that is the headline of the release. It also quietly moves a piece of trust from the root module into your dependency tree, and the engineer who wrote the pull request said so in the review thread before anyone else got the chance.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">What shipped</span><h3 class="ds-title">import blocks work inside modules</h3><p class="ds-body">Terraform 1.16, GA on 26 August. The check that blocked it, <code>#38352</code>, is deleted.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The old wall</span><h3 class="ds-title">"Import blocks are only allowed in the root module"</h3><p class="ds-body">Your resources live in modules. The import block lived in root. So you wrote the full address from root, or went imperative.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">Why I care</span><h3 class="ds-title">A plan that wanted to replace a production database</h3><p class="ds-body">Swapping one RDS module for another changed the address in state. <code>terraform state mv</code> saved it.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">now</span><h3 class="ds-title">The module carries its own import</h3><p class="ds-body">Brownfield adoption stops being a root-module chore, and the diff stays reviewable.</p></section>
<section class="deck-slide ds-err"><span class="ds-tag">the catch</span><h3 class="ds-title">A parent's import silently overrides the child's</h3><p class="ds-body">Two imports in one module is a loud error. Parent versus child is a quiet win for the parent. No plan line mentions it.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">From the review thread</span><h3 class="ds-title">"I don't want imports I didn't write"</h3><p class="ds-body">The PR author asked for a root-level switch to block nested-module imports, as a security stance. It didn't ship.</p></section>
<section class="deck-slide"><span class="ds-tag">also in 1.16</span><h3 class="ds-title">mermaid graphs, store, console scope</h3><p class="ds-body"><code>graph -format=mermaid</code>, <code>store</code> on <code>terraform_data</code>, <code>console -scope=</code>, <code>-json</code> on <code>state show</code>.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">Remember this</span><h3 class="ds-title">An import you review is a feature. An import you inherit is a supply chain.</h3><p class="ds-body">Pin your module versions. You were already supposed to.</p></section>
</div>
</div>
</details>

## The wall, and why it was in the way

Config-driven import gave us something the imperative `terraform import` command never could: a plan you can read before you run it. You declare intent in HCL, the diff shows up in the pull request, a reviewer sees what is about to be adopted into state.

The catch was scope. Until 1.16, the parser rejected any `import` block outside the root:

```text
An import block was detected in "module.rds".
Import blocks are only allowed in the root module.
```

Real infrastructure does not live in the root module. In roughly 95% of production projects we compose stacks out of versioned units, which means practically every resource sits behind at least one module boundary. So adopting an existing resource left two options, and both were worse than they should have been.

<div class="viz-label">the two bad options, before 1.16</div>
<div class="card-grid">
<div class="viz-card accent-warn"><span class="vc-name">Address from the root</span><span class="vc-note">Write <code>to = module.rds.aws_db_instance.this</code> in the root, for a resource the root does not otherwise mention. Reviewable, but the import lives nowhere near the thing it imports.</span><span class="vc-tag">awkward</span></div>
<div class="viz-card accent-err"><span class="vc-name">Imperative import</span><span class="vc-note">Run <code>terraform import</code> by hand against the address. No plan, no diff, no pull request, no record beyond somebody's shell history.</span><span class="vc-tag">unreviewable</span></div>
</div>

The second option is how most brownfield adoption actually happened, and it is the one that hurts. An operation that permanently changes what Terraform believes it owns should not be a thing one person does in a terminal at the end of a long day.

## Why I have opinions about resource addresses

I have paid for this gap with real adrenaline.

We were moving a client off click-ops onto Terraform with Terragrunt on top. Their database had been created early by a community module; we were swapping it for our own wrapper so the master password could stop arriving as an environment variable at apply time.

Different module, different resource address in state. Terraform does not track a resource by what it is, it tracks it by address, so a changed address reads as "delete this one, create that one". `terraform plan` proposed destroy plus create on the production database, and it was correct to do so.

<div class="viz-label">how a routine refactor becomes an incident</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">Swap one RDS module for another. <b>Routine refactor</b>, reviewed and approved.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">The resource's <b>address in state changes</b> with the module path.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">Terraform reads a changed address as <b>a different resource</b>.</span></div>
<div class="tl-step tl-crash"><span class="tl-text"><code>plan</code> proposes <b>destroy plus create</b>, on the production database.</span></div>
<div class="tl-step"><span class="tl-text">One command away from the worst afternoon of the quarter. <code>terraform state mv</code> caught it.</span></div>
</div>

Half of that dance is what 1.16 removes. A module that knows how to adopt an existing resource can now ship that knowledge with itself, in HCL, in the same directory as the resource block it targets, visible in the same diff.

That is a genuine improvement, and I don't want to undersell it before I complain about the rest.

## The half that got harder

An `import` block inside a module is an import you did not write.

If the module is yours, that is fine. It is the same code, one directory deeper. But modules are exactly the thing we deliberately consume from elsewhere. Our own rule is reuse before build, sourced from a curated registry and vetted upstream modules rather than whatever the public internet is offering that week. Every one of those is a module somebody else authors and versions.

Now consider the merge behaviour, which is where I stopped nodding along. From the implementation:

```go
// If we already have an import statement for this ConfigResource, it
// must have come from a parent module, because duplicate import
// blocks in the same module result in an error.
// The import block in the parent module overrides the block in the
// child module.
```

Two rules, and they are not symmetric:

| Situation | Terraform's behaviour |
|---|---|
| Two `import` blocks, same module, same target | error, loudly, at parse time |
| Parent module and child module both import the same target | parent silently overrides the child |
| A module you consume declares an `import` you never read | applies as written |

The asymmetry is defensible. It matches how `moved` blocks already behave, and root-wins is the sane precedence if you have to pick one. What bothers me is the silence. A parent overriding a child's import changes which real-world resource gets adopted into your state, and no line of plan output says an override happened.

> A conflict Terraform resolves loudly is a design decision. A conflict it resolves quietly is a future incident with a long git blame.

## The PR author got there first

This is the part that convinced me the concern is not paranoia. Here is the engineer who wrote the feature, in the review thread on #38352:

> "though ... never mind overriding an import block, to be honest I am not very comfortable with this feature at all. the only use-cases I can actually come up with are solved by data sources, not importing resources into your state from nested modules. ... If I owned everything, I could write the import statement in the root module, and if I don't own everything ... I don't want imports I didn't write."

And immediately after, the mitigation they wanted:

> "wearing my infra hat, I'd prefer the ability to control this behavior (ie, block nested-module imports/fail/etc) from the root module (as a security stance), but I guess a sentinel policy could cover that."

That switch is not in 1.16. If you want to guarantee no consumed module can declare an import into your state, you are writing a policy check, not flipping a flag.

I want to be precise about what this is and isn't. This is not a vulnerability, and nothing here happens without you running `apply` on a plan you can read. It is a shift in where you have to look. The reviewer's job used to end at the root module's import blocks. Now it extends into every module version bump, and version bumps are the change most likely to get a rubber stamp.

<div class="viz-label">what to actually do about it</div>
<ul class="checklist">
<li>Pin module versions and never float on <code>main</code>, which you were doing already</li>
<li>Diff module upgrades for new <code>import</code> blocks, not just for changed resource arguments</li>
<li>Treat an <code>import</code> in a third-party module as a finding, and ask what it adopts and why</li>
<li>Read the plan for adoption lines on any release that bumps a module, not only on releases that change infrastructure</li>
<li>If you need a hard guarantee, write the policy check, because there is no built-in switch</li>
</ul>

## Everything else worth knowing in 1.16

The rest of the release is genuinely nice, and most of it is small enough to fit in a sentence each.

`terraform graph -format=mermaid` (#38719) prints a dependency graph that pastes straight into a pull request or a docs page. No converter, no Graphviz install, no PNG committed into the repo that goes stale in a month.

```bash
terraform graph -format=mermaid > docs/graph.md
```

The `store` block on `terraform_data` (#38298) holds ephemeral and sensitive values across plan and apply. That is the same direction of travel as ephemeral values and write-only attributes: fewer reasons for a secret to end up parked in state.

`terraform console -scope=<module address>` (#31861) evaluates expressions inside a module's scope. If you have ever debugged an interpolation by adding a temporary output, promoting it to root, running apply, reading the value and then deleting all of it, this is a small mercy.

```bash
terraform console -scope=module.rds
```

And `-json` arrived on `state show` (#23940) and `workspace list` (#38397), which is the difference between scripting against Terraform and parsing its human output with regular expressions.

### One callback, because the framing has not changed

`lifecycle { destroy = false }` (#38784) reached GA with its behaviour intact from beta. So is the changelog description: "prevent a resource from being destroyed."

It does not prevent the resource from being destroyed. It removes the resource from state instead of destroying it. Terraform stops managing the thing, and the thing keeps running and keeps billing. In HashiCorp's own end-to-end test, `terraform destroy` reports `Resources: 0 destroyed` while both resources are still very much alive.

If you skimmed that line in the beta and filed it as "`prevent_destroy` done properly", GA is a good moment to unfile it. `prevent_destroy` fails loudly. `destroy = false` succeeds quietly. Only one of those is a safety feature.

## The line worth keeping

Config-driven import earned its place by making adoption reviewable. Extending it into modules is the right call, and the brownfield work it unblocks is work I do for a living.

But the reason it was worth having was always the review, not the convenience. Moving the declaration one layer deeper moves it one layer further from the person whose job is to read it.

An import you review is a feature. An import you inherit is a supply chain.

---

I'm curious where people land on this one, because I don't think it's obvious. Would you accept an `import` block inside a module you consume from a registry, or is that a hard no in your review checklist? And if it's a no, how are you actually enforcing it today?
