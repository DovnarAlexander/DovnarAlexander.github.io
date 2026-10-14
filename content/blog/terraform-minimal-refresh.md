---
title: "Terraform -minimal-refresh: a faster plan that stops looking at drift"
date: 2026-10-14
slug: terraform-minimal-refresh
excerpt: "Terraform 1.17 adds -minimal-refresh, which skips the refresh for resources a change does not touch. On a hand-edited file in an rc2 run it reported No changes with exit code 0, so drift detection needs its own full-refresh job."
tags: [Terraform, IaC, DevOps, PlatformEngineering, CICD]
---

# Terraform -minimal-refresh: a faster plan that stops looking at drift

Terraform 1.17.0-rc1 shipped on October 7 with a planning flag people have asked for since mid-2024: `-minimal-refresh`. rc2 followed today, October 14, and GA has not landed yet, so everything below is from the release candidate.

The flag makes plan cheaper on large states by skipping the refresh for resources your change does not touch. That is exactly what it promises, and it is also exactly why it should not go anywhere near the job that is supposed to catch drift. I ran it to see what that looks like in practice, and the output is more misleading than I expected.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version, flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">Fast plan, blind plan</h3><p class="ds-body"><code>-minimal-refresh</code> in Terraform 1.17 skips the refresh for anything your change doesn't touch.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">The mechanism</span><h3 class="ds-title">Plan first, refresh only on a diff</h3><p class="ds-body">Each resource is planned against stored state. No-op means no refresh.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The run</span><h3 class="ds-title">Same drift, two answers</h3><p class="ds-body">With the flag: <code>No changes</code>, exit 0. Without it: <code>1 to add</code>, exit 2.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">the catch</span><h3 class="ds-title">Untouched means unread</h3><p class="ds-body">Drifted resources outside the change, and dependents of changed ones, are not refreshed.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">The fix</span><h3 class="ds-title">Two jobs, not one flag</h3><p class="ds-body">Minimal refresh on PR plans. A full refresh on a schedule, alerting on exit code 2.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">Guardrails</span><h3 class="ds-title">Terraform won't mix it</h3><p class="ds-body">Errors with <code>-refresh=false</code> and with <code>-refresh-only</code>.</p></section>
<section class="deck-slide"><span class="ds-kicker">The numbers</span><h3 class="ds-title">207 · 2 years · 0 vs 2</h3><p class="ds-body">Reactions on #35290, time from issue to rc, and the exit codes for one drift.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Code diff vs cloud diff</h3><p class="ds-body">A fast plan diffs your code. Only a full plan diffs your cloud.</p></section>
</div>
</div>
</details>

## Why plan was slow in the first place

A normal `terraform plan` starts with a refresh: for every managed resource, the provider reads the real object back from the API and updates the in-memory state. On a state with a few hundred resources that is a few hundred read calls before Terraform even looks at your diff.

Issue [#35290](https://github.com/hashicorp/terraform/issues/35290), opened on June 4, 2024 under the title "terraform plan -light", lists the three workarounds people were using and why each one hurts:

<div class="viz-label">the workarounds, before 1.17</div>
<div class="card-grid">
<div class="viz-card accent-warn"><span class="vc-name">Raise -parallelism</span><span class="vc-note">More concurrent reads, until the provider's API rate limit pushes back.</span><span class="vc-tag">throttled</span></div>
<div class="viz-card accent-err"><span class="vc-name">-refresh=false</span><span class="vc-note">No reads at all. Plan runs against whatever state last recorded, for every resource.</span><span class="vc-tag">stale</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Split the state</span><span class="vc-note">Smaller roots, faster plans, and a dependency graph you now maintain across states.</span><span class="vc-tag">overhead</span></div>
</div>

The issue collected 207 reactions. It was closed on August 19, 2026 by PR #38953, which did not implement the original "-light" proposal but something more careful.

## How -minimal-refresh decides

The PR description is short and worth reading in full. The mechanism, per resource instance:

<div class="viz-label">per resource, during plan</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">plan</span><span class="fs-role">against the stored state, no refresh</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">no-op?</span><span class="fs-role">keep it, skip the refresh entirely</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">a change?</span><span class="fs-role">discard, refresh, plan again</span></div>
</div>

Using a real plan call as the signal, rather than a text diff of the config, is the smart part: the provider decides what counts as a meaningful change, so whitespace or an equivalent value does not trigger a refresh.

The help text in rc2 is honest about the trade:

```text
  -minimal-refresh    Skips checking for external changes to objects managed by
                      this configuration when an initial plan indicates that the
                      object has not changed since the most recent Terraform apply.
                      This can potentially make planning faster, but at the expense
                      of possibly planning against a stale record of the remote
                      system state.
```

## The run

I wanted to see the failure mode for myself. Two `local_file` resources, applied with Terraform v1.17.0-rc2 on darwin_arm64:

```hcl
resource "local_file" "app_config" {
  filename = "${path.module}/out/app.conf"
  content  = "replicas = 2\n"
}

resource "local_file" "feature_flags" {
  filename = "${path.module}/out/flags.json"
  content  = jsonencode({ new_checkout = false })
}
```

Then the drift: someone flips a flag by hand, outside Terraform.

```bash
echo '{"new_checkout":true}' > out/flags.json
```

With the new flag:

```text
$ terraform plan -minimal-refresh -detailed-exitcode; echo $?

No changes. Your infrastructure matches the configuration.

Terraform has compared your real infrastructure against your configuration
and found no differences, so no changes are needed.
0
```

Without it:

```text
$ terraform plan -detailed-exitcode; echo $?
local_file.feature_flags: Refreshing state... [id=0932faec15d7d4ea4fc3aa3808d19b09bfedac33]
local_file.app_config: Refreshing state... [id=9c9784843f694b0d666d6e2413b3edc46e87e47b]
...
  # local_file.feature_flags will be created
...
Plan: 1 to add, 0 to change, 0 to destroy.
2
```

Zero `Refreshing state...` lines in the first run, two in the second. Exit code 0 against exit code 2. And the first run's closing message says Terraform compared your real infrastructure against your configuration, which it did not do. The wording predates the flag, and it now describes something that did not happen.

> A fast plan diffs your code. Only a full plan diffs your cloud.

## What gets refreshed and what doesn't

Then I made a "PR change": `replicas = 2` became `replicas = 3` in `app_config`, with the hand-edited flag file still in place.

```text
$ terraform plan -minimal-refresh
local_file.app_config: Refreshing state... [id=9c9784843f694b0d666d6e2413b3edc46e87e47b]
  # local_file.app_config must be replaced
Plan: 1 to add, 0 to change, 1 to destroy.

$ terraform plan
local_file.feature_flags: Refreshing state... [id=0932faec15d7d4ea4fc3aa3808d19b09bfedac33]
local_file.app_config: Refreshing state... [id=9c9784843f694b0d666d6e2413b3edc46e87e47b]
  # local_file.app_config must be replaced
  # local_file.feature_flags will be created
Plan: 2 to add, 0 to change, 1 to destroy.
```

The changed resource was refreshed and planned correctly. The drifted one sitting next to it was not mentioned at all. Combined with the PR notes, the full picture is:

| Resource | Refreshed under -minimal-refresh? | Source |
|---|---|---|
| Changed by your config | yes, after an initial plan | PR #38953, my run |
| Unchanged but drifted | no | my run |
| Depends on a changed resource | no, each instance decides in isolation | PR #38953 |
| Schema upgraded by a new provider | always | PR #38953 |
| Destroy plans, deposed and orphaned | never | PR #38953 |

The maintainer put the consequence plainly in the PR thread, answering whether the flag affects drift detection: "if you never update your state (for example, if you always ran with this flag), then you'll never detect any drift until you change your configuration."

## Split the PR plan from the drift check

The flag is fine. The risk is the pipeline that has exactly one plan job and treats it as both the review gate and the drift detector. A lot of setups do, because until now every plan was a full refresh and you got drift detection for free.

So split it. The PR plan exists to show reviewers what this change will do, and that is the job `-minimal-refresh` was built for:

```bash
# pull request: what does this change do?
terraform plan -minimal-refresh -out=tfplan
```

The drift check exists to show what the cloud did without you, and it needs every resource read back:

```bash
# schedule: did anything change outside Terraform?
terraform plan -detailed-exitcode -lock=false
rc=$?
[ "$rc" -eq 2 ] && echo "drift detected" && exit 1
exit "$rc"
```

Terraform also refuses the combinations that would make this ambiguous. Both errors are from my rc2 run:

```text
$ terraform plan -minimal-refresh -refresh=false
Error: Incompatible refresh options

The -minimal-refresh and -refresh=false options are mutually-exclusive,
because -minimal-refresh only affects whether Terraform refreshes.

$ terraform plan -minimal-refresh -refresh-only
Error: Incompatible plan mode options

The -minimal-refresh option can only be used in normal or destroy planning
modes, but the current mode is RefreshOnlyMode.
```

If you are on HCP Terraform or Terraform Enterprise, check before you put it in `TF_CLI_ARGS_plan`. A user asked exactly that in the PR thread, because their workspace relies on background drift detection; the answer was that platform support is still in progress on a separate team.

## It's the same direction as --filter

The line I wanted people to leave our June Navitalks demo with was "A year ago this repo needed seven `--include` flags and a wrapper script for a PR-scoped plan. Now it's one filter." `--filter` narrows which units get planned. `-minimal-refresh` narrows which resources inside a unit get read. Both make PR plans cheaper by looking at less, and both are correct for that job. Neither is a drift detector, and the more you narrow the PR plan, the more you need one somewhere else.

## Also in 1.17

Two other items from the same release notes, briefly: variables and locals are now allowed in `required_providers` (PR #39153, `const` variables only, nothing that depends on a plan result), and Terraform Policy is GA, so `-policies` on `plan`, `apply` and `query` no longer needs an experimental build.

## What to actually do

<ul class="checklist">
<li>Find out whether your drift detection is a dedicated job or just "the PR plan would show it"</li>
<li>If it's the latter, add a scheduled full-refresh plan with <code>-detailed-exitcode</code> before adopting the flag</li>
<li>Then add <code>-minimal-refresh</code> to PR plans only, after 1.17 is GA</li>
<li>Keep it out of <code>TF_CLI_ARGS_plan</code> and any global env that also feeds the drift job</li>
<li>Time it on your real stack before quoting a speed-up; nobody has published one</li>
</ul>

I'm not going to quote a speed-up number. HashiCorp hasn't published one, and two local files plan in a tenth of a second either way. When I time it on a real stack I'll add the numbers here.

---

Where does your drift check actually run today? If the honest answer is "the PR plan", this flag quietly removes it.
