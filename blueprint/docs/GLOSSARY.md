# 术语表

## 所有权与访问

- **Business Application**：User、Organization、Membership、Product、Order、Payment、Entitlement 和商业额度的事实源。
- **Agent Platform**：Conversation、执行账本、Artifact、Provider、Sandbox、Technical Usage 和 Delivery 的事实源。
- **ClientApplication / ServicePrincipal**：使用 OAuth2 Client Credentials 调用平台的业务后端。
- **CommercialAuthorizationSnapshot**：Business 签发的 Entitlement、Capability、Limit 和 Quota Reservation 快照。
- **CommercialAuthorizationBinding**：RunManifest 与 RuntimeAuthorization 使用的不可变热路径引用，至少包含 Snapshot ID、Digest 和 `expires_at`，用于在不查询 Business 的情况下执行到期上限。
- **PrincipalContextSnapshot**：Business 签发的有界不可变身份/授权属性快照；凭据和可变展示资料不得进入，摘要用于 Grant、Policy 和 ProviderResolution 绑定。
- **ExecutionGrant**：绑定精确请求 Contract/Digest Profile、PrincipalContextSnapshot 和商业授权的短期单次 JWS；Turn 与 Control 使用互斥 Claim 形态。
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
- **AgentRuntimeProvider**：启动/Command/Status/Event/Checkpoint 的稳定 Agent Runtime Port；自研 Native Runtime 是主实现，第三方 Agent 项目只作参考或未来可选 Provider。
- **Prompt Policy / Revision**：Native Runtime 用于组合模型基础指令、Scenario、Experience、Skill 和安全提示的版本化策略及不可变摘要；`PromptPolicyBinding` 在 Run admission 时固化 Policy/Builder/Serializer 与指令来源，不保存明文 Prompt。
- **ContextPackage**：Context Builder 在策略、信任和预算约束下生成的有序、不可变、可解析模型上下文描述；Conversation 历史只是候选来源。
- **ContextResolverBinding**：把 ContextPackage 中的内容寻址引用绑定到受治理 Artifact/Capability Port 的 Contract、Audience、Route、Digest Profile 和短期读取授权要求；不携带裸 Endpoint。
- **RuntimeTurnContext / StepContext**：Runtime 私有的请求级默认执行上下文及每次模型采样快照；不得与 Platform `ConversationTurn` 混用，对外只通过版本化摘要和 ModelStepEvidence 证明。
- **Harness Step Snapshot**：一次模型采样请求使用的不可变 Runtime 私有快照，固定 Context、Model、Tool exposure/dispatch、Environment、Workspace/Sandbox、Skill、Budget、Policy、Permissions 和 Approval 状态。
- **ModelStepEvidence**：模型步骤实际 Prompt/Context/Model/Tool/Harness 摘要、Usage/Invocation 关系、内容分类和加密正文引用的脱敏证据；普通 Event/Telemetry 不保存正文。
- **Runtime-private Graph**：只表达一个 AgentRun 内 Plan/Step/局部依赖的 Provider 私有图；不能替代 Platform AgentRun Graph、Temporal History 或 Invocation Ledger。
- **ChildAgentRunSpawnRequest**：Parent Runtime 发出的类型化委派需求；不能自行选择 Provider、预算、Sandbox 或 Child AgentRun 身份。
- **WorkflowRunRootBinding**：Root Admission 成功后单次赋值的 WorkflowRun 到 Root AgentRun/RunManifest 绑定；准入前失败时不存在。
- **RuntimeAuthorization**：绑定一个 Runtime InvocationAttempt 的短期仅追加授权 Revision；可在同一 RunManifest 下等价或缩权续期，并携带 fresh ArtifactGrant。
- **AgentRuntimeInvocation Token**：绑定 Tenant、ProviderRevision、RunManifest、RuntimeAuthorization、Attempt、Fencing、Policy、Budget、Permissions 和请求摘要的短期调用授权；旧 v1 使用 `execution/safety_control`，新 Revision 将 Business 授权的执行/用户控制、只读观察和系统减权拆成 `execution/observation/reduction_control`。
- **SystemSafetyControl**：Platform-owned、不可变且仅用于减权的控制事实；在新的 Business Grant 不可用或不应成为前提时，以 Tenant/WorkOrder/RuntimeRun、Pause/Cancel action、触发证据和摘要授权停止动作，不能恢复执行或产生新副作用。
- **CommercialAuthorizationRevocation**：Business-owned 的不可变撤销通知；由 sender-constrained Business workload 提交，Platform 保存带摘要的幂等 deny 收据与 WorkSession/WorkOrder/ArtifactOperation/ArtifactIngest CAS/Outbox intents。WorkOrder 派生 fenced SystemSafetyControl，其他 Scope 按自身状态机减权；Platform 不回写商业授权事实。
- **RunManifest**：固化 Tenant、Scenario、ProviderResolution/Admission、Event Registry、Experience、Sandbox、Runtime、ArtifactAccessRequirement 和初始授权上限的执行快照；不保存短期 bearer Grant。

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
- **Interoperability Adapter**：把一个锁定的外部协议 Role/Feature/Transport/Revision 映射到平台稳定 Contract 的边缘组件；不拥有 WorkOrder、AgentRun、Invocation 或授权事实。
- **McpConnectorBinding**：MCP Client 连接使用的不可变协议、Feature、Transport、Server/Destination/Command、身份、Credential、Tool allowlist、上限和协商策略绑定；原始 Endpoint 与 Session 保持 Gateway 私有。
- **Skill Package / SkillPackageManifest**：锁定格式 Revision 的指令、资源、脚本和元数据包及其规范化不可变清单；Skill 是导入格式和 Experience/Provider 输入，不是统一 Wire Protocol。
- **SkillImportEvidence**：Skill 从 Source/Upload 经 Quarantine、校验、规范化、扫描和准入生成 Artifact/Experience/Provider Revision 的内容寻址证据。
- **A2A**：Agent-to-Agent 互操作协议；远程 Task 只作 Adapter/Invocation 关联，需要 Sub-agent 时仍必须经过平台 Child Spawn/Admission。
- **ACP（Agent Client Protocol）**：IDE/客户端到 Agent 的边缘交互协议；本文不使用 ACP 表示 Agent Communication Protocol，ACP Session 不等于 Conversation 或授权事实。
- **AG-UI**：Agent 到用户界面的事件互操作协议；只投影 CanonicalEvent/Task/Artifact，用户动作仍通过正式 Turn/Control API 回写。

## Artifact 与 Runtime

- **Artifact / ArtifactVersion**：逻辑产物及不可变内容版本。
- **ArtifactStaging**：Provider 输出在正式提交前的隔离验证区。
- **ArtifactAccessRequirement / ArtifactGrant**：前者是 RunManifest 中无时效的不可变访问需求，后者是绑定具体 InvocationAttempt 的短期读取/暂存授权；Provider 永远没有 Finalize 权限。
- **SandboxProvider**：创建/执行/Session/Snapshot/终止的可替换基础设施 Port。
- **SandboxOperation**：Sandbox 生命周期或 Exec 的持久化逻辑操作；与单次传输 Attempt 分离。
- **RuntimeSession**：前端经 Runtime Gateway 访问 Terminal/Browser/Desktop/Port Forward 的短期实时授权；Port Forward 不录制。
- **RuntimeRecording**：与实时 Session 分离的不可变 Chunk/Manifest 历史回放资源。
- **UsageObservation**：Provider 返回的有界测量证据；Platform 据此创建 TechnicalUsageEntry 的身份、归属、幂等和持久化时间。
- **UsageReport / BusinessSettlementEnvelope**：Platform 连续编号的技术用量快照与签名交接；Envelope 嵌入 Final/Correction Report，价格与余额仍由 Business 决定。
- **Model/Tool/Artifact/Egress Gateway**：强制预算、审批、凭据、Artifact 和网络策略的执行中介。
