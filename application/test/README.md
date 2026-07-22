# Cross-Component Tests

Package-local unit tests stay beside source. This directory contains tests that
cross a package, process, datastore, Provider, or version boundary.

- `conformance/` executes locked Contract Suites.
- `traceability/` maps every implementation-required Contract enforcement to
  explicit implementation and test evidence without treating gaps as success.
- `integration/` proves real component and datastore behavior.
- `replay/` proves Temporal and event-history compatibility.
- `fault/` contains controlled failure and recovery scenarios.
- `e2e/` proves complete user/business paths.

Test output is evidence only when it records exact source revisions, Contract
digests, environment, command, and result.
