# Business Identity, Membership and Entitlement Integration

## Boundary

The reference Business Application owns User/Login, Organization, Membership, Product, Plan, Order, Payment, Refund, invoice, commercial balance and quota ledger. Agent Platform owns technical execution and Usage facts only.

```text
Membership / Plan
 -> immutable EntitlementRevision
 -> idempotent QuotaReservation
 -> CommercialAuthorizationSnapshot
 -> ExecutionGrant / WorkSession
 -> Agent TechnicalUsage
 -> settle | release | reconcile in Business
```

## Admission

Before an executable turn, Business evaluates membership and reserves commercial quota. It signs an ExecutionGrant containing the CommercialAuthorizationSnapshot digest, authorized capabilities, policy and hard limits. Agent Platform verifies the signature and stores the snapshot with WorkOrder/RunManifest; it never queries the Business membership database in the execution hot path.

The snapshot carries explicit authorized entitlement IDs, capabilities and maximum limits in addition to their digests. This is required for local Catalog filtering and admission comparison; a digest without the governed values is not executable authorization evidence.

WorkSession carries the same authorization identity for Catalog filtering, but each new executable turn requires a fresh grant and reservation.

## Settlement

Agent Platform reports immutable TechnicalUsage and terminal WorkOrder outcome through registered Delivery/Usage targets. Business idempotently:

- settles confirmed usage against reservation;
- releases unused reservation;
- reconciles late/corrected Usage;
- applies refunds or commercial policy.

The Platform cannot mutate commercial balance or infer price. Business cannot rewrite TechnicalUsage evidence.

## Reference application modules

The repository implementation should separate `business-web/business-api` from `agent-workbench/agent-api`. The reference Business application provides Login, personal Organization, Free/Pro plan, Membership, billing, entitlement evaluation, reservation/settlement and WorkSession handoff while consuming only versioned Agent Platform contracts.
