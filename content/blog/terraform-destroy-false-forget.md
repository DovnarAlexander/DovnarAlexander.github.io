---
title: "destroy = false is not prevent_destroy"
date: 2026-08-04
slug: terraform-destroy-false-forget
excerpt: "Terraform 1.16 beta adds lifecycle destroy = false. It reads like prevent_destroy and behaves like the opposite: the resource leaves state and keeps running, and the plan output never calls that a leak."
tags: [Terraform, IaC, DevOps, PlatformEngineering, Cloud]
---

# `destroy = false` is not `prevent_destroy`

The Terraform 1.16.0-beta1 changelog has a line that will be misread by roughly everyone who skims it:

> Resource `lifecycle` blocks now support `destroy = false` to prevent a resource from being destroyed.

Read at speed, that sounds like `prevent_destroy` with the rough edges filed off. A guard rail. Something you put on the RDS instance so nobody drops the database.

It's a different mechanism with a different failure mode, and the difference matters more than the syntax.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The changelog</span><h3 class="ds-title">"to prevent a resource from being destroyed"</h3><p class="ds-body">Read fast, you hear <code>prevent_destroy</code>.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">Two contracts</span><h3 class="ds-title">Protect vs forget</h3><p class="ds-body"><code>prevent_destroy</code> refuses to plan. <code>destroy = false</code> removes the resource from state.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The run</span><h3 class="ds-title">Destroy complete! Resources: 0 destroyed.</h3><p class="ds-body">From HashiCorp's own e2e test. Nothing deleted, everything still billed.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The edge</span><h3 class="ds-title">Replacement orphans the old one</h3><p class="ds-body">Taint, apply: <code>1 added, 0 destroyed</code>. The old instance survives in the cloud, outside state.</p></section>
<section class="deck-slide"><span class="ds-kicker">Prior art</span><h3 class="ds-title">The removed block already did this</h3><p class="ds-body">Since 1.7, as a one-time act with a reviewable diff. The lifecycle flag is permanent.</p></section>
<section class="deck-slide"><span class="ds-kicker">Fair credit</span><h3 class="ds-title">Issue #15485, opened 2017</h3><p class="ds-body">Handing a resource to another team or tool is a real workflow with a nine-year-old request behind it.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Loud vs quiet</h3><p class="ds-body"><code>prevent_destroy</code> fails loudly. <code>destroy = false</code> succeeds quietly. Only one is a safety feature.</p></section>
<section class="deck-slide"><span class="ds-kicker">Status</span><h3 class="ds-title">1.16.0-beta1</h3><p class="ds-body">Read the PR, not the changelog line, before this reaches a shared module.</p></section>
</div>
</div>
</details>

## What each one actually does

<div class="viz-label">two flags, two contracts</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">prevent_destroy = true</span><span class="vc-note">Terraform <em>refuses to produce a plan</em> that would destroy the resource. You get an error and the run stops.</span><span class="vc-tag">protects</span></div>
<div class="viz-card accent-err"><span class="vc-name">destroy = false</span><span class="vc-note">Terraform <em>removes the resource from state</em> instead of destroying it. The plan succeeds. The resource lives on, unmanaged.</span><span class="vc-tag">forgets</span></div>
</div>

Both stop a `terraform destroy` from deleting your database. Only one of them tells you about it.

The internal naming gives it away. The end-to-end test that HashiCorp added with this feature lives in a directory called `forget-lifecycle`, and its fixture is as small as it gets:

```hcl
resource "random_pet" "root" {
  lifecycle {
    destroy = false
  }
}

module "child" {
  source = "./child"
}
```

Run destroy against that, and this is what the test asserts you see:

```text
$ terraform destroy --auto-approve
...
will no longer be managed by Terraform

Destroy complete! Resources: 0 destroyed.
```

Zero destroyed. Two resources still running in the provider, still costing whatever they cost, now tracked by nothing.

> `prevent_destroy` interrupts you. `destroy = false` agrees with you and quietly changes the subject.

## The replacement edge

The destroy case is at least intentional. Somebody typed `terraform destroy`.

The case I'd worry about in a shared module is replacement. The same e2e test taints a resource inside the child module and applies:

```text
$ terraform taint module.child.random_pet.child
$ terraform apply --auto-approve
...
will no longer be managed by Terraform

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

<div class="viz-label">what just happened</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">A resource is marked for <b>replacement</b>: tainted, or a change forces new.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">Terraform creates the <b>replacement</b> and records it in state.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">The old instance is <b>forgotten</b> rather than destroyed.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">The old instance is <b>still running in the cloud</b>, outside state, outside anyone's inventory.</span></div>
</div>

`1 added, 0 changed, 0 destroyed` is a line I've read a thousand times as "nothing was deleted, we're fine." With this flag set, it can also mean "something was abandoned." Nothing in the plan output uses the word leak, and nothing in the summary counts it.

Now imagine that flag sitting in a reusable module, applied across forty workspaces, set by an engineer who left last year for a migration that finished in March.

## We already had a way to forget

None of this means forgetting a resource is a bad idea. It's a genuine workflow: you provisioned something with Terraform, and now another team, another tool, or a managed service is taking over. Deleting it would be wrong, and `terraform state rm` is an out-of-band command with no plan, no review and no audit trail.

Terraform 1.7 already answered that with the `removed` block:

```hcl
removed {
  from = aws_s3_bucket.data

  lifecycle {
    destroy = false
  }
}
```

That's a deliberate act. It appears in a diff, it goes through review, it shows up in the plan, and once the apply lands you delete the block. Intent is expressed once, at the moment it's true.

`lifecycle { destroy = false }` on the resource itself is the same behaviour as a standing property. It doesn't describe a handover; it describes a permanent posture. And permanent postures in shared IaC have a habit of outliving the reason they were added.

The PR closes issues #15485 (opened July 2017, "option to forget a resource instance instead of deleting the instance") and #34439 (removed-block instance support). The 2017 date is worth sitting with: this is a nine-year-old request, and the maintainers explicitly note their theory is that it covers normal use cases while anything more complicated still requires manual state manipulation. That's a fair, honest scope.

## The rest of the beta, briefly

`destroy = false` is the one that will generate arguments, but 1.16.0-beta1 has two more that matter to anyone maintaining modules:

| Change | Why it matters |
|---|---|
| `import` blocks inside child modules | Closes #33474, open since July 2023. The end of "import at the root, then `state mv` it into place." |
| Action triggers get `on_failure` | `halt`, `taint` or `continue` when a provider action fails, plus `before_destroy` / `after_destroy` events. |
| `terraform graph -format=mermaid` | Dependency graphs you can paste straight into a doc or a PR description. |

`import` in modules is the quietly useful one. Bringing existing infrastructure under a module has meant a two-step dance for three years, and every team invented the same workaround.

## Where I've landed

I like this feature. The workflow it serves is real, and nine years is long enough to wait for a declarative answer to it.

What I don't like is the name it will be given in code review. Someone will read `destroy = false`, think "this protects the resource", and set it on a production database. It will do something completely different from what they intended, and the run that proves it will exit zero.

If you want a resource protected, `prevent_destroy` is still the tool. It's blunt, it breaks your plan, and that's exactly the property you're paying for.

If you want Terraform to hand something over, use `removed` while the handover is happening, and delete the block when it's done.

And it's a beta. There's time to argue about this before it lands in your modules, which is the best moment to argue about anything.

---

Would you let `lifecycle { destroy = false }` into a shared module in your organization? I'm genuinely split on whether the reviewable-once `removed` block is enough, or whether a standing flag has a legitimate place. Tell me where you'd draw the line.
