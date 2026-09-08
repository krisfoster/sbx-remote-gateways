# Plan: End-to-End Sandboxed Dev Loop (Goal 4)

This is a **planning document**, not the implementation specification itself. Its job is
to scope the goal, ground it in confirmed Docker Sandboxes mechanisms, and lay out the
outline the eventual `SPEC.md` (and, later, the actual demo project code) will follow.
Unlike goals 1–3, this goal produces a runnable artifact, not just a research write-up —
see the note on repo scope in `CLAUDE.md`.

## 1. Scope, as given

An agent (Claude, running inside a Docker Sandbox) builds and runs a simple self-hosted
Python web app, with:

- A **hello-world home page** — the only functional requirement on the app itself.
- **Playwright as a local MCP server**, added via `sbx mcp`, so the agent can visually
  check the site it is building as it works.
- A **declarative sandbox env/config file** that sets up **port forwarding**, so the
  running site is viewable from the host (browser on the host, or Playwright).
- A **boot script** that starts automatically when the sandbox boots, launching the app
  in **dev mode with live reload**, so edits the agent makes are reflected without a
  manual restart.

Explicitly out of scope for this planning doc: writing the actual Python app code, or the
final `SPEC.md` prose — both come after this plan is agreed.

## 2. Grounding: what's confirmed vs. inferred

Findings below are from public Docker documentation, fetched for this plan. Full source
list in §6. Each of the user's four requirements maps to a specific, named mechanism —
important because more than one superficially-similar mechanism exists for two of them
(port forwarding, boot hooks), and picking the wrong one silently breaks the demo.

### 2.1 Playwright as a local MCP server (`sbx mcp add`)

- Command shape: `sbx mcp add <name> (--url <url> | --command <cmd>) [flags]`, with
  `--command`/`--args` for a local stdio server
  ([`sbx mcp add`](https://docs.docker.com/reference/cli/sbx/mcp/add/)).
- **Confirmed but important**: a `--command` server runs as a **subprocess on the host**,
  not inside the sandbox. Docker's docs describe this local mode as "for ad-hoc
  development only" — no identity, no verifiable supply chain, no sandboxing — and note
  registrations are host-global and persist after the sandbox is removed
  ([`sbx mcp add`](https://docs.docker.com/reference/cli/sbx/mcp/add/)).
- **Architectural consequence**: because Playwright's browser process runs on the host,
  it cannot reach the app by a sandbox-internal address. It can only view the site once
  the dev server's port is **published to the host** (§2.2) and Playwright is pointed at
  `http://localhost:<published-host-port>`.
- **Not verified against docs.docker.com**: the exact invocation for `@playwright/mcp`.
  By analogy with the documented GitHub-server example
  (`sbx mcp add github --command npx --args @modelcontextprotocol/server-github`) plus
  Playwright's own published `npx @playwright/mcp@latest` invocation, the equivalent is
  inferred to be:
  ```bash
  sbx mcp add playwright --command npx --args "-y,@playwright/mcp@latest"
  ```
  **This needs to be tried against a real sandbox before it goes in `SPEC.md` as fact.**

### 2.2 Declarative port forwarding

Two distinct declarative surfaces exist with **different schemas** — the plan must pick
one and say so explicitly in `SPEC.md`, not conflate them:

- **`sbxenv.yaml`** (a project/user environment file — must live *outside* any directory
  mounted into the sandbox) supports a top-level `ports:` list:
  ```yaml
  ports:
    - sandbox: 3000
      host: 3000
  ```
  Fields: `sandbox` (required), `host` (optional — ephemeral if omitted), `protocol`,
  `hostIP` ([Environment files](https://docs.docker.com/ai/sandboxes/configuration/environment-files/)).
  This is also where `mcp.servers`, `kits:`, and `lifecycle:` live, so it's a natural
  single place to declare "everything about this sandbox" for the demo.
- **Kit `spec.yaml`** has its *own* `ports:` block, with different field names
  (`container` instead of `sandbox`), used when packaging the setup as a reusable kit
  rather than a one-off project env file
  ([Kit reference](https://docs.docker.com/ai/sandboxes/customize/kit-reference/)).
- Imperative fallback for comparison/debugging: `sbx ports <sandbox> --publish
  <host>:<container>` on a running/stopped sandbox (already documented in this
  repo's root `CLAUDE.md`).
- **Open question, not resolved in docs**: whether `ports` mappings survive a sandbox
  stop/restart cycle, or need to be re-declared/re-applied.

**Recommendation for `SPEC.md`**: use `sbxenv.yaml`'s `ports:` block, since the demo is a
single project, not a reusable kit — simpler and matches the "project-level env file"
framing in the user's request.

### 2.3 Boot-time startup script (dev server, live reload)

Two lifecycle mechanisms exist, running at **different times and in different places** —
picking the wrong one means the dev server either never starts, or starts on the host
instead of in the sandbox:

- **`lifecycle` block in `sbxenv.yaml`** (`initialize` / `postCreate` / `preRemove`) runs
  on the **host**, not inside the sandbox
  ([Environment files](https://docs.docker.com/ai/sandboxes/configuration/environment-files/)).
  **Not the right hook** for launching the dev server itself.
- **`setup.startup` in a kit's `spec.yaml`** runs **inside the sandbox**, on *every*
  sandbox start (not just creation), before the agent attaches:
  ```yaml
  setup:
    startup:
      - command: ["python", "-m", "http.server", "8000"]
        background: true
  ```
  `background: true` lets startup continue without waiting on it; commands are argv
  arrays (not shell-interpreted) and must be **idempotent**, since they replay on every
  restart. This exact shape appears in Docker's own kit examples for a background dev
  server ([Kit reference](https://docs.docker.com/ai/sandboxes/customize/kit-reference/),
  [Kit examples](https://docs.docker.com/ai/sandboxes/customize/kit-examples/)).

**Recommendation for `SPEC.md`**: this means the demo needs a small **mixin kit**
(referenced from `sbxenv.yaml`'s `kits:` list) purely to carry the `setup.startup` boot
command — the `ports:`/`mcp.servers:` declarations can stay directly in `sbxenv.yaml`,
but the boot hook itself must go in a kit's `spec.yaml`, since `sbxenv.yaml` has no
inside-the-sandbox startup hook of its own.

**Unresolved by docs, to test empirically**: how reliably/quickly the backgrounded
`setup.startup` process is listening before something (Playwright, a host browser)
tries to hit the port — may need a readiness check rather than assuming instant
availability.

### 2.4 The web app itself — decision not yet made

"Dev mode with live reloading" is a product requirement, not a Docker Sandboxes
mechanism, so it isn't something the research above resolves — `SPEC.md` needs to pick a
concrete approach and state the trade-off:

- Plain `python -m http.server` (used in Docker's own example above) has **no live
  reload** at all — closest to "self-hosted," least code, but doesn't satisfy the live-
  reload requirement on its own.
- Flask with `flask run --debug` (or `app.run(debug=True)`) auto-**restarts the process**
  on file changes, but does not push a browser refresh — the agent (via Playwright) would
  need to reload the page itself after editing.
- A framework/tool with true browser-push live reload (e.g. Flask + a livereload
  extension) satisfies the requirement most literally, at the cost of an extra
  dependency.

This is a decision for `SPEC.md` to make explicitly, not for this plan to preempt.

## 3. Proposed demo project layout

```
specs/sandbox-webapp-devloop/
  PLAN.md            # this file
  SPEC.md            # the implementation specification (next step)
  app/               # the actual Python web app (created once SPEC.md is agreed)
    ...
  sbxenv.yaml        # ports:, mcp.servers:, kits: — sandbox declarative config
  kit/               # mixin kit carrying the boot hook
    spec.yaml        # setup.startup: launches the dev server in the sandbox
```

`sbxenv.yaml` and `kit/` live under this spec's folder for now (self-contained goal 4
demo); if the demo later needs to be runnable from the repo root, that's a `SPEC.md`
decision, not this plan's.

## 4. Outline for `SPEC.md` (next step)

1. Overview & goal restatement
2. Web app: chosen framework, "hello world" route, live-reload mechanism and its
   limitations (§2.4 decision, made explicit)
3. `sbxenv.yaml`: full contents — `ports:`, `mcp.servers:` (Playwright), `kits:`
4. Boot hook: mixin kit `spec.yaml` with `setup.startup`, and why it's a separate kit
   rather than living in `sbxenv.yaml`'s `lifecycle:` (§2.3)
5. Playwright MCP registration: exact `sbx mcp add` invocation, verified against a real
   run (§2.1's open item), and how the agent uses it (navigate to
   `http://localhost:<port>`, screenshot/assert)
6. End-to-end walkthrough: boot sandbox → dev server up → agent edits app code → live
   reload (or restart) → agent re-checks via Playwright → host browser can also view it
7. Open questions carried over from this plan that remain unresolved after
   implementation/testing
8. Sources

## 5. Next steps

1. Confirm the web-app framework/live-reload choice (§2.4) — recommend asking the user
   only if it's not implied by "simple self-hosted Python web app" (a plain stdlib
   choice may be preferred over adding Flask as a dependency).
2. Stand up a real sandbox and verify the inferred `sbx mcp add playwright ...`
   invocation (§2.1) and the `setup.startup` readiness timing (§2.3) empirically.
3. Write `SPEC.md` following the outline in §4, updating any "inferred" items in this
   plan to "confirmed" (or correcting them) based on that empirical check.
4. Only then write the actual `app/`, `sbxenv.yaml`, and `kit/` files.

## 6. Sources

- [Docker Sandboxes CLI — `sbx mcp`](https://docs.docker.com/reference/cli/sbx/mcp/)
- [Docker Sandboxes CLI — `sbx mcp add`](https://docs.docker.com/reference/cli/sbx/mcp/add/)
- [Docker Sandboxes — Environment files](https://docs.docker.com/ai/sandboxes/configuration/environment-files/)
- [Docker Sandboxes — Kits](https://docs.docker.com/ai/sandboxes/customize/kits/)
- [Docker Sandboxes — Kit reference](https://docs.docker.com/ai/sandboxes/customize/kit-reference/)
- [Docker Sandboxes — Kit examples](https://docs.docker.com/ai/sandboxes/customize/kit-examples/)
- [Docker Sandboxes — Get started](https://docs.docker.com/ai/sandboxes/get-started/)
- [Docker Sandboxes — Usage](https://docs.docker.com/ai/sandboxes/usage/)
