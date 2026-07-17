# Glossary

## Ownership and access

- **Business Application**: User、Organization、Membership、Product、Order、Payment、Entitlement 和商业额度的事实源。
- **Agent Platform**: Conversation、执行账本、Artifact、Provider、Sandbox、Technical Usage 和 Delivery 的事实源。
- **ClientApplication / ServicePrincipal**: 使用 OAuth2 Client Credentials 调用平台的业务后端。
- **CommercialAuthorizationSnapshot**: Business 签发的 entitlement、capability、limit 和 quota reservation 快照。
- **ExecutionGrant**: 绑定 Conversation Turn、请求摘要和商业授权的短期单次 JWS。
- **WorkSession**: 绑定一个 Conversation、可选缩窄到一个 WorkOrder 的短期浏览器/SDK 会话。

## Conversation and execution

- **Conversation**: 多轮 Agent 会话，拥有一个 durable Workspace。
- **ConversationBranch**: 分支 head、fork point、CAS version 和 branch-local active WorkOrder 投影。
- **ConversationMessage**: Conversation 内按 message_sequence 追加的不可变消息。
- **Turn**: 一次可执行输入；原子创建 Message、GrantConsumption 和 WorkOrder。
- **WorkOrder**: 一个 Turn 的异步执行与总状态，不承担无限期 Conversation。
- **Workspace**: Conversation 范围的 Artifact、文件和 Sandbox 工作空间。
- **WorkflowRun**: Temporal durable workflow 实例。
- **AgentRuntimeProvider**: start/command/status/event/checkpoint 的稳定 Agent Runtime Port；DeerFlow 是首个 Adapter。
- **RunManifest**: 固化 Scenario、Capability、Provider/Admission、Experience、Sandbox、Runtime 和商业授权摘要的执行快照。

## Reliability

- **Invocation**: 一次逻辑外部能力调用。
- **InvocationAttempt**: 一次真实提交，拥有唯一 attempt ID 和递增 fencing token。
- **Reconciliation**: 根据 Provider/业务证据确认 outcome_unknown 的流程。
- **CanonicalEvent**: 不可变执行事实；Work 事件按 work_sequence 排序，Conversation-only 事件按 aggregate sequence 排序。
- **Outbox/Inbox**: 事务提交后可靠发布和消费去重机制。

## Capability and extension

- **Scenario**: 面向业务的输入、Workflow、Capability、Experience、UI 和输出定义。
- **CapabilityDefinition**: 请求/结果/错误、副作用、取消、Artifact 和 Conformance 的版本化语义契约。
- **ProviderInstance**: 可变的逻辑 Provider 配置容器。
- **ProviderRevision**: Plugin、配置、权限、运行绑定和 Conformance 的不可变快照。
- **ProviderAdmissionDecision**: 对 ProviderRevision 的 append-only certified/revoked 决策。
- **ProviderResolution**: 为精确 Capability/Profile 选择并锁定 Revision 的结果。
- **ExperienceCatalogEntry**: 用户可发现的模板、Skill、Design System 或 Editor 条目。
- **TemplateRevision / SelectedExperience**: 不可变 Experience 内容及 Run 中的精确选择。

## Artifact and runtime

- **Artifact / ArtifactVersion**: 逻辑产物及不可变内容版本。
- **ArtifactStaging**: Provider 输出在正式提交前的隔离验证区。
- **SandboxProvider**: create/exec/session/snapshot/terminate 的可替换基础设施 Port。
- **SandboxOperation**: Sandbox 生命周期或 Exec 的持久化逻辑操作；与单次 transport Attempt 分离。
- **RuntimeSession**: 前端经 Runtime Gateway 访问 Terminal/Browser/Desktop 的短期实时授权。
- **RuntimeRecording**: 与 live Session 分离的 immutable chunk/manifest 历史回放资源。
- **Model/Tool/Artifact/Egress Gateway**: 强制预算、审批、凭据、Artifact 和网络策略的执行中介。
