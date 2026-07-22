# Local Integration Environment

Define the pinned local PostgreSQL, Temporal, Redis/Valkey, S3-compatible object
storage, and optional fault-proxy environment here when Phase 0B integration
tests require it. Use immutable image digests and isolated test data volumes.

This environment is for development and reproducible tests. It is not a
production topology, reliability claim, or source of runtime configuration.
