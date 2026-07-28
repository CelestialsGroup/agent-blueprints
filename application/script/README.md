# Repository Scripts

This directory contains deterministic repository automation for builds,
dependency admission, code generation, validation, and evidence assembly.
Scripts may consume locked Blueprint and Contract checkouts read-only.

Scripts are not product components or Contract authorities. Pin their toolchains,
keep generated output under ignored `build/` paths, and make destructive or
networked maintenance actions explicit rather than part of normal validation.

`verify_dependency_lock.py` is the only maintenance entrypoint for refreshing
and validating the Application-owned Blueprint/Contract dependency lock.

`verify_phase0_traceability.py` validates Application evidence claims against
every locked `phase0_implementation_required` Contract mapping and emits an
explicit implemented/unimplemented report. A complete report is not itself a
claim that Phase 0B is complete.

`validate_implementation.sh` also runs gofmt detection, `go vet`, pinned
Staticcheck, normal and Race tests, sqlc vet/regeneration comparison, the
disposable PostgreSQL and Temporal integration suites, deterministic History
Replay, and reproducible `agent-access`, `agent-worker`, and Native Runtime
builds. Downloaded release tools and module caches live only under the ignored
`.cache/` tree.

Successful full runs emit PostgreSQL and Temporal manifests under
`build/evidence/b03.1` plus reproducible build, SPDX, provenance, and locked
upstream evidence under `build/evidence/b01`. The B03.1 manifests record exact
commands/results, source sets, History and Replay fixture digests, immutable
tool/image pins, the current Blueprint/Contract dependency lock, and validated
Race/repeat summaries. These are generated review artifacts, not committed
status or Phase 0 check-ID claims.
