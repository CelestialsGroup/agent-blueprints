# Local Integration Environment

Define the pinned local PostgreSQL, Temporal, Redis/Valkey, S3-compatible object
storage, and optional fault-proxy environment here when Phase 0B integration
tests require it. Use immutable image digests and isolated test data volumes.

This environment is for development and reproducible tests. It is not a
production topology, reliability claim, or source of runtime configuration.

The B02.1 PostgreSQL harness is `script/test_postgres_integration.sh`. It starts
`POSTGRES_TEST_IMAGE` from `toolchain/toolchain.env` on an isolated Docker
network, uses tmpfs storage, runs the Go integration package, and removes the
container/network on exit. The static test passwords exist only inside that
disposable network and are not deployment defaults.

The bootstrap's fixed PostgreSQL roles permit one Agent database name per
cluster. The suite creates a second database and proves its bootstrap is rejected
before Agent schema creation. It also provisions a separate test-only Migrator
Login and runs a reversible goose probe under explicit `SET ROLE`.
