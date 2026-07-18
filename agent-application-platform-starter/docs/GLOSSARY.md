# 术语表

## 所有权与访问

- **Business Application**：User、Organization、Membership、Product、Order、Payment、Entitlement 和商业额度的事实源。
- **Agent Platform**：Conversation、执行账本、Artifact、Provider、Sandbox、Technical Usage 和 Delivery 的事实源。
- **ClientApplication / ServicePrincipal**：使用 OAuth2 Client Credentials 调用平台的业务后端。
- **CommercialAuthorizationSnapshot**：Business 签发的 Entitlement、Capability、Limit 和 Quota Reservation 快照。
- **ExecutionGrant**：绑定精确请求 Contract/Digest Profile、Conversation Turn 和商业授权的短期单次 JWS。
- **WorkSession**：绑定一个 Conversation、可选缩窄到一个 WorkOrder 的短期浏览器/SDK Session。

## Conversation 与执行

- **Conversation**：多轮 Agent 会话，拥有一个持久 Workspace。
- **ConversationBranch**：Message Head、WorkspaceRevision Head、派生点、CAS 版本和分支内活动 WorkOrder 投影。
- **ConversationMessage**：Conversation 内按 `message_sequence` 追加的不可变消息。
- **Turn**：一次可执行输入；原子创建 Message、GrantConsumption 和 WorkOrder。
- **WorkOrder**：一个 Turn 的异步执行与总状态，不承担无限期 Conversation。
- **Workspace**：Conversation 范围的 Artifact、文件和 Sandbox 工作空间。
- **WorkspaceRevision**：Branch 范围的不可变文件 Manifest Revision；Sandbox 挂载精确 Revision，提交以 CAS 推进 Branch Head。
- **WorkflowRun**：一个 WorkOrder 的平台级持久编排身份；Temporal 或未来编排器的原生执行分段属于 Orchestration Adapter 私有历史。
- **AgentRun**：一个不可变、受治理的 Root 或 Sub-agent 执行身份，绑定一个 RunManifest 和一个 AgentRuntimeRun。
- **BuildProvenance**：Provider Implementation 的 Source Revision、Source Tree、Build Artifact、SBOM 与 Provenance Statement 摘要。
- **MeterDefinition**：不含价格的不可变技术计量语义和基础单位。
- **ExecutionBudget / PolicyDecision**：Platform 从商业限制和全部策略作用域导出的不可变执行预算与 `deny > ask > allow` 决策。
- **AgentRuntimeProvider**：启动/Command/Status/Event/Checkpoint 的稳定 Agent Runtime Port；平台不依赖单一框架，DeerFlow 只是首个参考 Adapter。
- **AgentRuntimeInvocation Token**：绑定 Tenant、ProviderRevision、Run、Attempt、Fencing、Policy、Budget、Permissions 和请求摘要的短期调用授权。
- **RunManifest**：固化 Tenant、Scenario、ProviderResolution/Admission、Event Registry、Experience、Sandbox、Runtime 和授权/预算/策略摘要的执行快照。

## 可靠性

- **Invocation**：一次逻辑外部能力调用。
- **InvocationAttempt**：一次真实提交，拥有唯一 Attempt ID 和递增 Fencing Token。
- **Reconciliation**：根据 Provider/业务证据确认 `outcome_unknown` 的流程。
- **CanonicalEvent**：不可变执行事实；Work Event 按 `work_sequence` 排序，仅属于 Conversation 的 Event 按 `aggregate_sequence` 排序。
- **EventTypeRegistry**：由 ID/Version/Digest 标识的不可变核心 Event Payload 注册表。
- **Outbox/Inbox**：事务提交后可靠发布和消费去重机制。

## Capability 与扩展

- **Scenario**：面向业务的输入、Workflow、Capability、Experience、UI 和输出定义。
- **CapabilityDefinition**：请求/结果/错误、副作用、取消、Artifact 和一致性要求的版本化语义契约。
- **ProviderInstance**：可变的逻辑 Provider 配置容器。
- **ProviderRevision**：Provider Implementation/BuildProvenance、Port、配置、权限、凭据和 Conformance 的不可变快照；不要求包装成 Plugin。
- **ProviderAdmissionDecision**：对 ProviderRevision 的仅追加 `certified`/`revoked` 决策。
- **ProviderResolution**：为精确 Capability/Profile 选择并锁定 Revision 的不可变决策，包含 Resolver、输入、逐候选结论和证据摘要。
- **ConformanceSuiteManifest**：内容寻址的机器可读测试清单；认证结果绑定 Suite ID/Version/Digest/Profile 和 Evidence。
- **ExperienceCatalogEntry**：用户可发现的 Template、Skill、Design System 或 Editor 条目。
- **TemplateRevision / SelectedExperience**：不可变 Experience 内容及 Run 中的精确选择。

## Artifact 与 Runtime

- **Artifact / ArtifactVersion**：逻辑产物及不可变内容版本。
- **ArtifactStaging**：Provider 输出在正式提交前的隔离验证区。
- **SandboxProvider**：创建/执行/Session/Snapshot/终止的可替换基础设施 Port。
- **SandboxOperation**：Sandbox 生命周期或 Exec 的持久化逻辑操作；与单次传输 Attempt 分离。
- **RuntimeSession**：前端经 Runtime Gateway 访问 Terminal/Browser/Desktop/Port Forward 的短期实时授权；Port Forward 不录制。
- **RuntimeRecording**：与实时 Session 分离的不可变 Chunk/Manifest 历史回放资源。
- **UsageReport / BusinessSettlementEnvelope**：Platform 连续编号的技术用量快照与签名交接；Envelope 嵌入 Final/Correction Report，价格与余额仍由 Business 决定。
- **Model/Tool/Artifact/Egress Gateway**：强制预算、审批、凭据、Artifact 和网络策略的执行中介。
