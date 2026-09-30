---
title: "Terragrunt stopped writing RootAccess into your state bucket. Your bucket didn't notice"
date: 2026-09-30
slug: terragrunt-state-bucket-rootaccess
excerpt: "Terragrunt 1.2 no longer grants s3:* to the account ARN on new state buckets, but old buckets keep the statement, and IAM was always what decided who reads your state."
tags: [Terragrunt, AWS, IaC, DevSecOps, PlatformEngineering]
---

# Terragrunt stopped writing RootAccess into your state bucket. Your bucket didn't notice

Terragrunt v1.2.0-rc1 shipped on September 24, and one of its breaking changes is a single paragraph about a bucket policy. Since December 2019, every time Terragrunt bootstrapped an S3 state backend it attached a statement with the `Sid` `RootAccess`, granting `s3:*` on the bucket and its objects to `arn:aws:iam::<account-id>:root`. In 1.2 that statement is gone.

Buckets that already have it keep it. Terragrunt will not touch them. Why that matters is not what most people will assume, and it takes a look at what the statement actually did to see it.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">Terragrunt 1.2 · AWS IAM</span><h3 class="ds-title">:root never meant root</h3><p class="ds-body">Your state bucket's policy, decoded.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">Since 2019</span><h3 class="ds-title">s3:* for the account ARN</h3><p class="ds-body">Every S3 backend bootstrap added a <code>RootAccess</code> statement. Removed in <strong>1.2.0-rc1</strong>.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">the misread</span><h3 class="ds-title">It reads like a lock</h3><p class="ds-body">"Only the root user." AWS docs: an account ARN <em>"does not limit permissions to only the root user."</em></p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The real gate</span><h3 class="ds-title">IAM always decided</h3><p class="ds-body">Same account: an identity policy alone opens S3. AdministratorAccess, PowerUserAccess, the CI role with <code>s3:*</code>.</p></section>
<section class="deck-slide ds-err"><span class="ds-tag">the trap</span><h3 class="ds-title">1.1 puts it back</h3><p class="ds-body">With <code>--backend-bootstrap</code> and <code>--non-interactive</code>, Terragrunt 1.1 calls the bucket out of date and re-adds the statement.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">Find and strip</span><h3 class="ds-title">get-bucket-policy, jq, put-bucket-policy</h3><p class="ds-body">Filter out <code>Sid == "RootAccess"</code>. If it was the only statement, delete the policy.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">The real lock</span><h3 class="ds-title">Deny with an allowlist</h3><p class="ds-body">An explicit <code>Deny</code> on <code>aws:PrincipalArn</code> beats any identity policy. Keep a break-glass role in it.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">It meant "ask IAM"</h3><p class="ds-body"><code>:root</code> in a Principal never meant root.</p></section>
</div>
</div>
</details>

## What Terragrunt wrote

This is the statement, as the bootstrap code built it (`EnableRootAccesstoS3Bucket` in the S3 backend client), with a made-up account and bucket:

```json
{
  "Sid": "RootAccess",
  "Effect": "Allow",
  "Principal": {
    "AWS": ["arn:aws:iam::111122223333:root"]
  },
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::acme-tofu-state",
    "arn:aws:s3:::acme-tofu-state/*"
  ]
}
```

It sat next to a second statement, `EnforcedTLS`, which denies any request where `aws:SecureTransport` is false. That one is still there in 1.2 and it is a good default. Only `RootAccess` went away.

The option to avoid it existed all along, `skip_bucket_root_access = true`, added a few hours after the statement itself, in December 2019. In 1.2 it has nothing left to skip and is deprecated.

## How it reads, and what it means

Almost everyone who opens that policy reads `:root` as the root user, the email-and-password identity that owns the account. Read that way, the statement looks harmless or even protective: only the most privileged identity has full access.

<div class="viz-label">the same line, two readings</div>
<div class="card-grid">
<div class="viz-card accent-warn"><span class="vc-name">How it reads</span><span class="vc-note">"Only the root user can touch this bucket." Looks like a lock, so nobody audits past it.</span><span class="vc-tag">the misread</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">What it means</span><span class="vc-note">"The whole account. IAM decides which identities." The account ARN and the bare account ID behave the same way.</span><span class="vc-tag">the reality</span></div>
</div>

The IAM documentation settles it in one line:

> Using the account ARN in the Principal element does not limit permissions to only the root user of the account.

An account principal delegates. Access then goes to whichever users and roles in that account have an identity policy that allows it.

## The part that surprised me

Here is where the Terragrunt release notes and the Terragrunt docs say slightly different things. The release notes say the statement "widened reach to state files that routinely hold secrets." The state backend docs say the account already owns the bucket, "so the statement gave the account no reach it did not have."

The docs are the precise version. Inside a single account, S3 grants a request if either the identity policy or the bucket policy allows it and nothing denies it. A role with `s3:GetObject` on `*` could read your state before Terragrunt added `RootAccess`, and it can read it after you remove it. Delegating to the account just hands the decision back to IAM, which already had it.

So removing the statement does not shrink who can read your state. What the statement did, for almost seven years, was make the bucket policy look like it was doing the protecting.

<div class="viz-label">what actually decides access to state</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">request</span><span class="fs-role">s3:GetObject on the state key</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">identity policy</span><span class="fs-role">allows it? that's enough in-account</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-err)"><span class="fs-probe">bucket policy</span><span class="fs-role">only an explicit Deny can stop it</span></div>
</div>

The list of identities that can open your state file is therefore the list of identities whose IAM policies allow S3 reads on that bucket. In a typical account that includes more than people expect:

| Identity | Reads state? | Why |
|---|---|---|
| `AdministratorAccess` | yes | `*` on `*` |
| `PowerUserAccess` | yes | everything except IAM, Organizations, Account |
| `AmazonS3FullAccess` | yes | `s3:*` on `*` |
| CI role with `s3:*` on `*` | yes | the shortcut someone took to make the pipeline green |
| Any of the above, after `RootAccess` is removed | still yes | the bucket policy was never the gate |

State is where the secrets you could not keep out of it end up. Our default is that secrets never land in state: they come from an encrypted store at apply time, and where the provider supports it they go through write-only arguments. That is the half you fix in code, and it only reaches as far as provider support for write-only arguments does. Generated passwords, credentials a provider returns as attributes, and resources written before any of this existed still put secrets into state, which is why the other half, who can open the file, matters.

## The trap: Terragrunt 1.1 puts it back

This is the detail that will bite teams who clean up quickly. Before 1.2, Terragrunt did not only add `RootAccess` at creation. On every bootstrap it checked whether the statement was present, and if it was missing it marked the bucket as needing an update. The check lives in the 1.1.5 source:

```go
if !client.SkipBucketRootAccess {
	enabled, err := client.checkIfBucketRootAccess(ctx, l, bucketName)
	if err != nil {
		return false, toUpdate, err
	}

	if !enabled {
		toUpdate.RootAccess = true

		updates = append(updates, "Bucket Root Access")
	}
}
```

Then it asks before changing anything:

```text
Remote state S3 bucket acme-tofu-state is out of date. Would you like Terragrunt to update it? (y/n)
```

In CI you run with `--non-interactive`, and in that mode every prompt resolves to yes:

```text
The non-interactive flag is set to true, so assuming 'yes' for all prompts
```

So if you strip the statement while one pipeline somewhere still runs Terragrunt 1.1 with `--backend-bootstrap`, the next run of that pipeline writes it straight back. Order matters:

<div class="viz-label">the safe order</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">Move every runner and laptop to <b>1.2</b>, or set <b>skip_bucket_root_access = true</b> in the root config for the ones you cannot move yet.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">Find every state bucket that carries a <b>RootAccess</b> statement.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">Confirm the roles that need the bucket can reach it through <b>their own IAM policies</b>.</span></div>
<div class="tl-step"><span class="tl-text">Strip the statement, then decide whether you want a <b>real lock</b> on top.</span></div>
</div>

## Find it and strip it

For a single bucket, the Terragrunt docs give the recipe. Fetch the policy, drop the statement by `Sid`, put it back:

```bash
aws s3api get-bucket-policy --bucket acme-tofu-state --query Policy --output text \
  | jq '.Statement |= map(select(.Sid != "RootAccess"))' > policy.json

aws s3api put-bucket-policy --bucket acme-tofu-state --policy file://policy.json
```

If you bootstrapped with `skip_bucket_enforced_tls`, `RootAccess` may be the only statement in the policy, and the filter leaves an empty list. S3 will not take a policy with no statements. Delete the policy instead:

```bash
aws s3api delete-bucket-policy --bucket acme-tofu-state
```

To find every affected bucket in an account, loop over them and look for the `Sid`:

```bash
for b in $(aws s3api list-buckets --query 'Buckets[].Name' --output text); do
  aws s3api get-bucket-policy --bucket "$b" --query Policy --output text 2>/dev/null \
    | jq -e '.Statement[] | select(.Sid == "RootAccess")' > /dev/null \
    && echo "$b"
done
```

If you still want the old behaviour, 1.2 lets you opt back in explicitly with `enable_bucket_root_access = true` in the `remote_state` config. And if you want to make sure nobody keeps the deprecated option around, the `skip-bucket-root-access` strict control turns its warning into an error:

```bash
terragrunt run --all --strict-control skip-bucket-root-access -- plan
```

## The lock you thought you had

If the goal was "only these identities can read state," the tool for that is an explicit `Deny` with a principal allowlist. AWS documents this pattern as the replacement for `NotPrincipal`:

```json
{
  "Sid": "StateReadersOnly",
  "Effect": "Deny",
  "Principal": "*",
  "Action": "s3:*",
  "Resource": [
    "arn:aws:s3:::acme-tofu-state",
    "arn:aws:s3:::acme-tofu-state/*"
  ],
  "Condition": {
    "ArnNotLike": {
      "aws:PrincipalArn": [
        "arn:aws:iam::111122223333:role/terragrunt-ci",
        "arn:aws:iam::111122223333:role/terragrunt-plan-readonly",
        "arn:aws:iam::111122223333:role/break-glass"
      ]
    }
  }
}
```

An explicit deny beats any identity policy, so `AdministratorAccess` on some unrelated role no longer opens your state. Two cautions. Keep a break-glass role in the list, because the same deny applies to whoever tries to fix a mistake in it. And roll it out on a non-production state bucket first, because every principal that is not on the list, including ones you forgot about, stops working the moment you apply it.

## What to actually do

<ul class="checklist">
<li>Upgrade every Terragrunt that runs <code>--backend-bootstrap</code> to 1.2, or pin <code>skip_bucket_root_access = true</code> where you can't yet</li>
<li>Run the loop above in each account and list the buckets that still carry <code>RootAccess</code></li>
<li>Strip the statement with the docs recipe, or delete the policy if it was the only statement</li>
<li>List the roles that can read each state bucket through IAM, starting with the CI role</li>
<li>Add a <code>Deny</code> with an <code>aws:PrincipalArn</code> allowlist if that list is longer than it should be</li>
</ul>

The honest summary of this change is that Terragrunt removed a line that looked like security and was not. Your exposure is exactly what it was yesterday. The difference is that the bucket policy no longer implies otherwise.

---

When did you last list who can read your state bucket, and was the answer shorter or longer than you expected?
