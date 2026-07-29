# Native Runtime Package

The B03.2a0 implementation contains the private durable Runtime kernel,
Provider-local SQLite state, command handling, cursor events, same-revision
checkpoint/restart, and a replaceable execution-loop Port. Secure request
admission and governed Gateway clients remain later slices.

Modules in this package must not read PostgreSQL or Temporal persistence, store
Platform authority, expose secrets, or leak private Agent/Thread/Checkpoint
objects into public Contract payloads. `MutationAdmission` records only the
already-verified mutation replay fact needed for an atomic local transaction; it
is not a token validator or RuntimeAuthorization authority.

Runtime Port values are closed domain types. In particular, `RuntimeEvent.data`
is a union of admitted event-specific values; the SQLite mapper rejects unknown
event types, versions, missing fields, extra fields, and non-string values.
