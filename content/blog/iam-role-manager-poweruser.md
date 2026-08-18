---
title: "Your new IAM role starts at PowerUser"
date: 2026-08-18
slug: iam-role-manager-poweruser
excerpt: "IAM role manager creates the role for you as you build. Four of the six supported consoles pull the same PowerUserRoleTemplate, so the starting point is close to full service access. What it grants, the SCPs that stop it, and how to find the roles it already made."
tags: [AWS, IAM, CloudSecurity, DevOps]
---

# Your new IAM role starts at PowerUser

On August 12, 2026 AWS made IAM role manager generally available. It is an account setting. Turn it on, and while you build in a supported console, AWS creates the IAM role the service needs and attaches it for you, so you never leave the flow to open the role wizard or write a trust policy.

The feature is genuinely useful and the documentation is honest about what it does. What deserves an afternoon of your attention is the set of templates behind it: what they grant, and what that does to the default in an account nobody is watching.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version, flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">What shipped</span><h3 class="ds-title">IAM role manager, GA on August 12</h3><p class="ds-body">An account setting. Supported consoles create and attach the role for you through the new <code>AcquireRole</code> API.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The template directory</span><h3 class="ds-title">Six consoles, four the same template</h3><p class="ds-body">Elastic Beanstalk, EventBridge, Lambda and Step Functions all resolve to <code>PowerUserRoleTemplate</code>.</p></section>
<section class="deck-slide ds-err"><span class="ds-tag">the default</span><h3 class="ds-title">Empty role in, PowerUser out</h3><p class="ds-body">For open-ended work AWS documents the attached policy as <code>PowerUserAccess</code>. You narrow it later, if you remember.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">inspect</span><h3 class="ds-title">Read the template first</h3><p class="ds-body"><code>iam:GetRoleTemplateVersion</code> returns the trust policy and permissions. AWS recommends this for broad-access templates.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-tag">lever</span><h3 class="ds-title">One permission gates it</h3><p class="ds-body"><code>iam:PutAccountProperties</code> enables and disables role manager. That is the whole switch.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">SCP</span><h3 class="ds-title">Block enablement org-wide</h3><p class="ds-body">Deny that action with <code>iam:AccountPropertyNamespaces</code> equal to <code>RoleManager</code>. AWS publishes the policy.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">SCP</span><h3 class="ds-title">Or block the mechanism</h3><p class="ds-body">Deny <code>iam:*</code> where <code>iam:RoleTemplateARN</code> is not null. Templated role creation stops in console and SDK alike.</p></section>
<section class="deck-slide"><span class="ds-tag">audit</span><h3 class="ds-title">Find what already exists</h3><p class="ds-body">Roles carry <code>SourceRoleTemplate</code>. CloudTrail logs one <code>AcquireRole</code> event per role, template ARN included.</p></section>
<section class="deck-slide ds-ok"><span class="ds-kicker">Remember this</span><h3 class="ds-title">Convenience moves the default, not the model</h3><p class="ds-body">Defaults are what ship. Decide yours before the first sandbox account decides for you.</p></section>
</div>
</div>
</details>

## What role manager actually does

Role manager lives on the IAM console's Account settings page and has two states, enabled and disabled. Flipping it requires the `iam:PutAccountProperties` permission, which the managed policy `IAMFullAccess` includes.

Once enabled, a supported console stops asking you for a role. It calls a new IAM API, `AcquireRole`, with the ARN of an AWS managed role template. `AcquireRole` either creates a role from that template or returns an existing role that already matches it, so the account does not fill up with duplicates. The permissions it needs are your permissions, evaluated per underlying action: `iam:GetRole` when it reuses, `iam:CreateRole` plus `iam:AttachRolePolicy` or `iam:PutRolePolicy` when it creates.

Six service consoles support it today: AWS Elastic Beanstalk, Amazon EventBridge, AWS Lambda, Amazon SageMaker Unified Studio, AWS Secrets Manager and AWS Step Functions.

## The template directory is the story

AWS documents the template each service uses. Read that table before you read anything else about this feature.

| Service console | Role template | Parameters |
|---|---|---|
| Elastic Beanstalk | `PowerUserRoleTemplate` | `AWSServiceName`, `RoleName` |
| EventBridge | `PowerUserRoleTemplate` | `AWSServiceName`, `RoleName` |
| Lambda | `PowerUserRoleTemplate` | `AWSServiceName`, `RoleName` |
| Step Functions | `PowerUserRoleTemplate` | `AWSServiceName`, `RoleName` |
| Secrets Manager | `AWSSecretsManagerRotationRoleTemplate` | rotation scoped, 8 parameters |
| SageMaker Unified Studio | two `IAMPermissiveExecutionRole` templates | admin and user variants |

Four of the six resolve to the same template, and it takes only the service name and the role name. Those parameters shape the trust policy and what the role is called. The permissions are whatever the template holds. For the Lambda case AWS states the policy plainly in its own security blog: because the permissions your code will need cannot be known up front, the template attaches the managed policy `PowerUserAccess`.

`PowerUserAccess` is not admin. It excludes IAM, AWS Organizations and account settings, and the template restricts the trust policy to the one service. Everything else in the account is in scope.

<div class="viz-label">what changed, in one comparison</div>
<div class="card-grid">
<div class="viz-card accent-cyan"><span class="vc-name">The old default</span><span class="vc-note">An empty role. You wrote the trust policy, picked the permissions, attached them. Slow, and every permission was a decision someone made.</span><span class="vc-tag">before</span></div>
<div class="viz-card accent-warn"><span class="vc-name">The new default</span><span class="vc-note">A role that already works, holding close to every service API, waiting for you to narrow it once the workload matures.</span><span class="vc-tag">now</span></div>
</div>

## Read the template before you trust it

Template versions are immutable. When AWS changes a template it publishes a new version rather than editing the old one, and the minor version used is recorded on the role. You can pull the current definition yourself:

```bash
aws iam get-role-template-version \
  --template-arn arn:aws:iam::aws:role-template/iam.amazonaws.com/PowerUserRoleTemplate:1
```

The docs recommend exactly this, in their own words, especially for a template that grants broad access. That sentence is doing a lot of quiet work: AWS is telling you that some of these templates are broad, in the reference page most people will never open.

## The three levers worth pulling this week

<div class="viz-label">from cheapest to most invasive</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">audit</span><span class="fs-role">find roles that already came from a template</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">block enablement</span><span class="fs-role">SCP on one IAM action</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-err)"><span class="fs-probe">block the mechanism</span><span class="fs-role">SCP on the template context key</span></div>
</div>

### Audit first

A role created this way carries a `SourceRoleTemplate` member, present only for roles created with `AcquireRole`, and both `GetRole` and `ListRoles` return it:

```bash
aws iam list-roles \
  --query 'Roles[?SourceRoleTemplate].[RoleName,SourceRoleTemplate.TemplateArn,SourceRoleTemplate.TemplateMinorVersion]' \
  --output table
```

CloudTrail records role creation as a single `AcquireRole` event that names the caller, the template, the parameter values and the role that came out:

```json
{
  "eventSource": "iam.amazonaws.com",
  "eventName": "AcquireRole",
  "requestParameters": {
    "templateArn": "arn:aws:iam::aws:role-template/iam.amazonaws.com/PowerUserRoleTemplate:1",
    "templateMinorVersion": 0,
    "replacementValues": { "AWSServiceName": { "values": ["iam.amazonaws.com"] } }
  },
  "responseElements": {
    "role": { "roleName": "PowerUserRole", "arn": "arn:aws:iam::123456789012:role/PowerUserRole" }
  }
}
```

### Block enablement across the organization

The SCP below is AWS's own, from the role manager access page. It stops any member account from turning the setting on, through the console or the API. Deny-list strategy, so `FullAWSAccess` or an equivalent allow policy stays attached to your organization entities.

```json
{
  "Sid": "DenyRoleManagerEnablement",
  "Effect": "Deny",
  "Action": "iam:PutAccountProperties",
  "Resource": "*",
  "Condition": {
    "ForAnyValue:StringEquals": {
      "iam:AccountPropertyNamespaces": "RoleManager"
    }
  }
}
```

### Or block templated role creation entirely

A second, blunter option keys off `iam:RoleTemplateARN`, the context key present on any action that acts on a templated role creation. This one covers the SDK path as well as the console, and it leaves ordinary role creation untouched:

```json
{
  "Sid": "DenyTemplatedRoleCreation",
  "Effect": "Deny",
  "Action": "iam:*",
  "Resource": "*",
  "Condition": {
    "Null": { "iam:RoleTemplateARN": false }
  }
}
```

There is a third documented shape that inverts the logic and allows only templated creation. It exists for teams that want role creation to run through templates and nothing else, which is a defensible position in a tightly governed account, and the wrong one almost everywhere else.

## Where I would leave it on

Sandbox and personal accounts. This is the case the feature was built for, and the friction it removes is real. A developer standing up a Step Functions workflow at 11pm should not be writing a trust policy from memory.

Production is a different conversation, and AWS agrees in print: disable role manager, then use IAM Access Analyzer unused access findings to cut each role down to what it actually called. Disabling does not delete anything, so roles created earlier keep working and keep their permissions until you change them. Editing one by hand takes it out of role manager's control and turns it into an ordinary customer managed role, with your edits preserved.

Two smaller things worth writing on the same ticket. Roles that role manager reuses rather than creates are shared by whatever else matched the template, so "one role per workload" stops being true unless you make it true. And the audit query above only finds roles created through this path, which means an account that had `PowerUserAccess` habits before August tells you nothing new.

> A convenience feature never changes your permission model. It changes the default, and defaults are what ships.

<ul class="checklist">
<li>Run the audit query in every account, not only production</li>
<li>Decide the organization position: blocked, allowed in sandbox OUs, or allowed everywhere</li>
<li>Attach the SCP to the OUs where the answer is "blocked"</li>
<li>Pull each template you allow with <code>get-role-template-version</code> and read the policy</li>
<li>Put an Access Analyzer review on the calendar for the accounts where it stays on</li>
</ul>

## Your turn

If your organization creates accounts directly through AWS Organizations, this setting is now part of your landing zone whether you wrote it down or not. Worth ten minutes before someone else finds it for you in a security questionnaire.

I write about AWS, Kubernetes and the boring parts of platform work that keep systems up. If you have already made the call on role manager one way or the other, I want to hear which way and why.
