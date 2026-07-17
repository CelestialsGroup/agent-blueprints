# Phase 0 — v0.9.0 Product Vertical Slice

Phase 0 implements one real Manus-like Conversation path. Directory scaffolding or contract-only code is not completion. Phase 1 starts only after this acceptance plan passes.

## 0A: Business authorization and Conversation

Implement reference Business User/Organization/Free-Pro Membership, immutable EntitlementRevision, idempotent QuotaReservation and CommercialAuthorizationSnapshot. Create Conversation/Workspace, issue Conversation WorkSession, then submit a fresh-grant Turn that atomically appends Message + creates WorkOrder + Workflow Start Outbox.

Prove duplicate Conversation/Turn requests do not create a second Message, WorkOrder, reservation or consumption record.

## 0B: execution path

Implement PostgreSQL/Outbox -> Temporal WorkOrder Workflow -> ProviderResolution/RunManifest -> DeerFlow AgentRuntimeProvider -> DeerFlow Built-in Sandbox `primary-code` -> Invocation/Sandbox Attempt Ledger -> Canonical Event -> Artifact Staging/Finalize -> Delivery/TechnicalUsage settlement.

Prove:

- follow-up input, interrupt, pause/resume, approval and cancel use append-only Runtime commands and fencing;
- Worker/Adapter restart can resume from external state/checkpoint;
- Provider response loss enters reconciliation;
- old Attempt/Runtime command results are rejected;
- Redis loss does not lose truth.

## 0C: Experience and nexu integration

Import at least one html-anything template as ExperienceCatalogEntry + immutable TemplateRevision. Scenario UI discovers it through Catalog, WorkOrder selects its exact digest, RunManifest binds the certified Template ProviderRevision, and DeerFlow consumes it through a governed Skill/Tool path.

Implement html-to-pptx or html-video as one Converter Provider producing a derived ArtifactVersion. No Plugin ID may be hard-coded in Scenario or Workbench logic.

## 0D: live runtime and playback

Open a Terminal RuntimeSession through Runtime Gateway with platform-managed recording. Finalize at least two immutable chunks and a playback manifest aligned to `work_sequence`. The UI must replay Chat, Plan, Timeline, Terminal, Files and Artifact without a live Sandbox.

Browser/Desktop recording remains capability-gated until capture, consent, redaction and capacity tests pass.

## 0E: security and failure evidence

- ExecutionGrant/CommercialAuthorization cannot be exceeded or reused across Turns.
- Model/Tool/Egress gateways cannot be bypassed by DeerFlow.
- Runtime recording does not persist secrets, raw tokens or unencrypted bytes in Event/Temporal/PostgreSQL.
- Template selection cannot reference a hidden, revoked or unadmitted revision.
- Conversation/message/command/recording/catalog database constraints pass concurrency tests.
- Temporal replay, duplicate/lost response, NetworkPolicy/RBAC/Pod Security and minimal backup/restore drills pass.

Phase 0 completion still does not imply Production Ready; capacity, SLO, comprehensive failure injection and production recovery require separate approval.
