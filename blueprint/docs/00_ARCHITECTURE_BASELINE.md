# v0.9.0 架构基线候选版本

Agent Application Platform 为多个 Business Application 提供受治理的 Conversation、长任务执行、Sandbox、Artifact、Runtime Recording 和 Delivery 能力。Business 与 Agent Platform 使用独立事实源，只通过版本化契约交换授权和技术用量。

## 系统分层

```text
Business Application
  User / Organization / Membership / Product / Order / Payment / Entitlement
        │ CommercialAuthorization / ExecutionGrant / WorkSession
        ▼
Agent Access 与稳定内核
  Conversation / Message / Branch / Workspace / WorkOrder
  Tenant-qualified WorkflowRun / AgentRun / Provider Admission / Policy / Event Registry
  Artifact / Metered TechnicalUsage / Recording / Audit
        │
        ├── Temporal：持久编排 History
        ├── PostgreSQL：当前状态、Ledger、Outbox/Inbox 和元数据
        ├── Object Storage：Artifact 与 Recording Blob
        └── Redis：Cache、Presence 和 Wakeup，不保存事实
        │
        ▼
执行与扩展平面
  AgentRuntimeProvider / SandboxProvider / Capability Provider
  Model / Tool / Artifact / Egress / Runtime Gateway
        │
        ▼
Native Runtime / Reference Contract Probe / Sandbox Provider / nexu Provider
```

Agent Workbench 只访问 Agent Access API、SSE 和 Runtime Gateway。Agent Engineering Workbench 只消费不可变运行证据的只读投影；调试重跑必须创建新的 ConversationBranch、WorkOrder、ExecutionGrant、ProviderResolution 和 RunManifest。

## 数据所有权

| 所有者 | 权威数据 | 禁止拥有 |
|---|---|---|
| Business | User、Organization、Membership、Product、Order、Payment、Entitlement、Commercial Quota | WorkOrder、Run、Event、Artifact、TechnicalUsage |
| Agent Platform | Conversation、Branch WorkspaceRevision、WorkOrder、Workflow、Event、Artifact、TechnicalUsage、Provider、Sandbox、Recording、Audit | 价格、商业余额、支付和会员事实 |
| Runtime/Sandbox Provider | 私有 Run、Checkpoint、Pod/VM、内部 Endpoint、后端观测状态 | Business 授权、Platform 终态和正式 ArtifactVersion |
| Workbench | 用户交互和短期客户端状态 | 任何服务端权威事实 |

## 稳定内核与 Provider

稳定内核只保存可复现、可审计且与执行后端无关的标识和状态。Agent Runtime、Sandbox、Model、Tool、Template、Renderer、Editor 和 Converter 都通过不可变 ProviderRevision、仅追加 AdmissionDecision 和 ProviderResolution 接入。Resolution 绑定 Resolver Revision、完整输入摘要、逐候选结论和不可变证据。

ProviderRevision 由通用 Implementation、BuildProvenance、稳定 Port Binding、配置、权限和 Conformance 组成，不要求 Runtime 或 Sandbox 伪装成 Plugin。

```text
WorkOrder 1 -> 0..1 WorkflowRun（Orchestration Start 成功后恰好一个）
WorkflowRun 1 -> 0..1 RootBinding（Root Admission 成功后恰好一个）
RootBinding -> 1 root AgentRun；WorkflowRun -> 0..N subagent AgentRun
AgentRun 1 -> 1 RunManifest + 1 AgentRuntimeRun
AgentRuntimeRun mutation -> Invocation 1 -> N Attempt
```

每个 AgentRun 由 Tenant/Conversation/Branch WorkspaceRevision、已消费 ExecutionGrant 的请求 Contract/Profile/Digest、实际有界输入、ContextPackage、ArtifactAccessRequirement、初始预算/策略/权限上限、商业授权 ID/Digest/到期上限、授权续期规则、四类 Gateway Binding、ProviderResolution、AdmissionDecision、Event Registry、Experience Revision、按需 Sandbox Slot 和 RunManifest 固化。短期 RuntimeAuthorization/ArtifactGrant 属于 InvocationAttempt，只能在同一 Manifest 与商业有效期内等价或缩权续期；其 Budget/Policy/Permissions 必须绑定同一 Tenant/WorkOrder/CommercialAuthorization，ArtifactGrant 不得早于 Authorization 签发或晚于其到期。Runtime 与 Sandbox Slot 只引用 ProviderResolution，避免重复快照产生冲突。没有 Sandbox Capability 的 Run 可以使用空 `sandboxes[]`；运行中的 Run 不得静默切换 Provider。

Sub-agent 由 Parent Runtime 的类型化 SpawnRequest 触发，但其身份、Provider、预算、Workspace/Sandbox 和是否准入均由 Platform 决定。所有 AgentRun 共享同一个 WorkOrder ExecutionBudget Ledger，并各自持有只包含资源维度的更窄 AgentRunBudgetAllocation；深度、总数和并发只取 WorkOrder ExecutionBudget，在 Admission 事务中硬限制，不复制为 Child 配额。Pause/Cancel 通过持久 fan-out 覆盖所有活动 RuntimeRun，WorkOrder 终态等待 Root 和全部 required Child 收敛，孤儿 Child 由对账器发现并减权。

## 可靠性边界

- Temporal 保存执行控制 History，PostgreSQL 保存查询态和账本。
- 外部副作用通过 Invocation 或 SandboxOperation Ledger 管理。
- 双写通过事务 Outbox/Inbox 或可重放协调器闭合。
- CanonicalEvent 以 Tenant/Producer/SourceStream/SourceEvent 唯一去重，Metadata 闭合；Provider 来源必须绑定 ProviderRevision。
- Artifact 和 Recording 大块字节只进入对象存储，数据库和 Event 只保存引用与摘要。
- 核心 Runtime Event、PolicyDecision、TechnicalUsage 和 Runtime Gateway Frame 使用闭合 Schema；RunManifest 绑定 Event Registry ID/Version/Digest，未知 Provider Payload 不能驱动核心 Projection。
- Runtime/Sandbox/Capability 认证绑定不可变 Conformance Suite/Profile/Digest；Runtime 调用令牌绑定 Tenant、Run、Attempt、Fencing、Policy、Budget 和请求摘要。
- Capability Provider 是独立通用 Port，请求携带完整执行授权并绑定 ProviderResolution/Instance/Audience；Invoke、Status、Cancel、Event 以正式 Contract/Profile/Digest 绑定且使用不可跨操作重放、按前驱续期的 Token。Model/Tool 复用该 Port，Artifact/Egress 使用各自 OpenAPI 与短期操作 Token；Egress 绑定不可变 DestinationRevision/Class；Plugin 只是可选实现方式。
- Preview/Edit/Conversion 统一为 ArtifactOperation ExecutionScope；公开请求不接受 Platform-owned Operation ID、Policy/Budget/Permissions、Gateway 或 Provider 事实。Platform 分配 Operation 后派生并持久绑定这些事实，再复用 Capability/Provider、Invocation/Attempt、Artifact Gateway、TechnicalUsage 与 Settlement，不创建第二套执行账本。ArtifactIngest 在 Session 分配后派生 Policy/Budget/Permissions，是不调度 Provider 的 Platform 分阶段状态机。
- Agent Access 对同时出现在 URL 与正文中的 WorkOrder、Artifact、IngestSession、Conversation 和 CommercialAuthorization 标识使用机器可读 `x-path-body-bindings`，错绑在授权消费和对象查找前 fail-closed。
- BusinessSettlementEnvelope 嵌入完整不可变 UsageReport，或在可证明没有任何执行 Attempt/TechnicalUsage 时绑定 NoUsageAttestation；缺失用量不等于零，Envelope 不包含价格、货币、余额或商业结论。
- Runtime Checkpoint 与 Sandbox Snapshot 的跨 Revision 恢复必须绑定 Platform CompatibilityDecision/Evidence；Secret 只由 SecretGrant + 单操作 Credential Gateway 交付，二者都 fail-closed。
- CommercialAuthorization 撤销收据同步建立 deny，并以可恢复 CAS/Outbox intents 覆盖 WorkSession、WorkOrder、ArtifactOperation 与 ArtifactIngest。ArtifactOperation 的 intent 先持久进入 `cancel_requested`；已派发取消和未知结果分别进入 `cancelling`/`cancellation_reconciling`，不以取消意图冒充终态证据。
- 系统不承诺全局 Exactly-once。

## 当前状态

v0.9.0 已通过本地契约 Gate，但尚未冻结。当前没有真实 Agent Platform 产品实现；Phase 0 的 Adapter、Migration、Runtime Gateway、故障注入、容量和备份恢复证据仍待完成。
