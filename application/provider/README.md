# Platform Providers

This directory contains independently deployable, platform-owned Provider
implementations other than Agent Runtime. Provider code implements external
Contract ports and remains isolated from the platform database and Temporal
persistence.

- `capability/` begins in Phase 0D.
- `sandbox/` begins in Phase 0D.

Third-party Agent frameworks are references only and do not belong here as
wrapped platform dependencies.
