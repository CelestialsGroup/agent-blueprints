# Architecture Review Status

Candidate: **v0.9.0 Product Boundary**

Current status: **product-boundary contracts locally closed and validated; repository/public admission excluded from this review; not frozen; not production ready**

## Closed in this candidate

- AgentConversation, append-only ConversationMessage, first-class ConversationBranch projection and executable Turn model.
- Conversation-scoped durable Workspace; one-shot calls use an implicit Conversation.
- WorkOrder/ExecutionGrant/WorkSession/RunManifest/CanonicalEvent Conversation binding.
- Dedicated AgentRuntimeProvider v1 lifecycle contract for DeerFlow upgrades and future runtimes.
- RuntimeRecording chunks and playback manifest separated from live RuntimeSession and Sandbox Snapshot.
- Entitlement-filtered Experience Catalog, immutable TemplateRevision and RunManifest selection binding.
- Signed isolated UiExtensionManifest; arbitrary remote JavaScript remains forbidden.
- Business-owned CommercialAuthorizationSnapshot with explicit entitlement/capability/limit evidence, reservation and settlement boundary.
- Conversation, AgentRuntimeRun and RuntimeRecording lifecycle state machines; CanonicalEvent all-or-none Work context binding.
- One authoritative Phase 0 vertical slice; stale v0.8.4/v0.8.6 bootstrap references removed.
- v0.8.6 Invocation/Sandbox adjudication, fencing, compatibility and state-machine hardening retained.

## Required before freeze

- public/repository admission runs the already passing local Schema/OpenAPI/semantic/manifest gates for v0.9.0;
- migrations prove Conversation/message/command/recording/catalog invariants;
- DeerFlow AgentRuntimeProvider adapter passes lifecycle, checkpoint and historical event normalization conformance;
- html-anything Template Catalog import and one converter vertical slice pass;
- Terminal recording capture/playback/redaction passes; Browser/Desktop recording remains capability-gated;
- reference Business authorization/reservation/settlement flow passes idempotency and reconciliation tests;
- full Phase 0 failure, replay, isolation and recovery evidence.

Contract validation does not prove production readiness.
