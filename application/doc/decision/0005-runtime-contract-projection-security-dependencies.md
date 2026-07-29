# 0005 Runtime Contract Projection And Security Dependencies

Date: 2026-07-29

Status: implemented candidate awaiting review for B03.2-P0 only. This decision
does not approve a Native Runtime lifecycle, HTTP Provider endpoint, Platform
dispatch, Temporal integration, production Safety Controller, or any
`runtime-core-v1` Conformance claim.

## Context

The locked Runtime Provider OpenAPI 3.1.1 document references external Draft
2020-12 Schemas. The complete Runtime boundary additionally names operation
descriptor and token contracts, while SystemSafetyControl is required by the
bounded Cancel design. The resulting transitive projection contains 39 Schema
documents with absolute URN `$id` references, conditionals, closed objects, and
dependent constraints.

Generated transport values cannot become domain or persistence truth, and
generator validation cannot replace the complete Draft 2020-12 semantics. Raw
Contract Schemas also cannot be copied into Application as a second authority.

## Decision

- Generate Go transport-only types with `go-jsonschema v0.24.0` from an
  isolated, sum-locked Go module.
- Generate Python closed TypedDict transport-only modules with the official
  `datamodel-code-generator 0.71.0` arm64 OCI image pinned by digest.
- Regenerate the Python generator image's complete 29-distribution manifest
  from that exact digest and require an exact match to the reviewed third-party
  inventory before accepting generated output.
- Materialize a temporary Schema closure by structurally resolving Contract
  `$id` values and rewriting URN references only inside an ignored scratch
  directory. Keep only generated types and a path/id/digest manifest.
- Require scratch regeneration and a zero committed-output diff in the full
  implementation Gate.
- Use `santhosh-tekuri/jsonschema/v6 v6.0.2` and Python `jsonschema 4.26.0`
  for independent Draft 2020-12 fixture validation.
- Use `go-jose/v4 v4.1.4` and `PyJWT 2.13.0` plus `cryptography 49.0.0` for
  EdDSA/ES256 primitives. Algorithms remain an explicit allowlist.
- Use `gowebpki/jcs v1.0.1` and Python `rfc8785 0.1.4` for RFC 8785
  canonicalization, verified against locked Contract vectors.
- Record every direct and transitive Runtime/codegen dependency, including all
  installed Python generator-image distributions, source,
  license, maintenance/security review, alternatives, upgrade strategy, and
  rollback strategy in the exact supply-chain inventory.

`oapi-codegen v2.8.0` is rejected for this projection because the real locked
Contract fails on a nested local `$defs` reference. Downgrading OpenAPI 3.1,
flattening away Contract semantics, or hand-maintaining shadow DTOs is not an
acceptable workaround.

## Consequences

The generated Go and Python trees are replaceable transport details. Callers
must validate against the authoritative release Schema closure and map into
stable domain values before use. Generated `map[string]interface{}` or TypedDict
shapes do not prove conditionals, unknown-field rejection, Strict I-JSON,
authority, digest, fencing, idempotency, or state-machine semantics.

Rollback restores the generator versions/images, isolated Go tool graph,
runtime dependency graphs, generated trees, fixture matrix, and inventory as
one unit. A partial rollback fails the zero-diff or supply-chain Gate. Removing
P0 is safe because no production Runtime or Platform path consumes it yet.
