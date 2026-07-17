# v0.8.6 Contract Closure Audit Report

The v0.8.5 review findings were reproducible. They are enforcement and repository-integration defects; no Business/Platform ownership, Provider Port, Sandbox Slot, source-of-truth or Adapter-private infrastructure boundary changed.

| Finding | v0.8.6 enforcement |
|---|---|
| Git-root integration bypass | Supply-chain Gate verifies governed Workflow and `.gitignore` in working tree and committed `HEAD`, and rejects root `.DS_Store` in index or `HEAD`; an executable temporary-monorepo test proves the fail/fail/pass sequence |
| Aggregate/adjudication contradiction | Validator derives the only permitted Decision and Case outcome from Aggregate status; callers no longer provide expected values |
| Invocation fencing gap | Two positive InvocationAttempt fixtures plus aggregate validation enforce contiguous numbering, immutable request digest, unique strictly increasing fencing tokens and current/latest pointer consistency |
| Adjudication time reversal | Platform timestamps enforce `opened <= resolved <= decided <= updated/completed` with zero skew; Provider timestamps remain evidence only |
| Partial compatibility policy | Reviewed conditional, unevaluated, contains, effective security and chained local-reference cases are executable self-tests; governance explicitly requires review/ADR and future consumer/replay/interoperability evidence |
| Orphan state | State-machine Gate requires every allowed state, not only terminals, to be reachable from the initial state |

v0.8.6 remains unfrozen. The archive cannot commit the user's local parent Git repository. Public CI and Phase 0 operational evidence remain required.
