---
title: "The plan wanted to replace the production database"
date: 2026-08-12
slug: terragrunt-migration-state-mv
excerpt: "Swapping an RDS module changed the resource address in state, so Terraform planned a destroy on a live database, and one state mv was the entire fix."
tags: [Terragrunt, Terraform, IaC, AWS, DevOps]
---

# The plan wanted to replace the production database

The client's AWS account had been built by hand over a couple of years. Names invented per resource, security groups nobody could justify, leftovers that existed because someone once needed them on a Tuesday. Two accounts, a dev environment that had stopped working, secrets in `.env` files, and long-lived IAM access keys doing the authentication.

Our job was the boring version of a rescue: modular Terraform underneath, Terragrunt on top, three environments that actually resemble each other, and a pipeline that can tell you what it is about to do.

The part I keep retelling isn't the architecture. It's the afternoon a routine refactor put a production database one `apply` away from being replaced.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The setup</span><h3 class="ds-title">Click-ops AWS, moving to Terraform and Terragrunt</h3><p class="ds-body">Two accounts, a broken dev environment, secrets in <code>.env</code>, three environments to build.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The moment</span><h3 class="ds-title">The plan wanted to replace prod</h3><p class="ds-body">Nobody typed <code>destroy</code>. We swapped one module for another.</p></section>
<section class="deck-slide"><span class="ds-kicker">Why</span><h3 class="ds-title">Terraform tracks addresses, not resources</h3><p class="ds-body">A new module address reads as delete one, create another.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">The fix</span><h3 class="ds-title">One <code>state mv</code></h3><p class="ds-body">Same database, new address. The plan goes quiet.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The cause</span><h3 class="ds-title">A password passed as an env var</h3><p class="ds-body">Drift on every plan, which is why we were rewriting the module at all.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">The model</span><h3 class="ds-title">Write-only, so state never sees it</h3><p class="ds-body"><code>secret_string_wo</code> plus <code>manage_master_user_password = false</code>.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">Earlier mistake</span><h3 class="ds-title">DRY through locals does not compose</h3><p class="ds-body">Locals never reach Terraform as variables. One config file reached 700 lines.</p></section>
<section class="deck-slide"><span class="ds-kicker">The rule</span><h3 class="ds-title">Maps merge, lists concatenate</h3><p class="ds-body">An environment can append a tag. It cannot override one.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Migrations kill you with addresses</h3><p class="ds-body">Read what the plan says about identity, not just the counts.</p></section>
</div>
</div>
</details>

## The change that looked safe

The database had been created early, by a community module, while the environment was still being stood up. Later we replaced that module with our own wrapper. Same engine, same instance class, same data, different code path.

Terraform does not track a resource by what it is. It tracks it by address: `module.<name>.<type>.<name>`. Change the module and you have changed the identity of the thing, as far as state is concerned. Everything that follows is the tool being consistent.

<div class="viz-label">how a refactor turns into a replacement</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">You swap a <b>community module</b> for your own wrapper.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">The resource lands at a <b>new address</b> in the configuration.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">State still holds the <b>old address</b>, pointing at the live instance.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">The plan reconciles the two the only way it can: <b>destroy and create</b>.</span></div>
</div>

The plan itself is unremarkable to look at, which is exactly the danger. Two lines carry the whole story, and they sit in the middle of a wall of attribute diffs:

```text
# module.db.aws_db_instance.this will be destroyed
# module.rds.aws_db_instance.this will be created

Plan: 1 to add, 0 to change, 1 to destroy.
```

`1 to destroy` on an environment where the numbers are usually zero is the line that should stop your hand. The fix is not clever. It is one command, run before the apply:

```bash
terraform state mv \
  module.db.aws_db_instance.this \
  module.rds.aws_db_instance.this
```

State now points the new address at the existing instance, and the next plan has nothing to say. Thirty seconds of work, on the correct side of an outage.

> A migration rarely kills you with `destroy`. It kills you with a resource address.

## Why we were rewriting the module at all

The reason is worth telling, because it is the more common bug.

The RDS master password had been generated by AWS, and it started with a character the migration tool read as the beginning of a comment. The quick workaround at the time was to pass a custom password as an environment variable during `terraform apply`. That unblocks the afternoon and quietly buys you drift: the value lives outside the configuration, so every subsequent plan has an opinion about it.

The wrapper exists to take the password out of that path entirely:

```hcl
ephemeral "random_password" "master" {
  length           = 32
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "aws_secretsmanager_secret_version" "master" {
  secret_id                = aws_secretsmanager_secret.master.id
  secret_string_wo         = ephemeral.random_password.master.result
  secret_string_wo_version = 1
}

resource "aws_db_instance" "this" {
  # ...
  manage_master_user_password = false
}
```

`secret_string_wo` is a write-only argument, supported since Terraform 1.11. The provider accepts the value and state never records it. After bootstrap, password rotation lives outside Terraform, in Secrets Manager, which is where it belonged in the first place.

That is the trade the wrapper makes, and it is worth saying plainly: you gain a state file with no password in it, and you accept that rotating the password is now a Secrets Manager operation with a manual step, not a `terraform apply`.

## The DRY trap that came first

Before any of that, we spent a stretch of the project making the repository worse.

The instinct is right. Units across three environments repeat a lot of the same values, so you put the shared ones in a single `defaults.hcl` and read it everywhere. The mistake is the block you put them in.

<div class="viz-label">two ways to share defaults</div>
<div class="card-grid">
<div class="viz-card accent-err"><span class="vc-name">Shared <code>locals</code></span><span class="vc-note">Context only. Locals never reach Terraform as variables, and Terragrunt leaves the <code>locals</code> block out of include merging by design. Every unit re-maps every value by hand.</span><span class="vc-tag">what we did</span></div>
<div class="viz-card accent-ok"><span class="vc-name">Shared <code>inputs</code></span><span class="vc-note">Inputs are what Terragrunt passes to the module, and a deep-merged <code>include</code> composes them across levels. The unit declares what is different, not what is the same.</span><span class="vc-tag">what works</span></div>
</div>

In practice the first shape looks like this, in every single unit:

```hcl
locals {
  defaults = read_terragrunt_config(find_in_parent_folders("defaults.hcl"))
}

inputs = {
  name        = local.defaults.locals.name
  environment = local.defaults.locals.environment
  tags        = local.defaults.locals.tags
  # and on, and on, for every value the module takes
}
```

Nothing here is shared. The location of the values is shared; the wiring is copied. One of those config files reached about 700 lines before we accepted that the pattern, not the file, was the problem.

The second shape moves the same values into `inputs` on the parent and lets the merge do the work:

```hcl
# root.hcl
inputs = {
  environment = "prod"
  tags = {
    owner   = "platform"
    managed = "terragrunt"
  }
}

# unit
include "root" {
  path           = find_in_parent_folders("root.hcl")
  merge_strategy = "deep"
}

inputs = {
  instance_class = "db.r6g.large"
}
```

### The catch nobody documents loudly enough

Deep merge is not uniform across types, and the difference will find you through tags:

| Type | What a deep merge does |
|---|---|
| Simple values | Child overrides parent |
| Maps | Merged recursively, key by key |
| Lists | Concatenated, never merged element-wise |
| Blocks | Same label merges recursively, otherwise appended |

Tags as a map are fine, and that is the shape to prefer. Tags as a list are not: an environment can append to the parent's list, but it cannot replace an entry in it. Where we needed genuinely different list values per environment, we gave the keys different names and let the module recombine them, which is uglier than it sounds in a sentence and less ugly than a list you cannot override.

`remote_state` and `generate` blocks do not deep merge at all, which is its own small surprise the first time you rely on it.

## What the pipeline learned

The last piece was CI. The first implementation ran a matrix job over the units, which works and scales badly: the matrix is a hand-maintained copy of the dependency graph, and it drifts from the repository the moment someone adds a unit.

Terragrunt already knows the graph, and since the 1.x filter syntax it will also work out what a commit touched:

```bash
terragrunt run --all --filter '[main...HEAD]' -- plan
```

Two related habits came out of the same review, both cheap:

<ul class="checklist">
<li>Run <code>terragrunt validate</code> across the whole codebase, not just the modules, so inputs and references between units are checked too</li>
<li>Build the dependency cache once, during validate, and reuse it for plan and apply instead of re-downloading on every step</li>
</ul>

And one vocabulary fix that saves confusion in every later conversation: in Terragrunt, a folder with a config in it is a **unit**. A **stack** is a generated tree of units. Calling everything a stack made half our documentation ambiguous.

## What I would tell the version of me from March

The database was never actually lost, so the honest version of this story is not heroic. Someone read the plan properly. That is the entire safety mechanism, and writing it out like that is uncomfortable.

So the process changes that came out of it are dull on purpose. Any plan touching a stateful resource gets read for identity first, counts second. Module swaps on live resources come with the `state mv` written into the pull request description, before the apply, where a reviewer can see it. And the DRY refactor waits until the environment is stable, because a config rewrite and a resource-address change in the same week is how you lose track of which one moved the ground.

The migration itself worked. Three environments, deny-all security groups, secrets in Secrets Manager, a pipeline that plans only what changed. None of that is the part I remember.

---

Has your plan ever wanted to replace something that could not be replaced? I am collecting the ones where the tool was technically right, because those are the interesting failures.
