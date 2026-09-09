---
title: "Rootless Kubernetes went on by default, and nothing happened"
date: 2026-09-09
slug: rootless-kubelet-beta
excerpt: "The KubeletInUserNamespace gate reached beta in Kubernetes 1.37 and now defaults to on, yet nothing changes on an existing cluster. What the gate really does, how it differs from hostUsers: false, and where rootless nodes are worth running today."
tags: [Kubernetes, ContainerSecurity, DevOps, PlatformEngineering, CloudNative]
---

# Rootless Kubernetes went on by default, and nothing happened

On September 4 the `KubeletInUserNamespace` feature gate graduated to beta in Kubernetes 1.37, and with the promotion it flipped to enabled by default. If you upgrade a cluster to 1.37 tomorrow, your node components will keep running as root exactly as they did before.

That is not a rollout gone wrong. It is the design, stated plainly in the announcement: enabling the gate does not put the kubelet into a user namespace, so nothing changes for existing rootful clusters. The gate is not the switch. Understanding why is the useful part, and it clears up the single most common confusion in this corner of Kubernetes security.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version — flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide"><span class="ds-kicker">The premise</span><h3 class="ds-title">Rootless is on by default now</h3><p class="ds-body">And your nodes are still root. Both statements are true at the same time.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">The mechanism</span><h3 class="ds-title">The gate was never the switch</h3><p class="ds-body">The user namespace is created <em>outside</em> Kubernetes, by rootless Docker, Podman, k3s or Usernetes.</p></section>
<section class="deck-slide ds-warn"><span class="ds-tag">the confusion</span><h3 class="ds-title">Two user namespaces, not one</h3><p class="ds-body"><code>hostUsers: false</code> wraps the <strong>pod</strong>, GA since 1.36. <code>KubeletInUserNamespace</code> wraps the <strong>node components</strong>.</p></section>
<section class="deck-slide"><span class="ds-kicker">What the gate does</span><h3 class="ds-title">It ignores six sysctls and /dev/kmsg</h3><p class="ds-body">Plus kube-proxy shrugging off <code>RLIMIT_NOFILE</code>. That is the entire feature gate.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The stakes</span><h3 class="ds-title">Five CVEs that end at root on the host</h3><p class="ds-body">cr8escape, two runc breakouts, a kubelet <code>gitRepo</code> bug, a containerd image-label bug.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">new in beta</span><h3 class="ds-title">runningInUserNamespace</h3><p class="ds-body">Node status now reports it, so you can label or taint rootless nodes away from workloads that need the real thing.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The limits</span><h3 class="ds-title">No nfs, no iscsi, not every CNI</h3><p class="ds-body">And not on EKS, GKE or AKS, where the kubelet flags are not yours.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">It stopped complaining, that's all</h3><p class="ds-body">The gate did not make your kubelet rootless. It stopped the kubelet from complaining when something else already had.</p></section>
</div>
</div>
</details>

## The confusion worth clearing first

There are two features in Kubernetes with "user namespace" in the name. They protect against different things, they graduated at different times, and people reach for the wrong one constantly.

<div class="viz-label">two different namespaces</div>
<div class="card-grid">
<div class="viz-card accent-cyan"><span class="vc-name">hostUsers: false</span><span class="vc-note">The <code>UserNamespacesSupport</code> gate, GA since v1.36. Puts <em>the pod</em> in a user namespace. Node components still run as root.</span><span class="vc-tag">pod-level</span></div>
<div class="viz-card accent-warn"><span class="vc-name">KubeletInUserNamespace</span><span class="vc-note">Beta in v1.37. Puts <em>the node components</em> in a user namespace: kubelet, CRI and OCI runtimes, CNI plugins, kube-proxy.</span><span class="vc-tag">node-level</span></div>
</div>

The pod-level one limits what a container can do to the node. The node-level one limits what the node's own software can do to the host. If the kubelet itself has a vulnerability, `hostUsers: false` on your pods does nothing for you.

They do not conflict, and the interesting case is combining them. A cluster running with `KubeletInUserNamespace` can now be nested inside pods of an outer cluster that use `hostUsers: false`, which gives you Kubernetes inside Kubernetes without reaching for `privileged: true`. That combination is new, and it is the practical reason this promotion matters.

## What the gate actually does

This is the part that surprises people, and it is why "on by default" changed nothing.

A Linux user namespace maps an unprivileged host UID, say 1000, to a fake root inside the namespace. Inside, UID 0 has enough authority for most of what node components need: mounting volumes, creating cgroups, configuring pod network namespaces. Outside, it is still UID 1000 with no power over the host.

Kubernetes does not create that namespace. Something else does, before the kubelet starts. Rootless Docker, rootless Podman, rootless nerdctl, k3s in rootless mode, or Usernetes.

So what is the gate for? It exists because a kubelet running as fake root will fail at a handful of operations that need real root, and without the gate it treats those failures as fatal. With the gate on, it shrugs and continues:

```text
ignore permission errors when setting:
  vm.overcommit_memory
  vm.panic_on_oom
  kernel.panic
  kernel.panic_on_oops
  kernel.keys.root_maxkeys
  kernel.keys.root_maxbytes

ignore errors when opening /dev/kmsg
kube-proxy: ignore errors setting RLIMIT_NOFILE
```

The blog post describing the promotion calls the gate "quite boring," and that is accurate. It is an error-tolerance flag, not a mode switch. On a normal rootful node every one of those operations succeeds, there is no error to ignore, and turning the gate on is a no-op. Hence a default flip that nobody notices.

## What you are actually buying

The motivation is a list of real breakouts, and it is worth reading as a group rather than one at a time:

| CVE | Component | What it gave the attacker |
|---|---|---|
| CVE-2022-0811 ("cr8escape") | CRI-O | arbitrary sysctls, such as `kernel.core_pattern`, leading to code execution as root |
| CVE-2023-27561 | runc | masked-path bypass via a volume mount race, exposing the host's procfs |
| CVE-2024-10220 | kubelet | arbitrary command execution as root via `gitRepo` volumes |
| CVE-2025-31133 | runc | bind-mounting attacker-controlled paths, writing to `/proc/sysrq-trigger` and `/proc/sys/kernel/core_pattern` |
| CVE-2026-53488 | containerd | arbitrary command execution via crafted labels in a container image |

Five bugs, five different components, one shared outcome: root on the host. That is the pattern the feature attacks. It does not prevent any of these bugs. It changes where the blast stops.

<div class="viz-label">same bug, two blast radii</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-err)"><span class="fs-probe">rootful</span><span class="fs-role">root on the host</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-warn)"><span class="fs-probe">rootless</span><span class="fs-role">one unprivileged UID</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">result</span><span class="fs-role">no kernel, no boot loader, no firmware</span></div>
</div>

That last step is the one I find most valuable operationally. An attacker confined to a non-root account cannot modify the kernel, the boot loader, or the firmware, which means they cannot conceal the intrusion at a level below your tooling. Detection stays possible.

The documentation is equally clear about what it does not do, and I would rather quote it than paraphrase it away:

> User namespaces are not effective for mitigating vulnerabilities in the kernel itself.

So this is a layer, not a replacement. It sits alongside a restricted Pod Security baseline, seccomp profiles, and minimal scanned images. The baseline stops most escapes from starting. This stops the ones that start anyway from ending on the host.

## New in beta: the node tells you

Alongside the default flip, one small change has immediate operational value. Node status now reports whether the node is running in a user namespace, through the `runningInUserNamespace` property on `NodeSystemInfo`:

```bash
kubectl get nodes -o yaml | grep runningInUserNamespace
```

This matters because rootless nodes are not interchangeable with rootful ones. Some workloads genuinely need real root on the host, and the announcement names the obvious category: CNI plugin installers. Now that the state is exposed as a field, you can label or taint on it and keep those workloads on nodes that can actually run them, instead of discovering the mismatch through a failing DaemonSet.

Kubernetes now runs its own node conformance end-to-end tests on a rootless cluster, which is the kind of dogfooding that makes a beta feel like a beta rather than a demo.

## The limits, stated honestly

This is where I would push back on anyone treating the promotion as a signal to go rootless in production next quarter.

<div class="viz-label">what breaks</div>
<div class="card-grid">
<div class="viz-card accent-err"><span class="vc-name">Storage</span><span class="vc-note">Most non-local volume drivers, including <code>nfs</code> and <code>iscsi</code>, do not work. <code>local</code>, <code>hostPath</code>, <code>emptyDir</code>, <code>configMap</code>, <code>secret</code> and <code>downwardAPI</code> are known to work.</span><span class="vc-tag">hard limit</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Networking</span><span class="vc-note">Some CNI plugins may not work; Flannel with VXLAN is the known-good path. The kubelet port and NodePort services need an external port forwarder to reach the host.</span><span class="vc-tag">watch</span></div>
<div class="viz-card accent-err"><span class="vc-name">Managed control planes</span><span class="vc-note">On EKS, GKE and AKS the kubelet configuration is not yours to change. This is a self-managed story today.</span><span class="vc-tag">blocked</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Setup cost</span><span class="vc-note">cgroup v2 only, systemd with a user session, per-distro sysctls, and your user in <code>/etc/subuid</code> and <code>/etc/subgid</code>.</span><span class="vc-tag">effort</span></div>
</div>

The storage constraint is the one that decides most clusters. If your workloads mount NFS, the conversation ends there.

For anyone who wants to see it work rather than read about it, the shortest path is kind on rootless Docker:

```bash
dockerd-rootless-setuptool.sh install
kind create cluster
```

minikube supports the same shape with `minikube start --driver=docker`. Usernetes is the option that builds multi-node clusters from rootless Docker, Podman or nerdctl connected over VXLAN, and it is where the feature gate came from originally. k3s has an experimental rootless mode that does not need an external runtime at all.

## Where this lands

The honest read is that this is not a production-cluster feature for most people yet, and the docs do not pretend otherwise. Where it earns its keep today is narrower and genuinely useful.

CI runners are the clearest case. Every platform baseline I have worked with enforces a restricted Pod Security profile, no privileged containers, no host mounts, run as non-root, and then carves out exactly one documented exception in its own namespace. That exception is almost always the runner that builds container images. A rootless node under a nested cluster is a real answer to that exception rather than a policy comment explaining it.

Nested clusters are the second. Running a test cluster inside a pod used to mean `privileged: true` and the shrug that comes with it. Combining `hostUsers: false` on the outer pod with `KubeletInUserNamespace` on the inner node removes the shrug.

Then laptops, shared HPC machines, and the use case the announcement calls out that I did not expect to see in a Kubernetes blog: a dedicated local account for running an AI coding agent alongside a test cluster, so the agent cannot break the host when it acts on something malicious it read on the internet. That is a sandbox argument, and it is a good one.

> The gate didn't make your kubelet rootless. It stopped the kubelet from complaining when something else already had.

## What to actually do

<ul class="checklist">
<li>Nothing urgent on your production clusters, the default flip is inert on rootful nodes</li>
<li>Check whether your workloads mount <code>nfs</code> or <code>iscsi</code>, because that answers the question before anything else does</li>
<li>Try it where it costs nothing: rootless Docker plus kind on a laptop, one afternoon</li>
<li>If you run self-managed nodes for CI, price out a rootless node pool against the privileged exception you currently document</li>
<li>Once you have mixed nodes, taint on <code>runningInUserNamespace</code> before something that needs real root schedules onto one</li>
</ul>

The feature started as an experiment in 2018 and reached alpha in 1.22 in 2021. Five years from alpha to beta is not a stall, it is what it costs to change the privilege model of every node component without breaking the clusters that depend on the old one.

---

Which of your workloads still genuinely needs real root on the node, and have you tried to remove that need? Mine is always the CI runner that builds container images.
