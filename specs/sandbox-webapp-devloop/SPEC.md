# Spec: Sandboxed Python Web App Dev Loop (Goal 4)

This is the implementation specification for goal 4, following the outline in
[`PLAN.md`](./PLAN.md) §4. Where `PLAN.md` flagged something as inferred rather than
docs-confirmed, this spec makes the concrete choice explicit and carries the caveat
forward into §7 rather than silently resolving it.

## 1. Overview & goal restatement

An agent (Claude) runs inside a Docker Sandbox and builds/runs a simple, self-hosted
Python web app with a hello-world home page. The sandbox is configured so that:

- The app's dev server starts automatically when the sandbox boots, in a mode that picks
  up code edits without a manual restart.
- The dev server's port is forwarded to the host, so the running site is visible both
  from a host browser and from Playwright.
- Playwright is registered as a local MCP server, so the agent can navigate to the app
  and visually verify what it just built/changed, as part of its own workflow.

## 2. Web app: framework, route, live-reload mechanism

**Decision**: Flask, run via its built-in development server with the debugger/reloader
enabled (`debug=True`), rather than plain `python -m http.server` or a Flask+livereload
combination. Rationale, carrying forward the trade-off `PLAN.md` §2.4 identified:

- Plain `http.server` has no reload of any kind — it fails the "live reloading" part of
  the requirement outright, so it's ruled out despite being the smallest possible option.
- A Flask + browser-push livereload extension satisfies "live reload" most literally, but
  adds a second dependency and moving part for a hello-world app; not justified yet.
- Flask alone, with its reloader, is one dependency, is still "simple," and satisfies the
  practical goal: the agent edits `app.py` (or a template), the process restarts itself,
  and the next request serves the new content.

**Explicit limitation** (carried to §6): Flask's reloader restarts the **process** on
file changes; it does not push a refresh to an already-open browser tab or Playwright
page. The agent's verification step must issue a fresh navigation/request after an edit,
not assume an open page updates itself. ([Flask — development server / debug
mode](https://flask.palletsprojects.com/en/stable/quickstart/#debug-mode))

**Route**: a single `GET /` route returning a minimal HTML page containing the text
`Hello, world!` — enough for both a human loading the page and Playwright's accessibility
snapshot/text content check to confirm the app is up and serving the expected content.

**Files**:

```
specs/sandbox-webapp-devloop/app/
  app.py             # Flask app: one route, __main__ runs app.run(debug=True, host="0.0.0.0", port=8000)
  requirements.txt   # flask
```

`host="0.0.0.0"` is required, not optional: the dev server must listen on the sandbox's
`eth0` interface (all interfaces), not just its own loopback, or the port-forwarding in
§3 has nothing reachable to forward to — matching this repo's root `CLAUDE.md` guidance
on binding addresses for published ports.

## 3. `sbxenv.yaml`: ports, MCP servers, kits

Per `PLAN.md` §2.2, port forwarding is declared in the project `sbxenv.yaml` (not a
kit's `spec.yaml`), since this is a single project, not a reusable kit. Per §2.1, the
Playwright MCP server is also declared here as an `mcp.servers` entry rather than added
imperatively, so the whole sandbox setup is reproducible from one file:

```yaml
# specs/sandbox-webapp-devloop/sbxenv.yaml
ports:
  - sandbox: 8000
    host: 8000

mcp:
  servers:
    - name: playwright
      command: npx
      args: ["-y", "@playwright/mcp@latest"]

kits:
  - ./kit
```

Field provenance: `ports[].sandbox`/`ports[].host` match the documented `sbxenv.yaml`
schema exactly ([Environment
files](https://docs.docker.com/ai/sandboxes/configuration/environment-files/)). The
`mcp.servers` entry's field names (`name`, `command`, `args`) are **inferred by analogy**
with the equivalent `sbx mcp add` CLI flags (`--command`, `--args`) — `PLAN.md` §2.1
flagged that no docs.docker.com example of the `mcp.servers` YAML block (as opposed to
the CLI form) was found during research. This needs verification against a real sandbox
before being treated as confirmed (tracked in §7).

`sbxenv.yaml` must live outside any directory that gets mounted into the sandbox as the
workspace, per the documented constraint in `PLAN.md` §2.2 — i.e. at
`specs/sandbox-webapp-devloop/sbxenv.yaml`, a sibling of (not inside) the mounted
`app/`/`kit/` workspace, if the workspace root for this demo is `app/`. This placement
decision should be re-checked once a real sandbox is stood up, since it depends on which
directory ends up as the actual `sbx run` workspace argument (open question, §7).

## 4. Boot hook: mixin kit with `setup.startup`

Per `PLAN.md` §2.3, `sbxenv.yaml`'s `lifecycle` block runs on the **host**, so it cannot
launch the in-sandbox dev server. The boot hook instead lives in a small mixin kit,
referenced from `sbxenv.yaml`'s `kits:` list above:

```yaml
# specs/sandbox-webapp-devloop/kit/spec.yaml
kind: mixin
name: goal-4-dev-server

setup:
  startup:
    - command: ["sh", "-c", "cd /workspace/app && flask --app app.py run --host=0.0.0.0 --port=8000 --debug"]
      background: true
      description: "Start the Flask dev server (debug/live-reload) for the goal 4 hello-world app"
```

Two things about this command are worth calling out rather than leaving implicit:

- `setup.startup` commands are **argv arrays, not shell-interpreted**
  (`PLAN.md` §2.3). Since starting the app requires changing into the app's directory
  first, the command wraps the real invocation in `sh -c "..."` — a single argv entry
  that itself invokes a shell, which is the standard way to get `cd`-then-run semantics
  out of an argv-only hook. This assumes a POSIX shell (`sh`) is present in the sandbox
  image, which is true for essentially every Linux container base but is not something
  Docker's kit docs state explicitly for `setup.startup` — noted as an assumption, §7.
- `background: true` is required so the startup dispatcher doesn't block waiting for a
  long-running dev server to exit (`PLAN.md` §2.3). Since the command must be
  **idempotent** across sandbox restarts, `flask run` is safe here — it doesn't mutate
  persistent state, it just (re)binds a port each time the sandbox (re)starts.

The literal `/workspace/app` path assumes the sandbox's workspace mount point is
`/workspace` and that `app/` sits at its root — this needs confirming against how the
sandbox is actually invoked (`sbx run <workspace-path> ...`) once §7's open items are
resolved; it is not a documented, fixed path in Docker's kit docs.

## 5. Playwright MCP registration

Registering Playwright as a local MCP server, per `PLAN.md` §2.1:

```bash
sbx mcp add playwright --command npx --args "-y,@playwright/mcp@latest"
```

This mirrors `sbxenv.yaml`'s `mcp.servers` entry in §3 — the CLI form is the fallback/
manual-testing path, the YAML form is the reproducible one actually used by the sandbox.
The `npx -y @playwright/mcp@latest` invocation itself (not the `sbx mcp add` wrapping) is
Playwright's own documented way to run its MCP server
([microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)) — that part is
confirmed; the `sbx mcp add ... --args "-y,@playwright/mcp@latest"` **wrapping syntax**
is the part `PLAN.md` flagged as not docs-verified (§7).

**How the agent uses it, given §2.1's architectural point that the Playwright browser
runs on the host, not in the sandbox**: the agent calls the Playwright MCP server's
navigation tool against `http://localhost:8000/` — the **published host port** from §3,
not any sandbox-internal address, since the host-side Playwright process cannot resolve
or reach the sandbox's internal network. A typical verification step:

1. Navigate to `http://localhost:8000/`.
2. Take an accessibility snapshot (or screenshot) of the page.
3. Assert the text `Hello, world!` is present.
4. After making a code edit, repeat steps 1–3 — a fresh navigation, not a reused page
   handle — per §2's note that Flask's reloader doesn't push updates to an open tab.

## 6. End-to-end walkthrough

1. Sandbox boots from this project's `sbxenv.yaml` (`ports`, `mcp.servers`, `kits: [./kit]`).
2. The `goal-4-dev-server` kit's `setup.startup` hook runs inside the sandbox, starting
   Flask in debug mode on `0.0.0.0:8000`, backgrounded so the sandbox continues starting
   up (§4).
3. `sbxenv.yaml`'s `ports` entry forwards sandbox port 8000 to host port 8000 (§3), and
   its `mcp.servers` entry (or the equivalent `sbx mcp add`, §5) registers the Playwright
   MCP server as a host subprocess.
4. The agent, working inside the sandbox, edits `app/app.py` (or a template) to change
   the home page.
5. Flask's reloader restarts the dev server process in place, picking up the change —
   still bound to the same forwarded port, no re-publishing needed.
6. The agent calls the Playwright MCP server to navigate to `http://localhost:8000/`
   and confirms the change is live (§5's steps 1–4).
7. A human can independently open `http://localhost:8000/` in a host browser at any
   point and see the same live site, since the same forwarded port serves both.

## 7. Open questions carried into implementation/testing

All of the following were inferred by analogy or assumption rather than confirmed
against Docker's published docs, and should be resolved (confirmed, corrected, or
documented as genuinely undocumented) once a real sandbox is stood up for this goal:

- **`mcp.servers` YAML schema** (§3): field names (`name`/`command`/`args`) are inferred
  from the `sbx mcp add` CLI flags, not from a docs.docker.com YAML example.
- **`sbx mcp add` Playwright invocation** (§5): the exact `--args "-y,@playwright/mcp@latest"`
  wrapping is untested against a real `sbx mcp add` call.
- **Workspace mount path** (§3, §4): `/workspace/app` is assumed, not confirmed — depends
  on how this project is actually passed to `sbx run`/`sbx create`, which also determines
  where `sbxenv.yaml` needs to sit relative to the mounted directory.
- **Shell availability for `setup.startup`** (§4): assumes `sh` is present in the sandbox
  image for the `sh -c "..."` wrapping; not stated either way in Docker's kit docs.
- **Startup readiness timing** (carried from `PLAN.md` §2.3): no documented guarantee of
  how soon a backgrounded `setup.startup` process is actually listening. If Playwright's
  first navigation races the Flask server coming up, the verification steps in §5 may
  need a short retry/backoff rather than a single attempt.
- **Port-mapping persistence across restarts** (carried from `PLAN.md` §2.2): whether the
  `ports` mapping in §3 needs to be re-declared/re-applied after a sandbox stop/restart,
  or persists automatically, is not stated in the docs reviewed so far.

## 8. Sources

- [Docker Sandboxes CLI — `sbx mcp`](https://docs.docker.com/reference/cli/sbx/mcp/)
- [Docker Sandboxes CLI — `sbx mcp add`](https://docs.docker.com/reference/cli/sbx/mcp/add/)
- [Docker Sandboxes — Environment files](https://docs.docker.com/ai/sandboxes/configuration/environment-files/)
- [Docker Sandboxes — Kits](https://docs.docker.com/ai/sandboxes/customize/kits/)
- [Docker Sandboxes — Kit reference](https://docs.docker.com/ai/sandboxes/customize/kit-reference/)
- [Docker Sandboxes — Kit examples](https://docs.docker.com/ai/sandboxes/customize/kit-examples/)
- [Docker Sandboxes — Get started](https://docs.docker.com/ai/sandboxes/get-started/)
- [Docker Sandboxes — Usage](https://docs.docker.com/ai/sandboxes/usage/)
- [microsoft/playwright-mcp](https://github.com/microsoft/playwright-mcp)
- [Flask — Quickstart: debug mode](https://flask.palletsprojects.com/en/stable/quickstart/#debug-mode)
