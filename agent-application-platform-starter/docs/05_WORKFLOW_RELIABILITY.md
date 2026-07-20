# Workflow 与可靠性

## Orchestration Binding

Phase 0 使用 Temporal 作为持久 Workflow Runtime，但稳定执行身份只保存 `WorkflowRun` 与 `OrchestrationBinding`。Binding 固化 Engine/Worker Revision 和原生执行引用摘要；Namespace、Endpoint、Temporal Run ID 与 History 仍由 Orchestration Adapter 管理。

Workflow Runtime Port 隔离 SDK，但不得隐藏以下平台语义：

- Platform WorkflowRun ID
- Engine ID/Version
- Worker Deployment
- Build ID
- Versioning Behavior
- Signal
- Cancellation
- Continue-as-New

## WorkOrder 启动

WorkOrder 数据库事务只写 Workflow 启动 Outbox。

Dispatcher 以稳定 Workflow ID 启动：

```text
work-order/<work_order_id>
```

重复 Dispatch 必须复用同一 Workflow Execution 或安全返回已存在结果。

Workflow 启动后通过幂等领域 Activity 将 WorkOrder 从 `accepted` 转为 `queued`/`running`。

Conversation Turn 事务先原子追加 Message、分配 message_sequence、创建 WorkOrder 和 Workflow Start Outbox。Conversation Workflow 只协调长期实体；每个 WorkOrder Workflow 保持可终止、可回放的执行边界。

控制现有 WorkOrder 不创建新 Turn。`WorkOrderControlRequest` 与新的单次 ExecutionGrant 先原子保存控制输入和 Control Outbox，再由 Worker 发送只引用 `control_request_id` 的 Runtime Command。`interrupt_and_enqueue` 属于新 Turn 路径：先记录当前 WorkOrder 取消意图，再创建独立后继 WorkOrder。`accepted` 在尚未入队时也允许直接进入 `cancel_requested`。

## 权威状态

PostgreSQL 是 API 当前状态事实源。

Temporal History 是 Phase 0 的执行控制事实源；PostgreSQL 中的 WorkflowRun 是稳定身份与查询绑定，不复制原生 History。

所有对外状态变化由幂等 Domain Activity 更新 PostgreSQL，并在同一事务写 Event/Outbox。

对账流程检测 Temporal 与 PostgreSQL 漂移。

## 外部副作用

Temporal 不提供外部副作用 Exactly-once。

所有外部调用通过 Invocation Ledger。

## Worker 版本管理

每个 Worker 使用：

- Worker Deployment 名称
- Build ID
- 明确 Versioning Behavior

建议：

- 有界 WorkOrder Workflow：固定版本
- 长期 Conversation Workflow：自动升级 + Patching，或在 Continue-as-New 边界升级

禁止笼统假设所有运行中 Workflow 永远固定同一版本。

## History 与 Payload 管理

- 大文件和 Artifact 只传引用/摘要。
- Prompt 和敏感 Payload 使用加密 Payload Codec。
- Activity Result 大小受限。
- 长期 Workflow 使用 Continue-as-New 控制 History。
- Temporal Namespace 保留期限与数据删除策略一致。

## 超时

Capability Timeout 映射到：

- Schedule-to-Start
- Start-to-Close
- Heartbeat
- Retry Policy

长任务必须发送 Heartbeat 并响应取消请求。

## Sandbox Workflow

Sandbox 创建、Lease、Exec、Snapshot、Restore、Terminate 都是异步 Operation。只有 Scenario/Runtime Capability 要求 Sandbox 时才进入该子流程；`sandboxes=[]` 的 Runtime 直接跳过，不能为了统一流程制造空 Sandbox。

Workflow 必须：

- 使用稳定 Sandbox ID 和 Operation ID
- 重试时复用逻辑操作
- 处理 outcome_unknown
- 等待持久 Sandbox Event 或查询 Operation
- 在取消时先阻止新 Exec，再取消活动 Operation，最后终止 Sandbox
- Lease 续期必须受 ExecutionBudget 限制

需要 Sandbox 的 AgentRun 按以下顺序执行：ProviderResolution 与证据固化 → 从 Branch WorkspaceRevision 创建 Sandbox → 固化含实际 Sandbox ID 的 RunManifest → Start Runtime。不得在 Sandbox 身份尚未知时伪造完整 RunManifest。

RunManifest 固化实际有界输入或不可变输入引用、ContextPackage、ArtifactAccessRequirement、初始 ExecutionBudget/PolicyDecision/EffectivePermissions 上限、CommercialAuthorizationBinding（ID/Digest/`expires_at`）、授权续期规则以及 Model/Tool/Artifact/Egress Gateway Binding。Start Runtime 携带本 InvocationAttempt 的短期 RuntimeAuthorization 和 ArtifactGrant；Authorization 的内部 Tenant/WorkOrder/Commercial 绑定必须闭合，且自身与 ArtifactGrant 均不得越过商业授权期限。到期、Adapter 重启或 Resume 时以连续前驱摘要创建等价/缩权 Revision，扩权必须新建 WorkOrder。Temporal History 只传内容寻址引用和必要控制字段，不复制大 Payload；Provider 收到摘要占位但拿不到执行值必须 fail-closed。
