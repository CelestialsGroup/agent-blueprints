# v0.8.4 Contract Closure Audit Report

## Decision

The new v0.8.3 review findings are valid. The Git-root Workflow and tracked `.DS_Store` finding is a parent-repository integration blocker that cannot be committed from a nested package archive. The remaining findings are contract/validator defects and are corrected in v0.8.4. No Business/Platform ownership or Adapter-private infrastructure boundary is changed.

## Resolution

| Finding | v0.8.4 enforcement |
|---|---|
| Real monorepo Admission blocked | Installer places the governed Workflow at Git root, refuses a tracked root `.DS_Store`, and tells the integrator which files must be committed. Supply-chain Gate continues to fail until integration is actually present. |
| Generic Provider crashes | Every Provider kind uses required `conformance_set_digest`; snapshot/refresh/admission logic has no Sandbox-vs-Runtime field branch. A Tool Provider is included as a positive end-to-end fixture. |
| Admission only checks self-consistency | Trusted context contains admitted CapabilityDefinitions and allowed Provider kinds. Validator checks definition digest, kind, conformance coverage, Agent Runtime outer digest, and every Sandbox required capability. |
| Invocation reliability incomplete | InvocationRecord v2, state machine v2, ReconciliationCase and ManualReviewDecision enforce attempts, deadlines, evidence, safe cancellation and risk-accepted abandon. |
| Strict I-JSON diverges | Exact decimal coefficient/scale checks are shared semantically across Python/Node/Go. RFC 8785 canonicalizer vectors are separated from stricter platform admission vectors. |
| Cancelled may mean effect completed | Shared CancellationConfirmation excludes `effect_completed`; completed effects require a real outcome or manual adjudication. |
| Compatibility misses narrowing | Gate covers `$ref`, added enum/const/type, removed anyOf/oneOf alternatives, request/parameter schema narrowing, response media removal and requires a fetched full commit SHA. |

## Maturity

v0.8.4 remains an unfrozen contract candidate. Parent repository integration and public CI are still pending. Production readiness still requires Phase 0 implementation, failure injection, isolation, replay, recovery, capacity and Provider conformance evidence.
