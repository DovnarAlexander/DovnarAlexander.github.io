---
title: "Your Argo CD MCP server is a network service holding your token"
date: 2026-10-21
slug: argocd-mcp-network-service
excerpt: "CVE-2026-82456 let any caller who reached argocd-mcp 0.8.0 act with the operator's Argo CD token. I ran 0.7.0, 0.8.0 and 0.9.0 locally to check the bind and the auth, and wrote down the four checks I now run on every MCP server that holds infra credentials."
tags: [ArgoCD, MCP, Kubernetes, DevSecOps, PlatformEngineering]
---

# Your Argo CD MCP server is a network service holding your token

`argocd-mcp` is the Model Context Protocol server for Argo CD from argoproj-labs: you point an agent at it, and the agent can list applications, read logs, create Applications and trigger syncs. Version 0.8.0, released on June 11, 2026, started its HTTP transport on every network interface and let anyone who reached it open a session without a credential. Every tool call then went to Argo CD with the operator's token.

The fix is 0.9.0, out since August 11 together with advisory GHSA-rp45-5x3v-48mr. VulnCheck assigned CVE-2026-82456 on August 29, CVSS 10.0 in both 3.1 and 4.0. Upgrading takes one command. The more useful part is why it happened, because the same mistake is easy to make in any MCP server that sits next to infrastructure.

<details class="deck-details">
<summary><span class="deck-chevron">▸</span>The 60-second version, flip through the deck<span class="deck-hint">9 slides · swipe →</span></summary>
<div class="deck" data-deck>
<div class="deck-track">
<section class="deck-slide ds-err"><span class="ds-kicker">CVE-2026-82456 · CVSS 10</span><h3 class="ds-title">The server had a token. Its callers didn't.</h3><p class="ds-body"><code>argocd-mcp</code> 0.8.0 as a network service.</p></section>
<section class="deck-slide ds-err"><span class="ds-kicker">The attack</span><h3 class="ds-title">Four steps, no credential</h3><p class="ds-body">Listen on every interface, <code>initialize</code>, <code>create_application</code> from the attacker's repo, <code>sync_application</code> with your token.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">The root cause</span><h3 class="ds-title">The one line</h3><p class="ds-body"><code>ARGOCD_API_TOKEN</code> authenticates the server to Argo CD. The code treated it as if it authenticated the caller.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">My run</span><h3 class="ds-title">Same command, two versions</h3><p class="ds-body">0.8.0: <code>*:3800</code> and HTTP 200 with no creds. 0.9.0: <code>127.0.0.1</code>, and a wider bind without a token exits 1.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">By version</span><h3 class="ds-title">0.7.0 behaved the same</h3><p class="ds-body">The advisory lists only 0.8.0. 0.7.0 also bound <code>*</code> and answered 200.</p></section>
<section class="deck-slide ds-warn"><span class="ds-kicker">Read-only</span><h3 class="ds-title">16 tools, 11 left, 0 permissions removed</h3><p class="ds-body"><code>MCP_READ_ONLY</code> hides tools. Only Argo CD RBAC scopes the token.</p></section>
<section class="deck-slide ds-cyan"><span class="ds-kicker">The checklist</span><h3 class="ds-title">Four questions per MCP server</h3><p class="ds-body">Interface, inbound auth, whose token, what scope.</p></section>
<section class="deck-slide ds-ok"><span class="ds-tag">takeaway</span><h3 class="ds-title">The socket never heard about it</h3><p class="ds-body">"Local, just for the agent" is how you started it. It is not a property of the listener.</p></section>
</div>
</div>
</details>

## Two tokens, one variable

An MCP server for Argo CD has two conversations. The agent talks to the server. The server talks to the Argo CD API. Each of those needs its own answer to "who are you?".

<div class="viz-label">who should authenticate whom</div>
<div class="flow">
<div class="flow-step" style="--fs-accent: var(--color-cyan)"><span class="fs-probe">agent</span><span class="fs-role">the caller, over HTTP or SSE</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-err)"><span class="fs-probe">MCP server</span><span class="fs-role">0.8.0 checked nothing here</span></div>
<div class="flow-arrow">→</div>
<div class="flow-step" style="--fs-accent: var(--color-ok)"><span class="fs-probe">Argo CD API</span><span class="fs-role">sees ARGOCD_API_TOKEN</span></div>
</div>

In 0.8.0 only the second hop had a credential. This is the line the advisory points at, in `src/server/transport.ts`:

```ts
const argocdApiToken =
  (req.headers['x-argocd-api-token'] as string) ||
  process.env.ARGOCD_API_TOKEN ||
  '';
```

If the request carries no token, the server falls back to its own. The listener itself was `app.listen(port)` with no host argument, which in Node means every interface. There was no Host or Origin validation either, so the advisory also flags DNS rebinding: a web page in your browser could reach a listener on your laptop.

The irony is that 0.8.0's headline change, PR #122, was a credential-hardening PR. It moved the token strictly into the transport layer so it would never land in prompts or tool-call logs. That is a real improvement for the second hop. Nobody was looking at the first.

## The attack, as the advisory describes it

The reporter reproduced it against the published package with a local HTTP sink instead of a real Argo CD. No cluster was touched. The chain:

<div class="viz-label">from open port to cluster</div>
<div class="timeline">
<div class="tl-step"><span class="tl-text">An operator starts <b>argocd-mcp http</b> with an Argo CD token in the environment.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">The listener comes up on <b>*:3000</b> and asks callers for nothing.</span></div>
<div class="tl-step tl-warn"><span class="tl-text">An attacker on the network sends <b>initialize</b> and gets an <b>mcp-session-id</b>.</span></div>
<div class="tl-step tl-crash"><span class="tl-text"><b>create_application</b> registers an Application whose <b>repoURL</b> is the attacker's Git repo.</span></div>
<div class="tl-step tl-crash"><span class="tl-text"><b>sync_application</b> tells Argo CD to deploy it, carrying <b>Bearer &lt;your token&gt;</b>.</span></div>
<div class="tl-step tl-crash"><span class="tl-text">The <b>default</b> AppProject allows any source repo, any destination, any resource kind. The cluster runs their manifests.</span></div>
</div>

The sink recorded exactly what Argo CD would have received:

```text
POST /api/v1/applications
Authorization: Bearer TEST-ARGOCD-TOKEN

POST /api/v1/applications/attacker-controlled/sync
Authorization: Bearer TEST-ARGOCD-TOKEN
```

## What I saw when I ran it

I wanted to see the bind for myself rather than trust a CWE label. Each version ran from npm on my Mac with a placeholder token and `ARGOCD_BASE_URL` pointing at a closed local port, so nothing could ever reach a real Argo CD. Each listener lived for a few seconds.

```bash
export ARGOCD_BASE_URL=http://127.0.0.1:9 ARGOCD_API_TOKEN=PLACEHOLDER
npx argocd-mcp@0.8.0 http --port 3800 &
lsof -nP -iTCP:3800 -sTCP:LISTEN
```

```text
COMMAND   PID  USER   FD   TYPE             DEVICE SIZE/OFF NODE NAME
node    35096 olala   12u  IPv6 0xf88f87c35a211587      0t0  TCP *:3800 (LISTEN)
```

Then an `initialize` with no credential of any kind:

```bash
curl -s -D - -o /dev/null http://127.0.0.1:3800/mcp \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"poc","version":"1"}}}'
```

```text
HTTP/1.1 200 OK
mcp-session-id: 3dd1a05c-fa39-49ce-be1a-f153025ed8aa
```

0.9.0 with no extra settings:

```text
node    35328 olala   12u  IPv4 0x2186f97f9d90637b      0t0  TCP 127.0.0.1:3900 (LISTEN)
{"level":30,...,"msg":"Http Stream transport listening on 127.0.0.1:3900"}
```

0.9.0 asked to listen on all interfaces without an inbound token refuses, with exit code 1:

```text
$ MCP_BIND_ADDRESS=0.0.0.0 npx argocd-mcp@0.9.0 http --port 3901
{"level":50,...,"msg":"Refusing to bind to 0.0.0.0 without inbound authentication. The MCP listener exposes every ArgoCD tool to anything that can reach it, and ARGOCD_API_TOKEN authenticates this server to ArgoCD, not the caller. Either set MCP_AUTH_TOKEN to require an inbound \"Authorization: Bearer <token>\" header, or pass --allow-unauthenticated if the listener is already protected by an external layer (a sidecar proxy, service mesh, or network policy). To listen locally only, set --bind-address to 127.0.0.1."}
```

That error message is the best one-paragraph summary of the whole CVE, and the maintainers wrote it into the binary.

Then I tried 0.7.0, because the advisory's affected range is `= 0.8.0` and I wanted to know whether older pins were actually safe:

| Version | Listener | `initialize`, no credential |
|---|---|---|
| 0.7.0 | `*:3811` | HTTP 200 |
| 0.8.0 | `*:3800` | HTTP 200 |
| 0.9.0, defaults | `127.0.0.1:3900` | loopback only |
| 0.9.0, `0.0.0.0` without `MCP_AUTH_TOKEN` | none | refuses to start, exit 1 |
| 0.9.0, `0.0.0.0` with `MCP_AUTH_TOKEN` | `*:3902` | HTTP 401, `Missing or invalid inbound bearer token` |
| 0.9.0, with the bearer header | `*:3902` | HTTP 200 |

The same env-var fallback and the bare `app.listen(port)` are in `transport.ts` at the v0.4.0, v0.5.0, v0.6.0 and v0.7.0 tags. I only ran 0.7.0 end to end (the 0.4.0 package wouldn't even start for me), and I only checked session creation, not tool calls. But "the advisory lists 0.8.0" is not the same statement as "my 0.6.0 pin is fine". Go to 0.9.0.

> "Local, just for the agent" is how you started it. The socket never heard about it.

## What 0.9.0 changed

<div class="viz-label">the fix, in four parts</div>
<div class="card-grid">
<div class="viz-card accent-ok"><span class="vc-name">Loopback by default</span><span class="vc-note"><code>--bind-address</code> / <code>MCP_BIND_ADDRESS</code> defaults to <code>127.0.0.1</code>. A sidecar in the same pod still reaches it.</span><span class="vc-tag">bind</span></div>
<div class="viz-card accent-ok"><span class="vc-name">A real inbound token</span><span class="vc-note"><code>MCP_AUTH_TOKEN</code>, checked as <code>Authorization: Bearer</code> in constant time. Separate from <code>ARGOCD_API_TOKEN</code>.</span><span class="vc-tag">auth</span></div>
<div class="viz-card accent-warn"><span class="vc-name">Fail closed</span><span class="vc-note">A wider bind without a token or <code>--allow-unauthenticated</code> exits non-zero instead of running exposed.</span><span class="vc-tag">startup</span></div>
<div class="viz-card accent-cyan"><span class="vc-name">Host and Origin checks</span><span class="vc-note">Validated on every request, which closes the DNS rebinding path. <code>/healthz</code> stays open for probes.</span><span class="vc-tag">browser</span></div>
</div>

One detail from the README is worth knowing before you design around it: `MCP_AUTH_TOKEN` is a single shared secret. Anyone holding it can reach every Argo CD instance the server knows about. If you need different callers with different reach, the maintainers' answer is separate server instances.

If you run it in Kubernetes and something outside the pod has to reach it, the release notes spell out the two settings you now need together:

```bash
-e MCP_BIND_ADDRESS=0.0.0.0 -e MCP_AUTH_TOKEN=<inbound_token>
```

## MCP_READ_ONLY only filters the tool list

`MCP_READ_ONLY=true` looks like the safe switch. Here is what it does on 0.9.0, summarized from two `tools/list` calls over stdio:

```text
MCP_READ_ONLY=false  16 tools
MCP_READ_ONLY=true   11 tools
hidden: create_application, update_application, delete_application,
        sync_application, run_resource_action
```

The server stops advertising the write tools. The token in its environment can still do everything it could before. If that token is the `admin` one somebody generated on day one, a read-only MCP server is one bug away from a read-write one, and this CVE was that bug.

The real fix lives in Argo CD itself: a dedicated local account, its own API key, and RBAC that matches what the agent actually needs:

```yaml
# argocd-cm
data:
  accounts.mcp-agent: apiKey
---
# argocd-rbac-cm
data:
  policy.csv: |
    g, mcp-agent, role:readonly
```

```bash
argocd account generate-token --account mcp-agent
```

If the agent really must sync, give it `sync` on one AppProject, not `*`. And look at what your `default` project allows, because the advisory's chain works precisely because `default` permits any repo and any destination.

## Four questions for every MCP server next to infra

This is the checklist I now run, on argocd-mcp and on everything shaped like it:

<ul class="checklist">
<li><strong>Interface.</strong> What does it actually bind to? Run <code>lsof</code> or <code>ss -ltnp</code> on the host or in the pod, don't read the README.</li>
<li><strong>Inbound auth.</strong> What does a caller have to present? "Nothing, it's local" is an answer about today's network, not about the server.</li>
<li><strong>Token owner.</strong> Whose credential sits in its environment? Yours, an admin's, or a dedicated account that exists only for this server?</li>
<li><strong>Scope.</strong> What can that credential write, with every tool enabled? Assume the tool filter will fail one day.</li>
<li><strong>Network.</strong> If it has to be reachable, what else stands in front: a sidecar proxy, a NetworkPolicy, a mesh policy?</li>
</ul>

In July I wrote about AI code and trust boundaries, and said that the part of my own Claude Code + MCP pipeline I trust least is the credentials sitting next to it. This CVE is the clean version of that worry, and the model had nothing to do with it. A small Node process held a powerful token and listened on the wrong address.

My position: an MCP server that holds infrastructure credentials gets the same review as any other service that holds them. Interface, auth, owner, scope. That it was started "for the agent" changes nothing.

---

Which MCP servers in your setup hold a token right now, and have you looked at what they bind to?
