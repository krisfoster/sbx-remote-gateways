# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

This repo is primarily documentation/research, plus one buildable demo (goal 4). It
demonstrates and investigates four things about Docker Sandboxes (`sbx`) — see
`docs/goals.md` for the canonical statement of each goal:

1. **`specs/remote-mcp-gateways/`** — using remote MCP gateways other than Docker's own,
   specifically Cloudflare; pass-through auth vs. Dynamic Client Registration (DCR).
2. **`specs/cloud-handoff/`** — `sbx --cloud` (moving a running sandbox to Docker-managed
   cloud infrastructure and back with `sbx move`), and what MCP/auth limitations exist
   across that hand-off.
3. **`specs/local-mcp-cedar-policies/`** — Docker Sandboxes' Cedar-based MCP governance:
   controlling tool access and restricting plugin/MCP additions from within a sandbox.
4. **`specs/sandbox-webapp-devloop/`** — an end-to-end demo: an agent inside a Docker
   Sandbox builds and runs a simple self-hosted Python web app, with Playwright as a
   local MCP server (`sbx mcp add`) for visual verification, declarative port forwarding
   for host visibility, and a boot-time hook that launches the dev server with live
   reload. Unlike goals 1–3, this folder's output is a runnable project (app code,
   `sbxenv.yaml`, a kit), not only a `RESEARCH.md` — see its `PLAN.md` for the outline.

Each goal has its own folder under `specs/`, matching the numbered list above 1:1. The
folder names don't literally match the goal wording in `docs/goals.md` — check this
mapping before creating a new folder for what might already be covered ground.

## Research conventions

Each `specs/<goal>/RESEARCH.md` is the running, factual write-up for that goal. Goal 4 is
the exception: `specs/sandbox-webapp-devloop/` carries a `PLAN.md`/`SPEC.md` plus actual
project files instead of a `RESEARCH.md`, since its deliverable is a runnable demo — but
every factual claim in those docs about Docker Sandboxes behavior still follows the same
citation discipline below. When extending or updating this research:

- **Public sources only.** Cite only publicly accessible documentation (official vendor
  docs, public GitHub repos/issues, public specs). Never include information that is
  internal/confidential to Docker or Anthropic in a `RESEARCH.md` file — if something
  relevant but non-public turns up, report it to the user separately in conversation
  instead of writing it into the doc.
- **Cite everything.** Every factual claim should trace to a linked source; each doc ends
  with a "Sources" list of every URL cited inline.
- **Be explicit about documentation gaps.** When a feature is new/undocumented (as with
  `sbx --cloud`, whose only public source at the time of writing was GitHub release notes
  rather than `docs.docker.com` prose), say so plainly rather than inferring confidently.
  Distinguish confirmed facts from reasoned inference, and end with an "Open questions"
  section for anything this repo could answer experimentally but the public docs don't
  yet confirm.
- **Cross-reference, don't duplicate.** The three goals overlap (e.g. goal 2's hand-off
  questions depend on goal 1's MCP registration model and goal 3's Cedar governance) —
  link to the other goal's `RESEARCH.md` rather than re-explaining its content.

## Structure

```
docs/goals.md                              # canonical statement of the four repo goals
specs/remote-mcp-gateways/RESEARCH.md
specs/cloud-handoff/RESEARCH.md
specs/local-mcp-cedar-policies/RESEARCH.md
specs/sandbox-webapp-devloop/PLAN.md       # goal 4: planning doc; SPEC.md + app code follow
```

No build, lint, or test tooling exists for goals 1–3 — there is no code to run there.
Goal 4 will eventually contain a runnable Python web app; see its `PLAN.md`.
