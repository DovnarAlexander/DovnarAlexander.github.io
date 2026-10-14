---
title: "EKS Auto Mode moved node tuning into the NodeClass"
date: 2026-10-14
slug: eks-auto-mode-advanced-compute
excerpt: "Since October 1, the EKS Auto Mode NodeClass accepts kubelet settings, 25 allowlisted kernel sysctls and hugepages, so the privileged tuning DaemonSet can go. Every edit replaces nodes, and anything off the list is still managed by AWS."
tags: [AWS, EKS, Kubernetes, PlatformEngineering, DevOps]
---

# EKS Auto Mode moved node tuning into the NodeClass

On October 1 the Auto Mode `NodeClass` got a new block, `advancedCompute`. It takes kubelet settings, Linux kernel sysctls and hugepages, the three things that used to push people off Auto Mode or into running a privileged pod on nodes they were not supposed to touch.

This is a small API change with a large blast radius on the cleanup side. If your cluster carries a "node tuning" DaemonSet, a chart with a privileged sysctl init container, or a managed node group that exists only because of one kernel flag, most of that can now be deleted. Not all of it, and the part that stays is worth knowing before you start.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version, flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">The tuning DaemonSet can go</h3><p class="ds-body">Kernel and kubelet settings moved into the Auto Mode <code>NodeClass</code> on October 1.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">Before</span><h3 class="ds-title">One sysctl, two bad exits</h3><p class="ds-body">Leave Auto Mode for your own launch template, or run a privileged pod that does <code>sysctl -w</code> on a node you don't own.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">after</span><h3 class="ds-title">Same setting, new home</h3><p class="ds-body"><code>advancedCompute.kernel.sysctl</code>, applied at boot. No privileged pod.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">What's in it</span><h3 class="ds-title">kubelet, sysctls, hugepages</h3><p class="ds-body">Seven kubelet settings, 25 allowlisted sysctls, 2Mi and 1Gi hugepages plus the THP policy.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">the catch</span><h3 class="ds-title">Every edit is a rollout</h3><p class="ds-body">Changing the block marks nodes as drifted. EKS replaces them; nothing is edited in place.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">Admission</span><h3 class="ds-title">Ranges, pairs, and dependencies</h3><p class="ds-body">Out-of-range values, half a pair, or <code>idsPerPod</code> without user namespaces are rejected.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The limits</span><h3 class="ds-title">25 · 110 · 80%</h3><p class="ds-body">Sysctls on the list, pods per node, and the hugepages share of memory.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">Just the config file</h3><p class="ds-body">The tuning DaemonSet was a config file with root access. Now it's just the config file.</p></section>
</div>
</div>
</details>

## How node tuning on Auto Mode used to work

Auto Mode runs nodes on a Bottlerocket variant that AWS manages. You pick instance requirements in a `NodePool`, networking and storage in a `NodeClass`, and AWS owns the rest of the node. Until this month, "the rest" included every kernel and kubelet setting.

That was fine until a workload needed one. The classic case is a search cluster. The OpenSearch Helm chart defaults `sysctlVmMaxMapCount` to `262144` and offers two ways to get it onto the node, both described in its own `values.yaml` as requiring privilege:

```yaml
## Set optimal sysctl's through securityContext. This requires privilege. Can be
## disabled if the system has already been preconfigured.
sysctl:
  enabled: false

## Set optimal sysctl's through privileged initContainer.
sysctlInit:
  enabled: false
```

On Auto Mode there was no "preconfigured" option, so the choice came down to two exits.

<div class="viz-label">before october 1</div>
<div class="card-grid">
<div class="viz-card accent-err"><span class="vc-name">Leave Auto Mode</span><span class="vc-note">A managed node group with your own launch template and user data. You get the flag and you also get AMI updates, node rotation and bootstrap scripts back on your plate.</span><span class="vc-tag">more infra</span></div>
<div class="viz-card accent-err"><span class="vc-name">Privileged pod</span><span class="vc-note">A DaemonSet or init container running <code>sysctl -w</code> as root on a node that AWS is managing for you. It works until it doesn't, and nobody reviews it as infrastructure.</span><span class="vc-tag">root on node</span></div>
</div>

Neither is wrong in isolation. Both are a tax for wanting one number in `/proc/sys`.

## The new block

`advancedCompute` sits on the `NodeClass` next to the networking and storage settings you already have. Here is one that covers all three sub-blocks, with values taken from the AWS documentation examples:

```yaml
apiVersion: eks.amazonaws.com/v1
kind: NodeClass
metadata:
  name: tuned-compute
spec:
  role: MyNodeRole
  subnetSelectorTerms:
    - tags:
        Name: "private-subnet"
  securityGroupSelectorTerms:
    - tags:
        Name: "eks-cluster-sg"

  advancedCompute:
    kubelet:
      maxPods: 60
      podPidsLimit: 4096
      eviction:
        hard:
          memory.available: "100Mi"
          nodefs.available: "10%"
      logging:
        containerLogMaxSize: "10Mi"
        containerLogMaxFiles: 5
    kernel:
      sysctl:
        vm.max_map_count: 262144
        net.core.somaxconn: 4096
    hugepages:
      pages:
        - size: "2Mi"
          count: 512
```

Point a `NodePool` at it, and the nodes come up with those settings from boot. Sysctls are written into Bottlerocket's `[settings.kernel.sysctl]` before anything schedules, which is the part a privileged DaemonSet could never guarantee: there was always a window between "node ready" and "DaemonSet pod finished".

## What you can and cannot set

The block is an allowlist. Every field below is enumerated in the docs, and anything outside the list is still AWS's.

| Sub-block | What it takes | Guardrail |
|---|---|---|
| `kubelet` | `maxPods`, `podPidsLimit`, `idsPerPod`, `singleProcessOOMKill`, `eviction`, `logging`, `allowedUnsafeSysctls` | `maxPods` 1–110; `podPidsLimit` is `-1` or ≥100 |
| `kernel.sysctl` | 25 sysctls: inotify, file handles, socket buffers, SYN backlog, ARP cache, TCP timers, dirty-page ratios, `vm.max_map_count`, `vm.swappiness`, `user.max_user_namespaces` | each one has a min and max; out of range is rejected |
| `hugepages` | static `2Mi` and `1Gi` pages, transparent hugepage `enabled` and `defrag` | combined reservation ≤80% of instance memory |

Things you might reach for that are not on the list: CPU manager and topology manager policy, `kubeReserved` and `systemReserved`, kubelet feature gates, and any sysctl outside the 25. If your node group exists for one of those, it stays.

`allowedUnsafeSysctls` deserves a note because it reads like a bigger escape hatch than it is. It accepts up to 64 entries matching `kernel.shm*`, `kernel.msg*`, `kernel.sem`, `fs.mqueue.*` or `net.*`, and it only permits pods to request those namespaced sysctls in their own `securityContext.sysctls`. It does not change the node.

## Admission does the reviewing

A pleasant surprise in the docs is how much the `NodeClass` admission check rejects up front, before a single node launches:

<ul class="checklist">
<li><code>vm.dirty_background_ratio</code> and <code>vm.dirty_ratio</code> must be set together, and background must be strictly lower</li>
<li>The three ARP thresholds <code>gc_thresh1</code>, <code>gc_thresh2</code>, <code>gc_thresh3</code> must be set together and strictly increasing</li>
<li><code>net.ipv4.tcp_congestion_control</code> accepts <code>cubic</code> or <code>reno</code>, nothing else</li>
<li><code>idsPerPod</code> must be a multiple of 65536, and is rejected unless <code>user.max_user_namespaces</code> is above zero on the same NodeClass</li>
<li>Static hugepages and <code>efa-only</code> interfaces cannot share a NodeClass</li>
</ul>

Compare that with a DaemonSet running `sysctl -w`. A typo there fails on the node, at runtime, in a pod log that nobody watches. Here it fails at `kubectl apply`.

## Every change is a node replacement

This is the part to plan around. Nothing in `advancedCompute` is applied to a running node.

<div class="viz-label">what an edit actually does</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">edit</span><span class="fs-role">change advancedCompute on the NodeClass</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">drift</span><span class="fs-role">every node using it is marked drifted</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">replace</span><span class="fs-role">new nodes boot with the new values</span></div>
</div>

The docs say it plainly for both kubelet settings and sysctls: changing them marks existing nodes as drifted, and the new values take effect only on replacement nodes. That is the right design, because it is the same model as an AMI update and it means a node's settings always match its spec. It also means bumping `net.core.somaxconn` on a busy NodeClass is a rollout across every node in it. Treat it like one: off-peak, with PodDisruptionBudgets you trust, and on a separate NodeClass first if the workload is sensitive.

> The tuning DaemonSet was a config file with root access. Now it's just the config file.

## User namespaces, declaratively

Two weeks ago I wrote about rootless kubelet in Kubernetes 1.37 and ended on "not on EKS, GKE or AKS, kubelet flags aren't yours there." On Auto Mode that is now partly untrue.

The announcement pitches user namespaces for rootless container builds in CI, and the mechanics are two fields. `user.max_user_namespaces` in `kernel.sysctl` decides whether user namespaces can be created on the node at all (`0` disables them). `idsPerPod` in `kubelet` sets how many UIDs and GIDs each pod's user namespace gets, and admission will not take it without the sysctl:

```yaml
advancedCompute:
  kernel:
    sysctl:
      user.max_user_namespaces: 65536
  kubelet:
    idsPerPod: 65536
```

That is a node-level setting for pod-level user namespaces (`hostUsers: false`), not a rootless kubelet. The node components stay AWS's. But for the CI runner that builds images, the one exception most restricted Pod Security baselines I've worked with end up carving out, it is a cleaner answer than a privileged pod with a comment explaining why.

## What to actually do

<ul class="checklist">
<li>List every privileged DaemonSet and init container on your Auto Mode clusters and note which sysctl or kubelet flag each one exists for</li>
<li>Check each against the 25-sysctl allowlist and the seven kubelet fields; the ones that match can move into a NodeClass</li>
<li>For Helm charts, turn the chart's own sysctl toggle off (<code>sysctlInit</code>, <code>sysctl</code>) once the NodeClass carries the value</li>
<li>If a managed node group exists only for a kernel flag, recheck it against the list before the next AMI cycle</li>
<li>Schedule NodeClass edits like AMI rollouts, because that is what they are</li>
</ul>

What I like most here is a change of category: node tuning stopped being a pod with root and became a reviewed field with a validator in front of it.

---

Which sysctl or kubelet flag still keeps you on your own node groups? If it's on the list now, I'd like to hear what you delete first.
