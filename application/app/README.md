# Applications

This directory contains user-facing applications and the isolated Business
Reference system. Agent-facing applications consume versioned Agent Access,
SSE, and Runtime Gateway contracts; they do not own platform state or write the
platform database directly.

- `agent-workbench/` is the Phase 0E end-user workbench.
- `business-reference/` is the Phase 0C reference Business system with its own
  API, Web UI, PostgreSQL migrations, and signing boundary.

Create the pnpm workspace only when the first TypeScript application slice is
implemented. Pin exact Node and pnpm versions and keep shared packages under
`../package/` only when reuse is real.
