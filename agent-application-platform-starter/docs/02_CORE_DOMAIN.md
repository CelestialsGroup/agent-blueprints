# 核心领域

## 访问

- ClientApplication
- ServicePrincipal
- ServiceAccessTokenProfile
- WorkSession
- InternalTenant
- ExternalTenantMapping
- ExternalPrincipalMapping

## 授权

- ExecutionGrant
- GrantConsumption
- IdempotencyRecord
- ExecutionBudget
- PolicyDecision

## 工作执行

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

## 外部调用

- Invocation
- InvocationAttempt
- InvocationResult
- ExternalOperation
- ReconciliationCase

## 扩展

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

## 事件

- CanonicalEvent
- EventTypeDefinition
- WorkEventCursor
- AggregateCursor
- Projection
- Outbox/Inbox

## 产物

- Artifact
- ArtifactVersion
- ArtifactRelation
- ArtifactStaging
- ArtifactIngestSession
- PreviewSession
- EditSession
- ConversionJob

## 交付

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

## Runtime 体验

- AgentRuntimeRun
- AgentRuntimeCommand
- AgentRuntimeCheckpointManifest
- RuntimeSession
- RuntimeRecording
- RuntimeRecordingChunk
- RuntimeRecordingManifest

Business 拥有的 Membership、EntitlementRevision、QuotaReservation 和商业 Settlement 仍位于本领域之外。Platform 保存本地准入所需、由 Business 签名的 CommercialAuthorizationSnapshot 值及摘要，但无权修改 Entitlement 或商业余额事实。
