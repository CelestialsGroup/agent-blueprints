# v0.8.5 Review Resolution

## Durable adjudication closure

Invocation and SandboxOperation use one adjudication chain rather than overlapping case types:

```text
Aggregate
  -> ReconciliationCase(case_id, case_version, case_digest, evidence, outcome)
  -> ManualReviewDecision(case_id, case_version, case_digest, evidence, decision)
```

The aggregate stores both referenced IDs. Admission validates the objects as a set. Abandon additionally requires explicit risk acceptance. A non-idempotent retry requires a resolved Case with `retry_approved` and a Decision with `retry`; it cannot use the automatic idempotent retry event.

## Bounded Strict I-JSON parsing

Safe-integer validation now has a resource envelope. Python, Node and Go reject oversized number tokens and extreme exponents before arbitrary-precision arithmetic. This prevents a short request from causing an unbounded integer allocation while preserving the existing RFC 8785 canonicalization test layer.

## Append-only chains and deterministic machines

Provider AdmissionDecision sequences start at one and are contiguous. Each later record points to the immediate predecessor for the same immutable ProviderRevision. State machines are deterministic by `(from,event)`. Both invariants have executable negative tests.

## Compatibility scope

The conservative compatibility comparator now detects the reviewed JSON Schema and OpenAPI narrowing cases, including local `$ref` parameters. It is still a policy Gate, not a proof of semantic substitutability; freezing therefore requires review plus the protected-baseline CI comparison.

## Local monorepo integration

The ZIP cannot alter or commit its parent checkout. Run `scripts/install_github_workflow.sh` from the extracted package inside the real repository. The installer places the governed Workflow at the Git root and adds `.DS_Store` to the root `.gitignore`. Any tracked `.DS_Store` must be removed from the index, and these root changes must be committed before Admission can run.
