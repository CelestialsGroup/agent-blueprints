# Agent Runtime Port

Phase: **0B Core Profile component foundation**.

The root package now provides the framework-neutral `AgentRuntimeProvider` Port,
bounded immutable opaque values, closed read failures, and four mutation
outcomes: `accepted`, `rejected`, `not_dispatched`, and `outcome_unknown`.
Uncertain mutations require fresh Status/Event read authority and explicitly
forbid replaying the original mutation. This requirement is a value boundary,
not a reconciliation executor or persistence claim.

The `contractprojection` subpackage owns existing generated-Contract parity
helpers and the required harness-injected Draft 2020-12 Runtime document/Event
Registry validator. The `httpadapter` subpackage implements all five Port
operations over an explicitly injected HTTPS origin, mutual-TLS `http.Client`,
client identity and Contract closure. It bounds requests/responses, maps only
declared statuses, dispatches Start/Command once, and preserves post-dispatch
uncertainty as `outcome_unknown` with fresh-read/no-original-retry requirements.
Status/Event HTTP 400 and undeclared read HTTP 429 remain invalid responses
because the locked OpenAPI does not authorize those mappings.

Only component/integration harnesses may construct the adapter. The installed
cross-language harness compiles normal/Race Go test binaries and calls the real
installed Native Runtime wheel/process for all five operations over ephemeral
Ed25519 mutual TLS, HTTP/1.1 loopback sockets, and a real Provider-local SQLite
file. It adds no production importer or composition root and evaluates no
locked Runtime Suite case. There is no production constructor/registration,
Provider endpoint/TLS resolution, token issuance, durable reconciliation
caller, CanonicalEvent projection, Safety Controller, Platform PostgreSQL/
Temporal ownership, or aggregate `runtime-core-v1` claim. Response-loss,
process-restart and fresh-read reconciliation mechanics remain separately
ordered work. Generated transport types and `net/http` remain below the
framework-neutral root Port; Native Runtime internals and private checkpoint
content do not leak into it.
