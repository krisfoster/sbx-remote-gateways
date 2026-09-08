# Goals

This repo demonstrates:

- Use of remote MCP gateways other than Docker's own, specifically Cloudflare; pass-through vs. client registration (DCR)
- Cloud hand-off: what it looks like, what MCP/auth limitations exist
- Local MCP server Cedar policies: controlling tool access, restricting plugin/MCP additions from within the sandbox
- End-to-end sandboxed dev loop: an agent builds and runs a simple self-hosted Python web app inside a sandbox, using Playwright as a local MCP server for visual verification, declarative port forwarding, and a boot-time hook to run the dev server with live reload
