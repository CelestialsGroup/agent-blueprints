# Fault Tests

Phase: **0H evidence; focused component cases may be added earlier**.

Define reproducible failure scenarios for lost/duplicate responses, stale
fencing, worker restart, Redis loss, network interruption, reconciliation,
storage failure, secret leakage checks, backup restore, and bounded overload.

Every case states injection point, expected invariant, recovery path, timeout,
and retained evidence. Unrun or environment-blocked cases remain explicitly
unproven.
