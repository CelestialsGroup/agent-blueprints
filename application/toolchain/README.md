# Build Toolchain

This directory records build toolchains, dependency ownership, and supply-chain
inputs. It does not change the maturity reported by the locked Contract
checkout.

The B01 implementation slice contains:

- a Go Agent Access process with lifecycle-only health endpoints;
- an independent Python Native Runtime package bound to `runtime-core-v1` build identity;
- exact container image digests and a reviewed third-party dependency inventory;
- reproducible Go binary and Python wheel builds with hashed Python build constraints;
- generated SPDX 2.3 SBOM, SLSA provenance, and contract-shaped BuildProvenance evidence;
- a containerized implementation validation entrypoint.

Every build first verifies `dependency-lock.json`. Generated provenance records
the locked Blueprint and Contract source snapshots, Contract Manifest, and each
consumed Conformance Suite/Profile. Changing an upstream checkout without an
explicit lock refresh fails before Application compilation.

The B02.1 slice adds pgx v5 persistence plus release-digest-pinned goose and
Staticcheck tools, a digest-pinned sqlc OCI image, and a PostgreSQL 18.4 test
image. Only Tenant/ClientApplication bootstrap persistence is implemented;
Temporal, Runtime HTTP, and product execution remain later slices.

Run `make validate-implementation` from the repository root. The command uses
the exact container images in `toolchain/toolchain.env` when host toolchains do
not match the governed versions. Reproducible B01 build artifacts are written
under `build/evidence/b01/`. PostgreSQL test logs and their source/tool/lock-bound
manifest are written under `build/evidence/b02.1/`. Both are generated outputs
and are not committed.

Verified tool, Go, and Python dependency downloads are cached under ignored
`.cache/implementation/` paths. A cold cache requires network access; subsequent
runs reuse content still checked by release SHA-256, `go.sum`, OCI digests, and
the hashed Python build constraints.

The B01 Go artifact target is explicitly pinned to `linux/arm64`, matching the governed toolchain image used by the current Phase 0 Gate. Multi-architecture production OCI builds are a later release concern and are not implied by this slice.

Reproducible archives and SPDX metadata use `SOURCE_DATE_EPOCH=946684800` (`2000-01-01T00:00:00Z`). This is the declared build timestamp for deterministic B01 evidence, not a wall-clock production build or release time.
