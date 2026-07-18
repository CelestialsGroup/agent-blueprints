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
DeerFlow / OpenAI Agents SDK / Native Runtime / Sandbox Adapter / nexu Provider
```

Agent Workbench 只访问 Agent Access API、SSE 和 Runtime Gateway。Agent Engineering Workbench 只消费不可变运行证据的只读投影；调试重跑必须创建新的 ConversationBranch、WorkOrder、ExecutionGrant、ProviderResolution 和 RunManifest。

## 数据所有权

| 所有者 | 权威数据 | 禁止拥有 |
|---|---|---|
| Business | User、Organization、Membership、Product、Order、Payment、Entitlement、Commercial Quota | WorkOrder、Run、Event、Artifact、TechnicalUsage |
| Agent Platform | Conversation、Workspace、WorkOrder、Workflow、Event、Artifact、TechnicalUsage、Provider、Sandbox、Recording、Audit | 价格、商业余额、支付和会员事实 |
| Runtime/Sandbox Provider | 私有 Run、Checkpoint、Pod/VM、内部 Endpoint、后端观测状态 | Business 授权、Platform 终态和正式 ArtifactVersion |
| Workbench | 用户交互和短期客户端状态 | 任何服务端权威事实 |

## 稳定内核与 Provider

稳定内核只保存可复现、可审计且与执行后端无关的标识和状态。Agent Runtime、Sandbox、Model、Tool、Template、Renderer、Editor 和 Converter 都通过不可变 ProviderRevision、仅追加 AdmissionDecision 和 ProviderResolution 接入。

ProviderRevision 由通用 Implementation、BuildProvenance、稳定 Port Binding、配置、权限和 Conformance 组成，不要求 Runtime 或 Sandbox 伪装成 Plugin。

```text
WorkOrder 1 -> 1 WorkflowRun
WorkflowRun 1 -> 1 root AgentRun + 0..N subagent AgentRun
AgentRun 1 -> 1 RunManifest + 1 AgentRuntimeRun
AgentRuntimeRun mutation -> Invocation 1 -> N Attempt
```

每个 AgentRun 由 Tenant/Conversation 绑定、授权/预算/策略摘要、ProviderResolution、AdmissionDecision、Event Registry、Experience Revision、Sandbox Slot 和 RunManifest 固化。RunManifest 的 Runtime 选择只引用一个 ProviderResolution，避免重复快照产生冲突。运行中的 Run 不得静默切换 Provider；Provider 原生 Checkpoint 默认不具备跨框架可移植性。

## 可靠性边界

- Temporal 保存执行控制 History，PostgreSQL 保存查询态和账本。
- 外部副作用通过 Invocation 或 SandboxOperation Ledger 管理。
- 双写通过事务 Outbox/Inbox 或可重放协调器闭合。
- Artifact 和 Recording 大块字节只进入对象存储，数据库和 Event 只保存引用与摘要。
- 核心 Runtime Event、PolicyDecision、TechnicalUsage 和 Runtime Gateway Frame 使用闭合 Schema；RunManifest 绑定 Event Registry ID/Version/Digest，未知 Provider Payload 不能驱动核心 Projection。
- Runtime/Sandbox/Capability 认证绑定不可变 Conformance Suite/Profile/Digest；Runtime 调用令牌绑定 Tenant、Run、Attempt、Fencing、Policy、Budget 和请求摘要。
- BusinessSettlementEnvelope 嵌入完整不可变 UsageReport，但不包含价格、货币、余额或商业结论。
- 系统不承诺全局 Exactly-once。

## 当前状态

v0.9.0 已通过本地契约 Gate，但尚未冻结。当前没有真实 Agent Platform 产品实现；Phase 0 的 Adapter、Migration、Runtime Gateway、故障注入、容量和备份恢复证据仍待完成。
