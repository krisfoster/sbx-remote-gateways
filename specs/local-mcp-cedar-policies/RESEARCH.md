# Research: Local MCP Server Cedar Policies — Controlling Tool Access and Restricting Plugin/MCP Additions

Scope: goal 3 — "Local MCP server Cedar policies: controlling tool access, restricting
plugin/MCP additions from within the sandbox". All findings below are drawn from
publicly available Docker documentation (and, for the complementary client-side layer,
public Claude Code documentation); sources are cited inline and listed at the bottom.

## 1. Two separate governance layers are relevant here

Getting this goal right requires distinguishing two independent controls that both
affect "can an MCP server/plugin be added, and can its tools be used":

| Layer | What it governs | Where it's authored/enforced | Language |
|---|---|---|---|
| **A. Docker Sandboxes MCP access policy** | The sandbox's own MCP gateway: server *registration* (`sbx mcp add`) and *use* (tool calls, resource reads, prompt gets) through that gateway | Docker Home (org admins) or the local sandbox host | **Cedar** |
| **B. Claude Code managed MCP configuration** | What the Claude Code process itself — running *inside* the sandbox — will load, independent of any gateway | Managed settings files deployed to the machine/session (MDM, server-managed settings) | Claude Code's own settings schema (JSON), not Cedar |

Docker's docs are explicit that (A) is Cedar-based: "Unlike network access policies and
filesystem access policies, MCP policies are organization policies written in Cedar, and
Docker defines the MCP namespace, including the actions, resource types, attributes, and
approval behavior that policies can match"
([MCP access policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/mcp/)).
Layer (B) is covered because the goal explicitly says "restricting plugin/MCP additions
*from within the sandbox*" — and inside the sandbox, the thing actually capable of adding
an MCP server or plugin is the Claude Code process itself (via `claude mcp add`, editing
`.mcp.json`, or `/plugin`), which Docker's gateway doesn't inherently prevent unless it's
also separately locked down at the Claude Code layer (§5).

## 2. Layer A: Docker's Cedar MCP access policy model

### Actions (`MCP::Action` namespace)

| Action | Evaluated when |
|---|---|
| `register` | A developer runs `sbx mcp add` |
| `invokeTool` | An agent calls a tool through the gateway |
| `readResource` | An agent requests an MCP resource |
| `getPrompt` | An agent requests a prompt |
| `invokePrimordial` | An agent invokes a built-in gateway tool, e.g. an OAuth helper |

Two distinct evaluation moments follow from this: **registration time** (matches the
chosen name and the resolved server's attributes, notably `identityURL`) and **use time**
(matches the registered server, tool annotations, resource URIs, or prompt names)
([MCP access policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/mcp/)).

### Resource types and attributes

- `MCP::Server` — a registered server, referenced like `MCP::Server::"example"`, with
  attributes including:
  - `identityURL` — the server's canonical identity/endpoint URL
  - `readOnly` — boolean, defaults to `false`, distinguishes read-only tools from
    state-changing ones
  - `type` — server classification, e.g. `"local-stdio"` for a host-run server (as
    opposed to a remote HTTP/SSE endpoint)
- `MCP::Primordial` — built-in gateway tools not tied to a registered server, e.g.
  `MCP::Primordial::"example-authorize"`

### Default-deny, and forbid-always-wins

"Governed MCP activity is default deny: a request is blocked unless a matching permit
allows it. A matching forbid overrides any permit, including a permit that requires
approval" ([search summary of Docker Sandboxes governance docs](https://docs.docker.com/ai/sandboxes/governance/)).

### Literal Cedar examples from Docker's documentation

Restricting registration to one approved name+identity:

```cedar
permit (principal, action == MCP::Action::"register", resource)
when {
  resource in MCP::Server::"example" &&
  resource.identityURL == "https://mcp.example.com/mcp"
};
```

Blocking a specific remote server by identity URL, regardless of the local name chosen:

```cedar
forbid (principal, action == MCP::Action::"register", resource)
when { resource.identityURL == "https://mcp.example.com/mcp" };
```

Blocking all host-run (local stdio) servers — this is the specific mechanism for
"restrict host-run servers" mentioned in Docker's own policy-pattern list, and covers
both explicit `--command` servers and OCI-packaged servers registered with `--local`:

```cedar
forbid (principal, action == MCP::Action::"register", resource)
when { resource.type == "local-stdio" };
```

Allowing only read-only tool calls on a given server:

```cedar
permit (principal, action == MCP::Action::"invokeTool", resource)
when {
  resource in MCP::Server::"example" &&
  resource.readOnly == true
};
```

Requiring human approval for anything that isn't read-only, via the `@requireApproval`
annotation:

```cedar
@requireApproval("non-read-only tool call")
permit (principal, action == MCP::Action::"invokeTool", resource)
when {
  resource in MCP::Server::"example" &&
  resource.readOnly == false
};
```

When a policy carries `@requireApproval`, the gateway sends an `elicitation/create`
request to the client session; the session must explicitly confirm, and if no
confirmation arrives the request is denied. Re-evaluation happens with an "approval
digest" binding the human's response to the specific authorization request it approved.
Docker's own docs caveat this precisely: it "functions as a confirmation guardrail for
human-driven clients" and explicitly **does not** implement administrative separation of
duties — i.e. it's a human-in-the-loop UX gate, not an access-control substitute.

### Registration policy is forward-only

Changing a registration-time policy governs future `sbx mcp add` calls; it does **not**
retroactively remove an already-saved registration, and does not by itself stop
`sbx mcp load` of a server that was previously approved. Use-time policy (`invokeTool` /
`readResource` / `getPrompt`) is what actually gates ongoing use of an already-registered
server ([MCP access policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/mcp/),
[Organization policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/organization/)).

### Where MCP Cedar policy is authored, and by whom

Cedar policy for MCP is authored in **Docker Home**, under **AI Platform > MCP access**,
as free-form Cedar statements in a policy editor. Only organization owners, or custom
roles granted governance permissions, can create or manage these policies
([Organization policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/organization/)).

**Finding**: across the Docker Sandboxes governance pages fetched for this research, MCP
policy is consistently described as an **organization-level** mechanism only. Network
policy has a documented local, per-machine equivalent (`sbx policy allow/deny network
<domain>`, `sbx policy init balanced|open|locked-down`), but no equivalent local
`sbx policy` subcommand for authoring MCP Cedar rules turned up in the fetched docs — MCP
governance appears to exist only via the organization-level Cedar editor. This is called
out explicitly as a gap in this research rather than asserted with full confidence, since
it is the absence of something in the docs rather than a positive statement; worth
confirming directly against a current `sbx policy --help`/`sbx mcp --help` in this repo's
experiments (see §6).

## 3. Precedence between local and organization policy (the general model)

While MCP policy itself is organization-authored, understanding how it composes with
locally-set rules matters for the "restrict...from within the sandbox" half of the goal,
because network and filesystem policy are the other levers that can independently box in
what a sandbox — and therefore an MCP server or the agent using it — can reach. The
general precedence rule, documented consistently across the governance pages
([Governance](https://docs.docker.com/ai/sandboxes/governance/),
[Policy concepts](https://docs.docker.com/ai/sandboxes/governance/concepts/),
[Organization governance](https://docs.docker.com/ai/sandboxes/security/governance/)):

- **Deny wins.** If any applicable rule — local or organizational — says deny, the
  request is denied regardless of any matching allow.
- **Default deny.** Anything no allow rule matches is blocked.
- **Once organization governance is active, only organization allow rules grant access**;
  local `sbx policy` allow rules "are no longer evaluated and can't expand what the
  organization permits." Local **deny** rules keep applying on top — a developer can
  narrow access further than the org policy, but never widen it.
- **Network policies are evaluated on every request** (so changes apply immediately once
  synced); **filesystem policies are checked only at workspace-mount time** (sandbox
  creation), not continuously at runtime.

Local network policy has three named presets, set with `sbx policy init <mode>`:

| Mode | Behavior |
|---|---|
| `open` | All outbound traffic allowed (equivalent to a wildcard allow rule) |
| `balanced` (default) | Default deny, with a baseline allowlist for AI provider APIs, package managers, code hosts, container registries, and common cloud services |
| `locked-down` | All outbound traffic blocked, including model provider APIs such as `api.anthropic.com` |

Representative local commands ([Local policy](https://docs.docker.com/ai/sandboxes/security/policy/)):

```bash
sbx policy init balanced
sbx policy allow network api.anthropic.com
sbx policy deny network ads.example.com
sbx policy check network api.anthropic.com
sbx policy ls --include-inactive
sbx policy reset --force
```

## 4. Sign-in enforcement: closing the personal-account bypass gap

A separate, complementary control — **sign-in enforcement** — restricts Docker Sandboxes
usage to authenticated members of specific Docker organizations, verified when a
developer runs `sbx login`; failed verification revokes credentials immediately
([Sign-in enforcement](https://docs.docker.com/ai/sandboxes/governance/sign-in-enforcement/)).
Its stated purpose is directly relevant to "restricting...from within the sandbox": it
"closes that gap" of a developer using a personal (non-org) Docker account specifically to
**bypass organization governance policies** — since organization-level Cedar/MCP/network/
filesystem policy only applies to a session authenticated into the governed organization,
sign-in enforcement is what stops someone from sidestepping all of §2–3 simply by not
being logged in as an org member.

## 5. Layer B: restricting MCP/plugin additions at the Claude Code layer itself

Docker's Cedar policy governs the sandbox's **gateway** — but the agent inside the
sandbox is still running the full Claude Code binary, which has its own, independent
notion of "add an MCP server" (`claude mcp add`, hand-editing `.mcp.json`, or installing a
plugin via `/plugin`). Nothing in the Docker governance docs fetched for this research
suggests Cedar policy intercepts those Claude-Code-native paths directly; they are a
separate control surface, documented in
[Control MCP server access for your organization](https://code.claude.com/docs/en/managed-mcp):

- **`managed-mcp.json`** — deployed to a fixed OS path (e.g. `/etc/claude-code/managed-mcp.json`
  on Linux/WSL, which is what a sandbox's Linux userspace would use), gives Claude Code an
  **exclusive** server set; users can't add, modify, or use any other server, and
  `claude mcp add --transport http test https://example.com/mcp` fails outright with
  `Cannot add MCP server: enterprise MCP configuration is active and has exclusive
  control over MCP servers` — the URL doesn't even need to resolve, since the policy
  check rejects the command before any network call.
- **`allowedMcpServers` / `deniedMcpServers`** — allowlist/denylist entries matched by
  `serverUrl` (with `*` wildcards), `serverCommand` (exact argument match), or
  `serverName`; denylist always wins; setting `allowManagedMcpServersOnly: true` makes
  the managed allowlist authoritative and ignores any allowlist a user adds in their own
  settings.
- **`strictPluginOnlyCustomization`** with `"mcp"` in its list — a named pattern
  ("Plugin servers only") that specifically blocks users from adding servers through
  `~/.claude.json` or project `.mcp.json`, while still allowing plugin-provided MCP
  servers to load. This is the closest documented match to the goal's literal phrase
  "restricting plugin/MCP additions."

These settings are deployed the same way any Claude Code managed setting is deployed —
MDM profile, GPO/registry key, fleet-management tooling, or server-managed settings from
the claude.ai admin console — which is a mechanism entirely outside `sbx`/Docker's own
governance surface. A sandbox image or setup script could bake one of these files into
the sandbox's filesystem so that, regardless of what Docker's Cedar MCP policy allows,
Claude Code itself refuses to load or add anything outside the fixed/allowed set.

### Why both layers matter together

Docker's Cedar policy (§2) governs traffic that goes **through the sbx-managed gateway**.
If an agent inside the sandbox instead calls `claude mcp add --transport http <name>
<url>` directly (bypassing `sbx mcp add`/the gateway entirely, as documented for goal 1
of this repo), that connection is only constrained by:

1. The sandbox's **network egress policy** (§3) — can the sandbox reach that URL at all.
2. Claude Code's **own** managed-MCP configuration (§5) — is Claude Code itself permitted
   to add/load that server.

Cedar's `register`/`invokeTool` policies do not appear (per the docs fetched) to apply to
that path, since it never touches the `sbx mcp` registry or gateway. That makes layer B a
necessary complement, not a redundant one, if the goal is to genuinely prevent MCP/plugin
additions "from within the sandbox" rather than only within Docker's own gateway.

## 6. Open questions for this repo to answer experimentally

- Confirm directly (via `sbx policy --help`, `sbx mcp --help`, and the current Docker
  Sandboxes CLI) whether any **local**, per-machine Cedar authoring path for MCP policy
  exists today, or whether MCP governance is genuinely organization-only as the fetched
  docs suggest.
- Verify empirically whether `claude mcp add --transport http` run from inside a Docker
  Sandbox is in fact unconstrained by Docker's Cedar MCP policy (i.e., that it bypasses
  the gateway entirely) versus being silently routed through the sandbox's single MCP
  endpoint regardless of how it was invoked.
- Test whether a `managed-mcp.json` (or `strictPluginOnlyCustomization`) baked into a
  sandbox image actually survives and is honored for the lifetime of a running sandbox,
  and whether the sandboxed user has write access to override it (filesystem policy, §3,
  would be the relevant control if so).
- Determine what a blocked `invokeTool` request actually looks like to the agent/user in
  practice (error text, retry behavior) — useful for writing this repo's own demo/test
  policies against a predictable signal.

## Sources

- [Docker Sandboxes — Governance](https://docs.docker.com/ai/sandboxes/governance/)
- [Docker Sandboxes — Policy concepts](https://docs.docker.com/ai/sandboxes/governance/concepts/)
- [Docker Sandboxes — MCP access policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/mcp/)
- [Docker Sandboxes — Organization policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/organization/)
- [Docker Sandboxes — Organization governance](https://docs.docker.com/ai/sandboxes/security/governance/)
- [Docker Sandboxes — Local policy](https://docs.docker.com/ai/sandboxes/security/policy/)
- [Docker Sandboxes — Sign-in enforcement](https://docs.docker.com/ai/sandboxes/governance/sign-in-enforcement/)
- [Claude Code Docs — Control MCP server access for your organization](https://code.claude.com/docs/en/managed-mcp)
