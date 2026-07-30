# Agent Runtime Port

Phase: **0B Core Profile component foundation**.

The root package now provides the framework-neutral `AgentRuntimeProvider` Port,
bounded immutable opaque values, closed read failures, and four mutation
outcomes: `accepted`, `rejected`, `not_dispatched`, and `outcome_unknown`.
Uncertain mutations require fresh Status/Event read authority and explicitly
forbid replaying the original mutation. This requirement is a value boundary,
not a reconciliation executor or persistence claim.

The `contractprojection` subpackage owns existing generated-Contract parity
helpers. Generated transport types, `net/http`, Native Runtime internals,
private checkpoint content, Provider endpoint/TLS resolution, token issuance,
and Platform PostgreSQL/Temporal facts do not leak into the root Port.

No HTTP adapter, production constructor/registration, installed cross-language
evidence, durable reconciliation caller, CanonicalEvent projection, Safety
Controller, or aggregate `runtime-core-v1` claim exists here. Future adapters may
be constructed only by separately admitted component/integration harnesses until
the required production authorities and composition are approved.
