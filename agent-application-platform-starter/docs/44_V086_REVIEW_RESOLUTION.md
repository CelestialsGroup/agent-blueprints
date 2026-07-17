# v0.8.6 Review Resolution

## Repository admission is a committed-state invariant

For a nested package, installed files are insufficient. The Gate compares the package Workflow with the Git-root working file and `HEAD`, requires the root `.gitignore` rule in `HEAD`, and rejects root `.DS_Store` in either index or `HEAD`. `test_monorepo_integration.py` builds a temporary repository and proves that the post-installer and staged-only states fail while the committed state passes.

## Aggregate-authoritative adjudication

The validator maps Aggregate status to a single legal pair:

| Aggregate status | Decision | Case outcome |
|---|---|---|
| succeeded | resolve_success | succeeded |
| failed | resolve_failure | failed |
| cancelled | resolve_cancelled | cancelled |
| abandoned | abandon | abandoned |
| retry_scheduled | retry | retry_approved |

The map is internal to the validator. IDs, version/digest, current Attempt, evidence, risk acceptance and platform timestamp order are checked in the same operation.

## Invocation Attempt ledger

InvocationAttempt is append-only. Per Invocation, attempt numbers start at one and are contiguous; fencing tokens are unique and strictly increasing; every Attempt binds the immutable request digest; aggregate `attempt_count` equals history length and `current_attempt_id` references the latest Attempt. Database uniqueness/check constraints and transactional pointer updates are required in Phase 0.

## Compatibility governance

The comparator remains intentionally conservative and now covers the reviewed cases. It is not presented as a general compatibility proof. Frozen-contract evolution additionally requires reviewed ADR/compatibility evidence and, after implementation exists, consumer contracts, historical payload replay and dual-version interoperability tests.
