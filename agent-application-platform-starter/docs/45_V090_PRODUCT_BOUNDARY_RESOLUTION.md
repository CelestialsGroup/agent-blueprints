# v0.9.0 Product Boundary Resolution

v0.8.6 closed the reviewed contract-enforcement defects, but the concrete Manus-like product target exposed six missing stable boundaries. These are not v0.8.x patches: Conversation ownership, stateful Agent Runtime lifecycle, historical Runtime recording, Experience discovery, commercial authorization handoff and authoritative delivery scope all affect Phase 0 migrations and public APIs.

v0.9.0 therefore adds:

- `AgentConversation -> ConversationMessage -> WorkOrder -> AgentRun`;
- `AgentRuntimeProvider v1` as a dedicated anti-corruption contract for DeerFlow and later runtimes;
- platform-owned `RuntimeRecording`, immutable chunks and playback manifests;
- `ExperienceCatalogEntry`, immutable `TemplateRevision`, `SelectedExperience` and signed isolated UI extensions;
- Business-owned `CommercialAuthorizationSnapshot` bound into ExecutionGrant and WorkSession;
- one Phase 0 vertical-slice plan with no competing legacy phase document.

The reliability kernel remains unchanged: Temporal durable history, PostgreSQL current state and ledgers, Outbox/Inbox, append-only events, Artifact staging, at-least-once delivery, idempotency, fencing and reconciliation.

## Boundary impact

This version intentionally changes the candidate boundary before it is frozen:

- Workspace is Conversation-scoped; each WorkOrder is one immutable execution turn.
- WorkOrder, ExecutionGrant, WorkSession, RunManifest and CanonicalEvent bind Conversation identity.
- UI and template selection cannot depend on a mutable string or Plugin ID.
- live RuntimeSession transport is separate from historical recording.
- DeerFlow private thread/run/checkpoint identifiers remain inside its Adapter.

v0.8.6 and earlier remain historical evidence and must not be used as the implementation baseline.
