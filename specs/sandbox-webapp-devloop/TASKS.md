# Tasks: Implementing Goal 4 (Sandboxed Python Web App Dev Loop)

Implementation checklist derived from [`PLAN.md`](./PLAN.md) and [`SPEC.md`](./SPEC.md).
Ordered so that each phase's open questions are resolved *before* the next phase
depends on the answer — several `SPEC.md` §7 items (workspace mount path, shell
availability, `mcp.servers` schema) block later steps if left unverified, so they're
pulled forward into Phase 0 rather than discovered mid-build.

Check off items as they're done; where a task resolves one of `SPEC.md` §7's open
questions, update that section (confirm, correct, or mark genuinely undocumented) as
part of the task, not as separate cleanup later.

**Status**: `sbx` is a host-side CLI and is not available from inside the sandbox this
repo is being edited in — so Phase 0 (stand up a throwaway sandbox, run real `sbx`
commands) and the runtime parts of Phases 3–5 (booting a sandbox, checking a forwarded
port from the host, driving Playwright against it) could not be executed here and remain
**blocked on you running them on your host**. Phases 1–3's *file authoring* is done, and
Phase 1's app logic was sanity-checked locally with a plain `python`/`flask` process
(not a sandbox) standing in for the real thing. See inline notes below for exactly what
was and wasn't verified.

## Phase 0 — Resolve blocking unknowns before writing files

**Blocked — requires host-side `sbx` access, not available from inside this sandbox.**
The files below were written using the assumptions `SPEC.md` §3–5 already flagged as
inferred; treat them as a first draft to validate, not confirmed fact.

- [ ] Stand up a throwaway sandbox for this goal and determine its actual workspace
      mount path (`sbx run <path> ...` / `sbx create` output) — confirms or corrects the
      `/workspace/app` assumption in `SPEC.md` §3–4.
- [ ] From inside that sandbox, confirm a POSIX shell (`sh`) is present, needed for the
      `sh -c "cd ... && flask run ..."` wrapping in `SPEC.md` §4.
- [ ] Run `sbx mcp add playwright --command npx --args "-y,@playwright/mcp@latest"`
      against the throwaway sandbox and confirm it registers and starts correctly
      (`SPEC.md` §5's flagged-as-unverified invocation).
- [ ] Check `sbx mcp --help` / `sbx run --help` (or docs) for a documented `sbxenv.yaml`
      `mcp.servers` example; confirm or correct the inferred `name`/`command`/`args`
      field names used in `SPEC.md` §3.
- [ ] Tear down the throwaway sandbox once the above are confirmed, so it doesn't linger
      as untracked state.

## Phase 1 — Web app scaffolding

- [x] Create `specs/sandbox-webapp-devloop/app/app.py`: single Flask app, one `GET /`
      route returning HTML containing `Hello, world!`, `__main__` block calling
      `app.run(debug=True, host="0.0.0.0", port=8000)` (`SPEC.md` §2).
- [x] Create `specs/sandbox-webapp-devloop/app/requirements.txt` with `flask` pinned to a
      specific version. Pinned to `flask==3.1.3`, the version `pip install flask`
      resolved to at the time of writing.
- [x] Locally (outside the sandbox, for a fast sanity check) `pip install -r
      requirements.txt` in a scratch venv and run the app; confirm `curl localhost:8000/`
      returns the expected HTML before involving the sandbox at all. Done in this
      environment's own Linux userspace (not a Docker Sandbox — `sbx` isn't reachable
      from here): `curl localhost:8000/` returned the hello-world HTML, and editing the
      greeting text while the server ran confirmed Flask's reloader picks up the change
      without a manual restart, matching `SPEC.md` §2's live-reload claim. Scratch venv
      and process were cleaned up afterward.

## Phase 2 — `sbxenv.yaml`

- [x] Write `specs/sandbox-webapp-devloop/sbxenv.yaml` per `SPEC.md` §3: `ports`
      (sandbox 8000 → host 8000), `mcp.servers` (playwright entry, using whatever schema
      Phase 0 confirmed), `kits: [./kit]`. Written using `SPEC.md`'s inferred schema
      (Phase 0 wasn't run — see Status note above); **not yet validated against a real
      sandbox**.
- [ ] Confirm its placement relative to the sandbox's workspace mount (per Phase 0's
      finding) — move it if the workspace root turns out to differ from what `SPEC.md`
      §3 assumed. **Blocked on Phase 0.**

## Phase 3 — Boot hook (mixin kit)

- [x] Write `specs/sandbox-webapp-devloop/kit/spec.yaml` per `SPEC.md` §4: `kind: mixin`,
      `setup.startup` entry running Flask via `sh -c "..."`, `background: true`. Written
      as drafted in `SPEC.md`; **not yet validated against a real sandbox**.
- [ ] Update the hardcoded path inside that command to match Phase 0's confirmed
      workspace mount path (replace `/workspace/app` if it turned out to be wrong).
      **Blocked on Phase 0.**
- [ ] Boot a sandbox from this project (`sbxenv.yaml` + `kit/`) and confirm the dev
      server actually comes up automatically, without manually running `flask run`.
      **Blocked — requires host-side `sbx`.**

## Phase 4 — Port forwarding & host visibility

**Blocked — requires host-side `sbx` and a running sandbox; not executable from here.**

- [ ] From the host, `curl http://localhost:8000/` (or open in a browser) and confirm
      the hello-world page loads via the forwarded port (`SPEC.md` §3, §6 step 7).
- [ ] Restart the sandbox (stop/start, not recreate) and re-check the port still
      forwards without re-declaring anything — resolves the "port-mapping persistence"
      open question in `SPEC.md` §7.

## Phase 5 — Playwright MCP verification loop

**Blocked — requires a running sandbox with the Playwright MCP server registered; not
executable from here.**

- [ ] Confirm the Playwright MCP server (registered via `sbxenv.yaml`'s `mcp.servers` or
      the Phase 0-verified `sbx mcp add` command) is available to the agent inside the
      sandbox.
- [ ] From the agent, use the Playwright MCP tools to navigate to
      `http://localhost:8000/`, take an accessibility snapshot, and assert
      `Hello, world!` is present (`SPEC.md` §5 steps 1–3).
- [ ] Make a visible edit to `app/app.py` (change the greeting text), confirm Flask's
      reloader restarts the process (check logs/timestamps), then repeat the
      navigate-and-assert step with a **fresh** navigation and confirm the new text
      appears (`SPEC.md` §5 step 4, §6 steps 4–6) — also resolves the "startup readiness
      timing" question if a retry/backoff turns out to be necessary.

## Phase 6 — Close out documentation

- [ ] Update `SPEC.md` §7: for each open question, replace it with the confirmed
      behavior (or explicitly mark it as still-undocumented-upstream if genuinely
      unresolved after testing), citing the sandbox run itself as the source where the
      public docs didn't say.
- [ ] Update `PLAN.md` §5 "Next steps" to reflect what's now done vs. still pending.
- [ ] Add a short "Status" note at the top of `SPEC.md` once the full walkthrough
      (`SPEC.md` §6) has been run end-to-end successfully at least once.
