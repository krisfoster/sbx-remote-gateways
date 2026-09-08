# Research: Integrating a Non-Docker Remote MCP Gateway (Cloudflare) into a Docker Sandbox

Scope: goal 1 — "Use of remote MCP gateways other than Docker's own, specifically
Cloudflare; pass-through vs. client registration (DCR)". All findings below are drawn
from publicly available vendor documentation and the public MCP specification; sources
are cited inline and listed at the bottom.

## 1. Background: two different "gateways" in play

There are two distinct things called a "gateway" that are relevant here, and it's easy
to conflate them:

1. **Docker's own MCP Gateway/Toolkit** — a Docker Desktop / Docker Hub feature that runs
   MCP servers as containers and unifies them behind one endpoint for MCP clients
   ([MCP Gateway docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/),
   [MCP Toolkit docs](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/)).
2. **The Docker Sandboxes MCP gateway** — a separate, sandbox-specific gateway. The agent
   inside a sandbox is given one MCP endpoint; the `sbx` CLI on the host manages which
   servers are registered behind it, OAuth credentials, and sandbox lifecycle
   ("the gateway gives the agent inside the sandbox one MCP endpoint, while `sbx` manages
   the registered servers, OAuth credentials, and sandbox lifecycle on the host")
   ([Docker Sandboxes: MCP gateway](https://docs.docker.com/ai/sandboxes/mcp-gateway/)).

This repo's "remote MCP gateway other than Docker's own" goal is about (2): pointing the
sandbox's MCP gateway at an MCP endpoint that is *not* run by Docker — e.g. one hosted on
Cloudflare — instead of (or alongside) Docker-run/local servers.

## 2. Registering a remote (non-Docker) MCP endpoint with `sbx`

The sandbox gateway supports registering **remote** MCP servers by URL, in addition to
local stdio/container-based servers. Per the official Docker Sandboxes docs
([mcp-gateway](https://docs.docker.com/ai/sandboxes/mcp-gateway/)):

> "A remote endpoint URL identifies a running MCP server. The server runs remotely, and
> the sandbox gateway connects to it." Local stdio servers, by contrast, "run on the
> host, not inside the sandbox."

Representative commands from that same page:

```bash
# Register a remote MCP server by URL (e.g. a hosted MCP endpoint)
sbx mcp add notion --url https://mcp.notion.com/mcp

# List registered servers
sbx mcp ls

# Attach registered server(s) to a sandbox at run time
sbx run claude --name mcp-demo --static-mcp notion
sbx run claude --name my-session --static-mcp notion,linear

# Load a server into an already-running sandbox
sbx mcp load
sbx mcp load linear --sandbox my-session

# Inspect / remove
sbx mcp inspect notion
sbx mcp rm notion
```

Nothing in the URL scheme is Docker-specific — `--url` just needs a reachable HTTPS MCP
endpoint. A Cloudflare-hosted remote MCP server (e.g. a Worker running the
`agents`/MCP framework, or a Cloudflare **MCP Portal** aggregating several upstream
servers — see §4) is registered the same way a first-party remote server is:
`sbx mcp add <name> --url https://<cloudflare-endpoint>/mcp`.

Two things must independently allow this for it to work end-to-end:

- **Network egress**: the sandbox's network policy must permit outbound access to the
  gateway's/endpoint's domain. Docker Sandboxes are network-isolated by default and use an
  allow-list model (`sbx policy allow network <domain>`), with policy modes such as
  "Balanced" pre-allowing common categories (AI provider APIs, package managers, code
  hosts, etc.) but not arbitrary third-party hosts
  ([Sandboxes governance](https://docs.docker.com/ai/sandboxes/governance/)).
- **MCP registration policy**: if organization-level governance is active, an
  administrator-authored Cedar policy must permit registering that specific server/URL
  (see §5) — local `sbx policy allow` rules are not evaluated once org policy governs MCP,
  though local `forbid` rules still apply on top
  ([Sandboxes governance](https://docs.docker.com/ai/sandboxes/governance/)).

## 3. Auth options when registering a remote server with `sbx`

The same docs page shows flags for handling authentication to the remote endpoint,
covering both "skip for now" and pre-registered/pass-through-style OAuth client setups:

```bash
# Register without completing the OAuth flow immediately
sbx mcp add notion --url https://mcp.notion.com/mcp --skip-auth

# Pre-registered (static) OAuth client — client id supplied up front, secret via sbx secret
sbx secret set mcp:slack.client_secret
sbx mcp add slack --url https://slack.example.com/mcp --client-id <CLIENT_ID>

# Custom/non-standard authorization server metadata + pre-registered client
sbx mcp add serverx --url https://mcp.serverx.example/mcp \
  --oauth-authorization-server ./serverx-authorization-server.json \
  --client-id <CLIENT_ID>

# Scope control
sbx mcp add serverx --url https://mcp.serverx.example/mcp --scope read --scope write
sbx mcp auth serverx --scope read
sbx mcp auth serverx --no-scope

# Check/complete auth, inspect status
sbx mcp auth <server>
sbx mcp auth status notion
sbx mcp auth status notion --json
```

This maps directly onto the MCP authorization spec's client-registration options (§4):
`--client-id` is the **pre-registration** path (a client id/secret is already known to
the remote server ahead of time, without a live DCR round-trip), while omitting it and
simply completing an interactive OAuth flow relies on whatever the remote server's
authorization server advertises (DCR or CIMD) at connect time.

## 4. Cloudflare as the "other" remote MCP gateway

Cloudflare offers two relevant, independent things:

### 4.1 Hosting your own remote MCP server on Cloudflare Workers

Cloudflare documents building and deploying a remote MCP server on Workers, with OAuth
login built in via the `@cloudflare/workers-oauth-provider` library
([Build a Remote MCP server](https://developers.cloudflare.com/agents/model-context-protocol/guides/remote-mcp-server/),
[workers-oauth-provider on GitHub](https://github.com/cloudflare/workers-oauth-provider),
[Cloudflare blog: Build and deploy Remote MCP servers](https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/)).
That library "adds OAuth 2.1 authorization to HTTP APIs and remote MCP servers running on
Cloudflare Workers. The MCP server acts as both an OAuth client to upstream services and
as an OAuth server to MCP clients" — i.e. it is designed to be spec-compliant with the
MCP authorization spec described in §5, including token issuance, client registration,
and consent screens
([Securing MCP servers](https://developers.cloudflare.com/agents/model-context-protocol/guides/securing-mcp-server/)).
The securing-MCP-servers guide also documents CSRF protection, input sanitization for
client name/logo (XSS prevention), a restrictive Content-Security-Policy, state tokens
in KV with short expiry, `__Host-`-prefixed cookies, and a per-user "approved clients"
registry keyed by HMAC-signed cookies.

### 4.2 Cloudflare Access "MCP server portals"

Separately, Cloudflare Access offers **MCP portals**, which "centralize multiple Model
Context Protocol (MCP) servers onto a single HTTP endpoint," acting as an aggregating
gateway in front of several upstream MCP servers, with tool visibility and auth managed
centrally
([MCP server portals](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/)).
This is the piece most directly analogous to "a non-Docker gateway": instead of Docker's
sandbox gateway being the only aggregation point, a Cloudflare MCP portal can itself
aggregate several upstream MCP servers behind one URL, and *that* portal URL is what gets
registered into the sandbox with `sbx mcp add <name> --url https://<portal>.<domain>/mcp`
— giving a "gateway behind a gateway" topology (sandbox gateway → Cloudflare portal →
individual MCP servers).

The portal documents supporting **both** auth patterns discussed in §5:

- **Dynamic Client Registration (automatic)**: "When an MCP server supports dynamic
  registration, Cloudflare automatically handles the OAuth flow," using admin credentials
  captured at setup time to periodically resync tools/prompts (roughly every two hours).
- **Manual OAuth (pass-through / per-user)**: "For servers not supporting dynamic
  registration, administrators manually register OAuth credentials with the upstream
  provider," and users then authenticate directly, per-server, through the portal.

Client connection flow: the MCP client requests `https://<subdomain>.<domain>/mcp`, gets
a `401` with OAuth discovery metadata, the user authenticates via the org's Cloudflare
Access identity provider (plus any additional per-server OAuth for servers using the
manual/pass-through pattern), and the portal then returns the aggregated tool set from
the enabled upstream servers.

## 5. Pass-through auth vs. Dynamic Client Registration (DCR) — the spec-level picture

The current MCP authorization specification (`2025-11-25`) defines three client
registration mechanisms and a priority order for choosing among them
([MCP spec — Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization);
background on the shift away from DCR-by-default:
[Evolving OAuth Client Registration in MCP](https://blog.modelcontextprotocol.io/posts/client_registration/),
[Den Delimarsky: What's new in the 2025-11-25 spec](https://den.dev/blog/mcp-november-authorization-spec/)):

1. **Pre-registration** — client and server already have a relationship; the client uses
   a hardcoded/pre-issued `client_id` (and secret, if confidential), or the user manually
   registers an OAuth client via the server's own config UI and supplies the id. This is
   what `sbx mcp add ... --client-id <CLIENT_ID>` implements (§3), and it's the closest
   analogue to what people informally call "pass-through" auth — a human/admin sets up the
   OAuth client once, out of band, rather than the protocol negotiating it live.
2. **Client ID Metadata Documents (CIMD)** — newest mechanism; the client hosts a JSON
   metadata document at an HTTPS URL and uses that URL itself as the `client_id`. The
   authorization server fetches and validates the document (checking `client_id`,
   `redirect_uris`, etc.) instead of requiring a registration round-trip. Servers
   advertise support via `client_id_metadata_document_supported: true` in their OAuth
   Authorization Server metadata. This is now the **preferred** option in the spec for
   the common case where client and server have no prior relationship.
3. **Dynamic Client Registration (DCR, RFC 7591)** — the client `POST`s to a
   `/register` endpoint and gets back a fresh `client_id` with no human involved,
   discovered via a `registration_endpoint` field in the authorization server's metadata.
   The spec now frames DCR as **retained mainly for backwards compatibility**, with CIMD
   as its likely long-term replacement — but real-world implementations (including
   Cloudflare's, per §4.2) still rely on it heavily today.

Clients that support all three **should** try them in order: pre-registered credentials
first, then CIMD if the authorization server advertises it, then DCR as a fallback, and
only prompt the human for manual client details if none of the above apply.

Separately, the spec is explicit that an MCP server must **not** forward ("pass through")
the *access token it received from its own client* to an upstream API unmodified — that
specific meaning of "token passthrough" is a named anti-pattern/security risk (the
"confused deputy" problem), distinct from the informal "pass-through auth" terminology
used above for manually pre-registered OAuth clients. Cloudflare's `workers-oauth-provider`
model is a legitimate implementation of "MCP server acts as its own OAuth client to the
upstream service" specifically to avoid this confusion — the token a caller uses against
the Cloudflare-hosted MCP server is not the same token the Worker uses against, say,
GitHub or Google upstream.

## 6. Anthropic/Claude Code side: connecting to a remote MCP server directly

Independent of Docker's sandbox gateway, Claude Code itself can register a remote MCP
server directly (bypassing any gateway) via:

```bash
claude mcp add --transport http <server-name> <server-url>
claude mcp add --transport http --scope local my-mcp-server https://your-mcp-server.com \
  --env API_KEY="your-api-key-here" --header "API_Key: ${API_KEY}"
```

Claude Code has "native OAuth support for remote MCP servers" so the user authenticates
once and Claude Code manages the token rather than requiring a stored API key
([Remote MCP support in Claude Code](https://claude.com/blog/claude-code-remote-mcp),
[Claude Code docs — Connect to MCP servers](https://code.claude.com/docs/en/mcp-quickstart)).
The Anthropic blog post did not go into DCR/CIMD/pre-registration specifics — it only
confirms OAuth is supported end-to-end for the user.

This is a second, simpler integration path worth contrasting with the `sbx mcp` path in
§2–3: `claude mcp add` talks to the remote endpoint directly from inside the sandbox
(subject to the sandbox's network egress policy only), with no host-side gateway,
registration governance, or shared-credential management — whereas `sbx mcp add` centralizes
registration and credentials on the host and is what the sandbox's MCP governance/Cedar
policies (§7) actually govern.

## 7. Note: registration governance also applies to remote/Cloudflare endpoints

Not core to this goal but directly relevant to whether a given non-Docker gateway can be
registered at all: Docker Sandboxes support organization-level Cedar policies that gate
`sbx mcp add`. Policies match on the resolved server's `identityURL`, so an org can
explicitly permit or forbid registering a specific remote endpoint (including a
Cloudflare-hosted one) by URL
([MCP access policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/mcp/)).
Example (illustrative syntax from that page):

```
permit (principal, action == MCP::Action::"register", resource)
when {
  resource in MCP::Server::"example" &&
  resource.identityURL == "https://mcp.example.com/mcp"
};

forbid (principal, action == MCP::Action::"register", resource)
when { resource.identityURL == "https://mcp.example.com/mcp" };
```

Registration policy changes are forward-only: they govern future `sbx mcp add` calls and
do not retroactively remove an already-saved registration or block `sbx mcp load` of one
that was previously approved. (This overlaps with, but is distinct from, this repo's goal
3 on Cedar-based tool-access policy — flagged here only because it gates whether a
non-Docker gateway can be added in the first place.)

## Open questions for this repo to answer experimentally

- Whether `sbx mcp add --url` against a Cloudflare **MCP portal** URL (as opposed to a
  single Cloudflare Worker-hosted MCP server) round-trips cleanly through the sandbox
  gateway's own OAuth handling, given the portal itself performs a second layer of
  per-upstream-server auth.
- Concrete behavior differences between `--skip-auth`, `--client-id` (pre-registration),
  and doing nothing (letting the sandbox gateway attempt CIMD/DCR against the Cloudflare
  endpoint's discovered authorization server).
- Whether registering the same Cloudflare endpoint via `claude mcp add --transport http`
  directly (§6) versus via `sbx mcp add` (§2–3) produces observably different token
  scoping/audience behavior, per the spec's resource-indicator (`RFC 8707`) requirements.

## Sources

- [Docker Sandboxes — MCP gateway](https://docs.docker.com/ai/sandboxes/mcp-gateway/)
- [Docker Sandboxes — Governance](https://docs.docker.com/ai/sandboxes/governance/)
- [Docker Sandboxes — MCP access policies](https://docs.docker.com/ai/sandboxes/governance/access-controls/mcp/)
- [Docker — MCP Gateway (Docker Desktop/Hub product)](https://docs.docker.com/ai/mcp-catalog-and-toolkit/mcp-gateway/)
- [Docker — MCP Toolkit](https://docs.docker.com/ai/mcp-catalog-and-toolkit/toolkit/)
- [Cloudflare Agents docs — Build a Remote MCP server](https://developers.cloudflare.com/agents/model-context-protocol/guides/remote-mcp-server/)
- [Cloudflare Agents docs — Securing MCP servers](https://developers.cloudflare.com/agents/model-context-protocol/guides/securing-mcp-server/)
- [Cloudflare One docs — MCP server portals](https://developers.cloudflare.com/cloudflare-one/access-controls/ai-controls/mcp-portals/)
- [Cloudflare blog — Build and deploy Remote MCP servers](https://blog.cloudflare.com/remote-model-context-protocol-servers-mcp/)
- [cloudflare/workers-oauth-provider (GitHub)](https://github.com/cloudflare/workers-oauth-provider)
- [Model Context Protocol specification (2025-11-25) — Authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [MCP blog — Evolving OAuth Client Registration in the Model Context Protocol](https://blog.modelcontextprotocol.io/posts/client_registration/)
- [Den Delimarsky — What's New In The 2025-11-25 MCP Authorization Spec](https://den.dev/blog/mcp-november-authorization-spec/)
- [Claude — Remote MCP support in Claude Code](https://claude.com/blog/claude-code-remote-mcp)
- [Claude Code docs — Connect to MCP servers](https://code.claude.com/docs/en/mcp-quickstart)
