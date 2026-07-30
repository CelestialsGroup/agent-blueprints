# Native Runtime Package

The package contains the B03.2a0 private durable Runtime kernel and the
B03.2a1.0 secure admission core. It provides Provider-local SQLite state,
command handling, cursor events, same-revision checkpoint/restart, bounded
Strict I-JSON and Schema admission, JWS verification, and a replaceable
execution-loop Port. B03.2a1.1.1 adds only the component process foundation:
immutable startup configuration, separate migrate/serve CLI, bounded loopback
HTTP/1.1 and TLS, exact test workload identity mapping, Capabilities,
health/readiness, and bounded drain. B03.2a1.1.2 and B03.2a1.1.3 add strict
installed component routes for Start and Command, closed Contract response
mapping, and Provider-local transaction, lease, and same-revision checkpoint
recovery. Status/Event HTTP routes and governed Gateway clients remain later
slices.

Modules in this package must not read PostgreSQL or Temporal persistence, store
Platform authority, expose secrets, or leak private Agent/Thread/Checkpoint
objects into public Contract payloads. `MutationAdmission` carries the closed
result of secure verification into an atomic local transaction; it is not a
token issuer or RuntimeAuthorization authority.

The installed recovery workers and fault drivers live only under `test/` and
are not package entrypoints or production composition. Their subprocess,
SQLite, filesystem, and SIGKILL evidence does not establish a production
executor, external side-effect exactly-once behavior, cross-revision checkpoint
compatibility, or aggregate Runtime Core conformance.

Runtime Port values are closed domain types. In particular, `RuntimeEvent.data`
is a union of admitted event-specific values; the SQLite mapper rejects unknown
event types, versions, missing fields, extra fields, and non-string values.
