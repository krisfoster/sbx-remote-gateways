# Research: `sbx --cloud` — Moving a Docker Sandbox to the Cloud and Back, and What Happens to MCP/Auth

Scope: goal 2 — "Cloud hand-off: what it looks like, what MCP/auth limitations exist".

**Correction from an earlier version of this document**: "cloud hand-off" for this repo
means Docker Sandboxes' own **`sbx --cloud`** feature — the ability to run a sandbox on
Docker-managed cloud infrastructure instead of (or in addition to) locally, and to move a
sandbox's filesystem between the two with `sbx move`. An earlier draft of this research
investigated Claude Code's own, unrelated `claude --cloud`/`--teleport` feature (which
runs sessions on *Anthropic*-managed infrastructure and has nothing to do with `sbx`).
That content has been removed. It's worth keeping in mind that both features exist and
happen to share the word "cloud" — a session that is inside a `sbx --cloud` sandbox could
still separately use Claude Code's own `--cloud`/`--teleport`, and the two are fully
independent — but this document is scoped to `sbx --cloud` only, per the actual goal.

## 1. What `sbx --cloud` is, per the public record

**Finding, stated up front**: as of this research, `sbx --cloud` is a very recently
shipped feature, and Docker's prose documentation (`docs.docker.com/ai/sandboxes/...`)
has not yet caught up to it. I checked the sandboxes documentation index, `usage`,
`faq`, `workflows`, `configuration`, `architecture`, and `governance` pages, plus the
`docker/docs` GitHub repo's file listing for the sandboxes section — none of them mention
cloud sandboxes, `sbx --cloud`, or `sbx move`. The only public source that documents this
feature is the **`docker/sbx-releases` GitHub release notes**
([releases](https://github.com/docker/sbx-releases/releases)), specifically the entry for
**v0.42.0**, dated **2026-09-07** — i.e. released the day before this research was
conducted. Treat everything below as an accurate summary of that one source, not as
confirmed, stable, documented behavior — the deeper mechanics in §3 are genuinely
open questions, not gaps in my research.

### What the release notes say `sbx --cloud` does

- **Run an agent in the cloud**: `sbx --cloud run claude --name cloud-project` — runs the
  agent on Docker-managed cloud infrastructure rather than the local microVM.
- **Move a sandbox's filesystem between environments**: `sbx move` — "copy a sandbox
  filesystem between local and cloud environments." This is the literal "move a running
  sandbox to the cloud, and back again" mechanism.
- **Transfer files, publish services, and connect interactively**: "Transfer files with
  `sbx --cloud cp`, publish services through public HTTPS URLs, and connect using SSH."
- **Cloud-specific credentials**: `sbx --cloud secret` — configure credentials scoped to
  the cloud environment.
- **Cloud-specific network policy**: `sbx --cloud policy` — configure outbound network
  restrictions scoped to the cloud environment.
- **Separate resource/credential/policy scope, stated explicitly**: "Cloud sandboxes have
  separate resources, credentials, and network policies from local sandboxes."
- **Billing**: "Cloud compute requires an active Docker Agentic Platform plan and is
  billed based on usage." Model inference is billed separately by the model provider, as
  with local sandboxes.

Co-released in the same v0.42.0 changelog, though not stated to be specific to cloud
sandboxes:

- "Fixed a gateway defect where a remote MCP server's reconnect could silently wipe its
  tool routing" — a general MCP gateway bug fix.
- "`sbx mcp auth` now requests only the scopes you chose" — a general OAuth-scope-request
  narrowing fix for `sbx mcp auth` (see [goal 1's research](../remote-mcp-gateways/RESEARCH.md)
  for the `--scope` flags this improves).

## 2. Direct implication for MCP/auth: local and cloud are separate scopes

The single most load-bearing sentence in the release notes for this goal is: **"Cloud
sandboxes have separate resources, credentials, and network policies from local
sandboxes."** Read together with the existence of parallel, cloud-prefixed subcommands
(`sbx --cloud secret`, `sbx --cloud policy`, as distinct from plain `sbx secret` and
`sbx policy`), this points to a clear, testable conclusion:

- **MCP server registrations and OAuth grants are per-environment, not global.** A remote
  MCP gateway registered locally with `sbx mcp add <name> --url <url>` and authorized with
  `sbx mcp auth <name>` (see goal 1) has no stated mechanism for automatically being
  available to a cloud-run sandbox. The cloud side would need its own registration/auth —
  and since `sbx --cloud secret` exists specifically to hold "cloud-specific credentials,"
  a client secret or OAuth client id set locally via `sbx secret set mcp:<server>.client_secret`
  would need to be set again via `sbx --cloud secret set mcp:<server>.client_secret` for a
  cloud sandbox to use it. Nothing in the release notes states this is automated.
- **Network egress allow/deny is per-environment, not global.** A remote MCP gateway's
  domain allow-listed locally via `sbx policy allow network <domain>` is a **local**
  policy rule; reaching that same domain from a cloud sandbox would need the equivalent
  `sbx --cloud policy allow network <domain>`, per the existence of a distinct
  `sbx --cloud policy` subcommand.
- **It is not yet established whether `sbx move` carries MCP/auth state with it.**
  `sbx move` is described as copying "a sandbox filesystem" — i.e. the sandbox's
  workspace/container state. The MCP server registry, OAuth tokens, and credentials that
  `sbx mcp add`/`sbx mcp auth`/`sbx secret set` manage are described elsewhere (goal 1's
  research) as living on the **host** the gateway runs on, not inside the sandboxed
  workspace filesystem itself. If that's still true for cloud sandboxes, a filesystem-level
  `sbx move` would plausibly **not** bring MCP registrations, OAuth grants, or secrets with
  it — those would need to be independently present in the destination environment's own
  `sbx mcp`/`sbx secret`/`sbx policy` scope. This is inference from the two features'
  documented shapes, not a confirmed behavior — see the open questions in §3.
- **Org-level Cedar MCP governance (goal 3) is authored centrally, so it most plausibly
  applies to both scopes uniformly** — the same reasoning documented for org network and
  filesystem policy ("Sandbox network and filesystem policies defined in the Docker Admin
  Console apply uniformly to every sandbox in the organization... take precedence over
  local `sbx policy` rules") would extend naturally to a cloud sandbox, since Cedar MCP
  policy is described as an organization-wide control rather than a per-machine one to
  begin with. The release notes don't confirm this explicitly for cloud sandboxes, so
  it's stated here as a plausible extrapolation, not a documented fact.

## 3. Open questions for this repo to answer experimentally

Because the only public documentation is a one-paragraph release-note summary, this repo
is well positioned to be one of the first places these questions get answered concretely.
Recommended experiments, roughly in order of how directly they test the goal:

1. **Does `sbx move` require stopping the sandbox first, or does it work on a running
   sandbox?** The user's framing of this goal ("move a *running* sandbox to the cloud")
   implies live migration; confirm via `sbx move --help` and by trying it against a
   sandbox with an active Claude Code session and pending agent state.
2. **Does a remote MCP gateway registered and authorized locally (goal 1's
   `sbx mcp add --url ... && sbx mcp auth ...`) remain callable immediately after
   `sbx move` or inside a fresh `sbx --cloud run` session** — or does the agent see the
   server as unregistered/unauthorized until `sbx --cloud secret`/equivalent cloud-side
   registration is repeated?
3. **Does a secret set with plain `sbx secret set` need to be duplicated with
   `sbx --cloud secret set` for a cloud sandbox to use it**, and is there any documented
   or observed sync/copy command, or is this strictly manual duplication?
4. **Does `sbx --cloud policy` start from the same baseline (`balanced`/`open`/`locked-down`)
   as local `sbx policy`, and does it need the destination MCP gateway's domain
   allow-listed separately**, the way goal 1 requires for local sandboxes?
5. **Does an org's Cedar MCP access policy (goal 3) actually apply to `sbx --cloud`
   sessions**, or is cloud-sandbox MCP governance out of scope for that policy engine
   today (e.g. because it's a newer feature that policy enforcement hasn't caught up
   with yet)?
6. **What, precisely, does "publish services through public HTTPS URLs" mean for a
   cloud-run MCP server** — i.e., could a cloud sandbox itself be made to host and expose
   a remote MCP endpoint (tying back into goal 1's "non-Docker remote gateway" scenario,
   just hosted by `sbx --cloud` instead of Cloudflare)?

## Sources

- [docker/sbx-releases — Releases](https://github.com/docker/sbx-releases/releases)
  (primary source: the v0.42.0 entry, dated 2026-09-07)
- [docker/sbx-releases — v0.42.0 tag](https://github.com/docker/sbx-releases/releases/tag/v0.42.0)
- [Docker Sandboxes — documentation index](https://docs.docker.com/ai/sandboxes/) (checked; no cloud/move content found as of this research)
- [Docker Sandboxes — Usage](https://docs.docker.com/ai/sandboxes/usage/) (checked; no cloud/move content found)
- [Docker Sandboxes — FAQ](https://docs.docker.com/ai/sandboxes/faq/) (checked; no cloud/move content found)
- [Docker Sandboxes — Workflows](https://docs.docker.com/ai/sandboxes/workflows) (checked; no cloud/move content found)
- [Docker Sandboxes — Configuration](https://docs.docker.com/ai/sandboxes/configuration) (checked; no cloud/move content found)
- [docker/docs — content/manuals/ai/sandboxes (GitHub source tree)](https://github.com/docker/docs/tree/main/content/manuals/ai/sandboxes) (checked; no cloud.md/move.md file present)

## Note on absence of non-public information

Nothing in this research came from anything other than the public `docker/sbx-releases`
GitHub repository and public `docs.docker.com` pages. There is no separate confidential
finding to report for this update — the main finding *is* that public documentation for
this feature is currently thin, which is itself the reason §3's questions are open rather
than answered.
