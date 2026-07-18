# 核心领域

本文件只定义稳定所有权和聚合边界。字段以 `contracts/` 为准；Provider 私有对象、前端 Projection 和实现组件不提升为领域聚合。

## Phase 0 聚合

| 聚合 | 负责 | 不负责 |
|---|---|---|
| Access | ClientApplication、ServicePrincipal、WorkSession、Tenant/Principal Mapping | Business User、Membership、登录会话 |
| Conversation | AgentConversation、Message、Branch、持久 Workspace 与不可变 WorkspaceRevision Head | Agent 框架 Thread、Checkpoint、共享可变分支文件头 |
| WorkOrder | 一个可执行 Turn、ExecutionGrant 消费、ExecutionBudget、PolicyDecision、Approval | 商业 Reservation 与余额 |
| Invocation | 逻辑外部调用、Attempt、Fencing、结果未知与 Reconciliation | Provider 内部重试状态 |
| Sandbox | Registry、Spec、Lease、Operation、Snapshot Metadata、RuntimeSession Endpoint 引用 | Pod、VM、Node、原始 Endpoint |
| Artifact | Artifact、Version、Relation、Staging、Ingest、Preview/Edit/Conversion Session | Provider 临时文件系统 |
| Provider | Instance、Revision、Implementation/Provenance、Port、Admission、带解析证据的 Resolution、Conformance | Plugin Marketplace 和框架内部注册表 |
| Recording | RuntimeSession 授权、RuntimeRecording、Chunk、Manifest | 实时 Sandbox 生命周期、视频字节数据库存储 |
| Usage/Delivery | MeterDefinition、TechnicalUsage、UsageReport、Delivery Package/Attempt、Settlement Envelope | 价格、货币、商业余额和 Settlement 结论 |

PostgreSQL 保存聚合当前态、Ledger、Outbox/Inbox 和元数据；CanonicalEvent 是仅追加审计与 Projection 输入，但系统不采用全量 Event Sourcing。

## 执行身份

```text
Conversation Turn
 -> WorkOrder
 -> WorkflowRun
 -> root AgentRun
    -> optional child AgentRun
 -> AgentRuntimeRun
 -> Invocation
    -> InvocationAttempt
```

- 一个 WorkOrder 只有一个平台 WorkflowRun。Temporal Continue-as-New 或未来编排器分段属于 Orchestration Adapter 私有历史。
- 一个 WorkflowRun 有且只有一个 Root AgentRun，可拥有显式父子关系的 Sub-agent AgentRun。
- 一个 AgentRun 绑定一个 RunManifest 和一个 AgentRuntimeRun。Runtime/网络重试复用同一逻辑身份并追加 Attempt。
- 无法在兼容 Checkpoint 范围内恢复时，当前 AgentRun 明确失败；重试或调试重跑创建新的 AgentRun，必要时创建新的 WorkOrder/Branch/Grant。
- 框架原生 Agent、Thread、Run、Checkpoint 和 Session ID 只保存在 Adapter 私有映射中。

## 不可变值与注册表

- ScenarioDefinition、CapabilityDefinition、SchemaReference
- ProviderRevision、BuildProvenance、ProviderAdmissionDecision、ProviderResolution/Resolver Evidence、ConformanceSuiteManifest
- WorkspaceRevision、Branch Workspace Head
- RunManifest、OrchestrationBinding、CommercialAuthorizationSnapshot
- EventTypeDefinition、EventTypeRegistry、MeterDefinition、ExecutionBudget、PolicyDecision
- ExperienceCatalogEntry、TemplateRevision、UiExtensionManifest

这些对象通过 ID、Revision 和摘要绑定；发布后只追加新版本或新决策，不原地修改。

## Projection

Chat、Plan、Timeline、Task、Files、Artifact、Usage、Recording、Provider Health 和 Engineering Trace View 都是从权威聚合、CanonicalEvent、Artifact 与 Recording 构建的 Projection。Projection 可以重建，不拥有终态、授权或计费事实。

## Business 边界

Business 拥有 User、Organization、Membership、Product、Plan、Order、Payment、Refund、Invoice、EntitlementRevision、QuotaReservation 和商业 Settlement。Platform 仅保存签名 CommercialAuthorizationSnapshot、ExecutionGrant 消费和不可变技术 Usage/Settlement Envelope，无权修改会员、价格或余额。

## 明确排除

以下内容不得成为稳定事实源：第三方 Trace、本地 JSON/JSONL/SQLite、ACP Session、宿主机 Bash 状态、Pod/VM/Endpoint、Provider 私有 Checkpoint、可变模板 ID、Hook 结论和浏览器客户端状态。
