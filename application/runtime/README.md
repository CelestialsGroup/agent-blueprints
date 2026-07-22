# Agent Runtime Providers

This directory contains product Agent Runtime implementations that expose the
external AgentRuntimeProvider Port. Runtime packages are separately buildable
and cannot read the platform PostgreSQL database or Temporal persistence.

The self-developed Native Runtime is the primary implementation. The independent
Go Reference Runtime Probe lives under `cmd/reference-runtime-probe/` because it
is conformance-only, not a product Runtime family.
