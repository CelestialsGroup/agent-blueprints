# v0.8.3 Contract Re-hardening Audit Report

## Decision

The eight reported v0.8.2 findings were reproducible contract or repository-governance defects. They were not dismissed as tool-environment failures. The local absence of Go and the scratch runner's relocated virtual-environment symlinks are environment limitations and are recorded separately; neither is counted as a passing public CI result.

v0.8.3 preserves the frozen domain boundary and Provider/Capability/Sandbox Slot architecture. It changes enforceable contract semantics and governance only. v0.8.2 must not be frozen.

## Resolution matrix

| Finding | Classification | v0.8.3 enforcement |
|---|---|---|
| `.venv/*.pyc` breaks official order | CI/implementation | Supply-chain scan uses `git ls-files` in a real tracked checkout and excludes generated roots only in source-package fallback; tracked bytecode remains forbidden. |
| nested Workflow inactive | repository integration | Installer copies to Git root and requires commit/configuration; supply-chain Gate rejects a tracked nested package with no Git-root Workflow. |
| state documentation conflicts | contract/document | WorkOrder and Invocation now have governed JSON state machines; semantic Gate requires exact Schema state-set equality, reachability, and terminal closure. |
| unsafe Sandbox cancellation | contract | `cancel_requested` and `cancellation_confirmed` separate intent from evidence; unknown outcomes remain in reconciliation; abandon requires accepted risk. |
| incomplete RunManifest admission | contract | `RunAdmissionContext` binds exact Scenario capabilities, self-digested immutable revisions, self-digested latest admission decisions, provider instances, and snapshots. |
| partial Compatibility Gate / mutable baseline | CI/contract governance | Comparator covers the reported Schema/OpenAPI narrowing classes; CI baseline and first-baseline exception come only from protected variables and fail closed by default. |
| Strict I-JSON decimal/exponent bypass | contract/implementation | Python, Node, and Go check the canonical numeric value; shared negative vectors cover decimal and exponent spellings. |
| incomplete Sandbox aggregate constraints | contract/database | Active state requires a current Attempt, count bounds have semantic/DB requirements, and abandon requires `risk_accepted=true`. |
| tracked `.DS_Store` | repository hygiene | Git-tracked `.DS_Store` is rejected. The parent repository must remove any already tracked file and commit that removal. |

## Boundary impact

No Business/Platform ownership is moved. ProviderRevision remains immutable and certification remains append-only. Kubernetes/VM/container identity remains Adapter-private. Temporal, PostgreSQL, S3-compatible storage, outbox/inbox, append-only events, idempotency, fencing, reconciliation, and immutable artifact versions remain the reliability basis.

## Maturity statement

This package is ready to re-enter public CI only after the repository-root Workflow is committed and protected variables are configured. It is not frozen and not production ready. Phase 0, multi-node behavior, isolation, failure injection, replay, backup/restore, capacity, and provider conformance remain unproven.
