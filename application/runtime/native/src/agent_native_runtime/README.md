# Native Runtime Package

The package contains the B03.2a0 private durable Runtime kernel and the
B03.2a1.0 secure admission core. It provides Provider-local SQLite state,
command handling, cursor events, same-revision checkpoint/restart, bounded
Strict I-JSON and Schema admission, JWS verification, and a replaceable
execution-loop Port. HTTP/TLS process behavior and governed Gateway clients
remain later slices.

Modules in this package must not read PostgreSQL or Temporal persistence, store
Platform authority, expose secrets, or leak private Agent/Thread/Checkpoint
objects into public Contract payloads. `MutationAdmission` carries the closed
result of secure verification into an atomic local transaction; it is not a
token issuer or RuntimeAuthorization authority.

Runtime Port values are closed domain types. In particular, `RuntimeEvent.data`
is a union of admitted event-specific values; the SQLite mapper rejects unknown
event types, versions, missing fields, extra fields, and non-string values.
