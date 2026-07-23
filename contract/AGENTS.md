# Agent Contract Rules

## Authority

This directory is a declarative agreement package. It owns Schema, OpenAPI, state machines, event registries, semantic constraints, fixtures, Conformance Suites, compatibility manifests, and examples. Architecture intent and development rules remain in Blueprint; product implementation and runtime evidence remain in Application; executable validation support remains under `script/contract/`.

Only Markdown, JSON, YAML, and directory metadata belong here. Do not add scripts, source code, Makefiles, dependency manifests, lockfiles, build output, generated Gate evidence, CI configuration, migrations, deployment resources, or product implementation.

## Change Discipline

- Update every affected Schema, OpenAPI document, state machine, event registry, semantic rule, fixture, Conformance Suite, and compatibility manifest together.
- Preserve Draft 2020-12 absolute IDs, Strict I-JSON, RFC 8785 JCS, deterministic resource ordering, and fail-closed compatibility behavior.
- Every `contract_gate` check ID must map to a stable validation identifier. Every `phase0_implementation_required` mapping must resolve to a Contract Suite test or a Blueprint responsibility URN.
- Contract resources must not depend on a script directory name, a common Git history, or a hard-coded sibling path.
- Do not claim global exactly-once or promote third-party runtime, sandbox, thread, checkpoint, endpoint, local database, hook, or trace state into the stable contract.

## Validation

Use the external scripts under `script/contract/` and set `AGENT_CONTRACT_ROOT` to this directory. Validation reports belong to the Script package or release governance, never to this Contract package. Keep Contract Gate, 0B implementation, 0C-0G integration, 0H reliability, formal freeze, and production approval as separate conclusions.
