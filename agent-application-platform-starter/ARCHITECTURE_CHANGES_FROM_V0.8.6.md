# Architecture Changes from v0.8.6

- Added AgentConversation, append-only ConversationMessage, first-class branch-head projections and executable Turns.
- Moved durable Workspace ownership from one WorkOrder to one Conversation; one-shot calls create implicit Conversations.
- Added AgentRuntimeProvider v1 for DeerFlow/future runtime lifecycle, commands, events and checkpoints.
- Added RuntimeRecording, chunks and playback manifest owned by Runtime Gateway/Artifact.
- Added Experience Catalog, immutable TemplateRevision, SelectedExperience and isolated UiExtensionManifest.
- Added Business-owned CommercialAuthorizationSnapshot with executable entitlement/capability/limit evidence and reservation/settlement boundary.
- Added Conversation, AgentRuntimeRun and RuntimeRecording state machines plus all-or-none CanonicalEvent Work context.
- Extended Agent Access API, CanonicalEvent, RunManifest and semantic validators.
- Replaced competing Phase 0/Phase 1 descriptions with one authoritative delivery plan.

v0.8.6 and earlier are historical and must not be used as the implementation baseline.
