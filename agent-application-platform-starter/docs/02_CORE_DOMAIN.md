# 核心领域

## Access

- ClientApplication
- ServicePrincipal
- ServiceAccessTokenProfile
- WorkSession
- InternalTenant
- ExternalTenantMapping
- ExternalPrincipalMapping

## Authorization

- ExecutionGrant
- GrantConsumption
- IdempotencyRecord
- ExecutionBudget
- PolicyDecision

## Work

- AgentConversation
- ConversationMessage
- ConversationBranch
- WorkOrder
- Workspace
- WorkflowRun
- WorkflowStepRun
- AgentRun
- RunManifest
- Approval

## Invocation

- Invocation
- InvocationAttempt
- InvocationResult
- ExternalOperation
- ReconciliationCase

## Extension

- ScenarioDefinition
- CapabilityDefinition
- PluginManifest
- PluginRegistryRecord
- PluginInstallation
- ProviderInstance
- ProviderRevision
- ProviderResolution
- ConformanceResult
- ExperienceCatalogEntry
- TemplateRevision
- UiExtensionManifest

## Event

- CanonicalEvent
- EventTypeDefinition
- WorkEventCursor
- AggregateCursor
- Projection
- Outbox/Inbox

## Artifact

- Artifact
- ArtifactVersion
- ArtifactRelation
- ArtifactStaging
- ArtifactIngestSession
- PreviewSession
- EditSession
- ConversionJob

## Delivery

- CallbackRegistration
- DeliveryTarget
- DeliveryPackage
- DeliveryAttempt
- TechnicalUsageEntry

## Sandbox

- SandboxRegistry
- SandboxSpec
- SandboxStatus
- SandboxLease
- SandboxOperation
- SandboxExecResult
- SandboxSnapshot
- SandboxRuntimeSessionEndpoint
- SandboxUsageEntry
- SandboxConformanceReport

## Runtime Experience

- AgentRuntimeRun
- AgentRuntimeCommand
- AgentRuntimeCheckpointManifest
- RuntimeSession
- RuntimeRecording
- RuntimeRecordingChunk
- RuntimeRecordingManifest

Business-owned Membership, EntitlementRevision, QuotaReservation and commercial Settlement remain outside this domain. The Platform stores only a signed CommercialAuthorizationSnapshot reference/digest with a WorkOrder.
