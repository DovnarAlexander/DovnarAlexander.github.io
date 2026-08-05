---
title: "Terragrunt 1.1: six experiments became defaults"
date: 2026-08-04
slug: terragrunt-1-1-stack-dependencies
excerpt: "Terragrunt 1.1 turned six --experiment flags into defaults, including stack dependencies and the content addressable store. Here is what autoinclude changes, and what moved under your CI without a pull request."
tags: [Terragrunt, Terraform, OpenTofu, IaC, DevOps]
---

# Terragrunt 1.1: six experiments became defaults

Most release notes are a list of things you can now opt into. Terragrunt 1.1 is mostly a list of things you have already opted into, whether or not you noticed.

Six features that used to sit behind `--experiment` are now the default behaviour: `stack-dependencies`, `cas`, `catalog-redesign`, `mark-many-as-read`, `opt-out-auth` and `dag-queue-display`. A feature you have to enable is a feature you evaluated. A default is something that changes under your CI while nobody is looking at it.

Two questions, then. What did they build that's actually good, and what moved underneath your pipeline?

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">8 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The release</span><h3 class="ds-title">Six experiments, now defaults</h3><p class="ds-body"><code>stack-dependencies</code>, <code>cas</code>, <code>catalog-redesign</code>, <code>mark-many-as-read</code>, <code>opt-out-auth</code>, <code>dag-queue-display</code>.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">Before</span><h3 class="ds-title">Paths threaded by hand</h3><p class="ds-body">Wiring stack units meant <code>dependency</code> blocks in the catalog plus paths passed through <code>values</code>.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">After</span><h3 class="ds-title">autoinclude, in the stack file</h3><p class="ds-body"><code>unit.vpc.path</code> resolves to the generated path. Nothing hardcoded.</p></section>
<section class="deck-slide"><span class="ds-kicker">Bonus</span><h3 class="ds-title">Patch a catalog unit, don't fork it</h3><p class="ds-body">Anything valid in a unit is valid in <code>autoinclude</code>, including <code>errors</code> and retry rules.</p></section>
<section class="deck-slide"><span class="ds-kicker">CAS</span><h3 class="ds-title">No longer git-only</h3><p class="ds-body">HTTP, S3, GCS, Mercurial, SMB and <code>tfr://</code> deduplicate too. On by default, <code>--no-cas</code> opts out.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The catch</span><h3 class="ds-title">Your filter selects more units</h3><p class="ds-body">Local module <code>.tf</code> files now count as read by the unit. Change-based CI plans a wider surface.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">Skip it</span><h3 class="ds-title">1.1.1 broke assumed roles</h3><p class="ds-body">Backend ops assumed the role a second time. The role got <code>AccessDenied</code> from itself. Fixed in 1.1.2.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">A graduated experiment is a moved default</h3><p class="ds-body">Read the release notes for what stopped being optional, not for what got added.</p></section>
</div>
</div>
</details>

## Stack dependencies: the part worth an afternoon

A Terragrunt stack generates a tree of units from a single `terragrunt.stack.hcl`. The awkward part has always been the wiring. Unit `app` needs the VPC ID from unit `vpc`, so you define a `dependency` block in the catalog unit and then feed it a path from the stack file through `values`.

That works, and it puts your directory layout inside your shared catalog. Reorganize the tree and you patch the catalog for everyone.

`autoinclude` moves the relationship to where the stack is defined:

```hcl
# terragrunt.stack.hcl
unit "vpc" {
  source = "github.com/acme/catalog//units/vpc"
  path   = "vpc"
}

unit "app" {
  source = "github.com/acme/catalog//units/app"
  path   = "app"

  autoinclude {
    dependency "vpc" {
      config_path = unit.vpc.path
    }

    inputs = {
      vpc_id = dependency.vpc.outputs.vpc_id
    }
  }
}
```

Terragrunt writes a `terragrunt.autoinclude.hcl` next to the generated `terragrunt.hcl` and merges it into the unit. The `unit.<name>.path` reference resolves to the generated path, so the layout stops being a shared secret between the catalog and the stack.

> The catalog stopped needing to know where you keep your directories.

### Patch instead of fork

The second-order effect matters more than the syntax. Anything valid in a unit configuration is valid in an `autoinclude` block, which means you can add configuration a catalog unit never shipped with:

```hcl
unit "app" {
  source = "github.com/acme/catalog//units/app"
  path   = "app"

  autoinclude {
    errors {
      retry "transient_errors" {
        retryable_errors   = [".*Error: transient network issue.*"]
        max_attempts       = 3
        sleep_interval_sec = 5
      }
    }
  }
}
```

Every platform team knows the alternative: one environment needs a retry rule, the shared unit doesn't have one, so someone forks the unit. Six months later there are three forks and nobody remembers which is canonical.

Two smaller additions round it out. `include` blocks now work in `terragrunt.stack.hcl`, so shared stack configuration can live in a parent folder. And `dependency` blocks can target stack directories, with the run queue expanding them to the units inside. That relationship is one-way: units can depend on stacks, stacks cannot depend on stacks or units.

## CAS stopped being a git thing

The content addressable store deduplicates source downloads by content instead of by URL. It used to be a git-only experiment. Now it covers everything Terragrunt fetches.

<div class="viz-label">what CAS deduplicates now</div>
<div class="card-grid">
<div class="viz-card accent-cyan"><span class="vc-name">Git</span><span class="vc-note">Catalog clones and <code>git::</code> sources. This is what the experiment already did.</span><span class="vc-tag">before</span></div>
<div class="viz-card accent-ok"><span class="vc-name">HTTP · S3 · GCS</span><span class="vc-note">Remote archives and bucket-hosted modules now resolve through the same local store.</span><span class="vc-tag">new</span></div>
<div class="viz-card accent-ok"><span class="vc-name">Mercurial · SMB · tfr://</span><span class="vc-note">Registry sources fetched over <code>tfr://</code> deduplicate too.</span><span class="vc-tag">new</span></div>
</div>

Identical files occupy disk once regardless of how many configurations use them. Two attributes give you control, both off by default: `update_source_with_cas` rewrites a relative source into a content-addressed `cas::` reference during `stack generate`, so a generated tree stops depending on the surrounding repository layout. `mutable = true` on a `terraform` block copies content instead of hard-linking it, which costs I/O and disk but leaves the working tree editable.

If you need the old behaviour for a run, `--no-cas` (or `TG_NO_CAS=true`) turns it off.

## What moved under your pipeline

This is the part I'd read twice before upgrading a shared repo.

<div class="viz-label">the two behaviour changes</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">Local module changes</span><span class="fs-role">now count as reads</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">reading= filters widen</span><span class="fs-role">more units selected</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-err)"><span class="fs-probe">PR-scoped plan</span><span class="fs-role">covers more than last week</span></div>
</div>

Reading detection is the basis of change-based runs in CI. Previously, pointing a unit's `terraform` block at a local directory did not mark the files inside that directory as read, so editing the module did not select the unit. That was a real gap, and closing it is correct. It also means a `--filter 'reading=./modules/vpc/main.tf'` job now selects units it skipped before:

```bash
terragrunt run --all --filter 'reading=./modules/vpc/main.tf' -- plan
```

For files the detector doesn't track on its own, the new `mark_glob_as_read()` function expands a glob and marks every match as read in one call.

### Skip 1.1.1

One honest warning about the patch line. 1.1.1 fixed chained role assumption for the S3 backend, and in doing so broke setups that supply static AWS credentials and configure a role through `iam_role`, `--iam-assume-role` or `TG_IAM_ASSUME_ROLE`. Terragrunt assumes the role once at the start of a run, and every later call uses that session. In 1.1.1 backend operations started performing a second assumption, so the role tried to assume itself and AWS answered `AccessDenied`. 1.1.2 fixes it, and also cuts `find_in_parent_folders()` lookups: in the project's own micro-benchmark, resolving the root configuration for 100 units nested eight directories deep went from 4.8 ms to 0.49 ms.

## Where I've landed

In June I said 1.0 was the release that made the floor stop moving, and that Runner Pool plus `--filter` were the reasons you would actually re-platform onto Terragrunt now. 1.1 doesn't change that verdict. It does something quieter: it takes the pile of `--experiment` flags that early adopters were carrying in their CI config and folds them into the product.

The upside is real. `autoinclude` is the first time stack wiring reads like a description of the system instead of a description of the filesystem.

The thing to keep in your head is that a graduated experiment behaves differently from a new feature. A new feature waits for you. A default is already running.

---

Which of the six were you already running with `--experiment`? And has anyone measured what reading detection did to the size of their PR-scoped plan? I'd genuinely like the before and after numbers.
