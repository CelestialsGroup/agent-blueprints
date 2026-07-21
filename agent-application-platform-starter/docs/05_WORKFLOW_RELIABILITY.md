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

Orchestration Start 确认后先创建不含 Root 指针的 WorkflowRun。Provider/Sandbox 准入成功后，Root AgentRun、RunManifest 与 WorkflowRunRootBinding 在一个 PostgreSQL 事务中创建，循环外键使用 Deferred Constraint 并在提交时验证。若 ProviderResolution、Sandbox 或 Policy 在 Root Admission 前失败，WorkflowRun 保留但没有 RootBinding，WorkOrder 可以诚实进入 `failed`；不得伪造 AgentRun、RunManifest 或 Sandbox。

Conversation Turn 事务先原子追加 Message、分配 message_sequence、创建 WorkOrder 和 Workflow Start Outbox。Conversation Workflow 只协调长期实体；每个 WorkOrder Workflow 保持可终止、可回放的执行边界。

控制现有 WorkOrder 不创建新 Turn。`WorkOrderControlRequest` 与新的单次 ExecutionGrant 先原子保存控制输入和 Control Outbox，再由 Worker 发送只引用 `control_request_id` 的 Runtime Command。`interrupt_and_enqueue` 属于新 Turn 路径：先记录当前 WorkOrder 取消意图，再创建独立后继 WorkOrder。`accepted` 在尚未入队时也允许直接进入 `cancel_requested`。

平台安全减权不依赖新的 Business Grant。Business 通过 sender-constrained Service Token 提交不可变 `CommercialAuthorizationRevocation`；Platform 原子保存 Inbox、带 JCS 摘要的 deny 收据，以及 WorkSession 和所有活动 WorkOrder/ArtifactOperation/ArtifactIngest 的 CAS + Outbox intents，不修改 Business 快照。收据提交后新授权和 Gateway 副作用同步拒绝；异步 fan-out 可从收据重放直到每个目标 `completed/already_terminal`。WorkOrder target 事务锁定 WorkOrder、禁止新 Child Admission、创建 AgentRunControlFanout，并为每个活动 RuntimeRun 仅追加独立 `SystemSafetyControl` 和 Control Outbox；ArtifactOperation/Ingest 使用自身状态机进入 reduction-only Cancel/Reject。硬到期、撤销、Deadline、Tenant/Provider 撤销、预算耗尽与平台停机必须 Cancel；只有 WorkOrder 的策略复核、对账止损和操作员介入可以选择 Pause。Runtime Command 的 Pause/Cancel 必须在用户 ControlRequest 与 SystemSafetyControl 之间二选一，绝不能用于扩权或新副作用。

## Child AgentRun

Parent Runtime 通过 `runtime.subagent.spawn.requested` 提交 ChildAgentRunSpawnRequest。Platform 先按 `(work_order_id, spawn_request_id)` 幂等落库，再锁定 WorkOrder Budget Ledger，检查 WorkOrder 活动状态、商业授权、父子拓扑、最大深度、总 AgentRun 数、并发、Policy、Capability、Provider 和 Workspace/Sandbox 隔离。Accepted Decision 与 Child AgentRun、RunManifest、AgentRunBudgetAllocation、Runtime Start Outbox 和 Platform Event 同事务；Rejected Decision 不创建任何执行或 Sandbox。`subagent_spawn_decision` Command 只回告已提交的决定，不是创建事实。

Child 的 Workspace 请求不能只保留在 SpawnRequest。Accepted Decision、RunManifest 与 Runtime Start 必须固化同一个 AgentRunWorkspaceBinding：`read_only_parent_revision` 只读挂载且禁止 Commit；`isolated_revision` 以 Parent Revision 建立 Copy-on-write 层，完成后产生独立 Revision 并按 `expected_workspace_head_version` Merge CAS；`shared_branch_cas` 允许直接提交同一 Branch，但每次 Commit 仍执行 Workspace Head CAS。模式、Base Revision、Mount Access 或 Commit Policy 不一致即拒绝 Start，不能把隔离请求降级为共享写入。

ExecutionBudget 是 WorkOrder 共享硬上限，所有 Model/Tool/Artifact/Egress Gateway、Sandbox Lease 和 Runtime Admission 对同一个 PostgreSQL Ledger 原子扣减或预留；AgentRunBudgetAllocation 只包含 token、请求、Sandbox 时间、网络、存储、Artifact 和转换等单 Run 资源上限，不能复制共享额度或 Agent 数/深度/并发上限。Root 终态不自动结束 WorkOrder：全部 required Child 必须终态，且不得存在任何活动 Child。取消、暂停、失败与部分完成的汇总规则由 WorkOrder Workflow 固化；对账器扫描终态 WorkOrder、失联 Parent、无进展 Runtime 和缺失 Event Cursor，发现孤儿 Child 后提高 Fencing、取消并对账。

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

RunManifest 精确绑定已消费 ExecutionGrant 的请求 Contract/Profile/Digest，并固化实际有界输入或不可变输入引用、ContextPackage、ArtifactAccessRequirement、初始 ExecutionBudget/PolicyDecision/EffectivePermissions 上限、CommercialAuthorizationBinding（ID/Digest/`expires_at`）、授权续期规则以及 Model/Tool/Artifact/Egress Gateway Binding。Start Runtime 携带本 InvocationAttempt 的短期 RuntimeAuthorization 和 ArtifactGrant；Authorization 的内部 Tenant/WorkOrder/Commercial 绑定必须闭合，且自身与 ArtifactGrant 均不得越过商业授权期限。到期、Adapter 重启或 Resume 时以连续前驱摘要创建等价/缩权 Revision，扩权必须新建 WorkOrder。Capability 长任务使用操作级 Token：Invoke、Status、Cancel 和 Event 各自绑定正式 Contract/Profile/Digest；Invoke `execution` 不越过原 request deadline/CommercialAuthorization，后续前驱 `jti` 链只提供无 Artifact/副作用权限的 `safety_control` 以完成取消和对账。所有 Token 的 `sub` 匹配当前 Workload Identity。Temporal History 只传内容寻址引用和必要控制字段，不复制大 Payload；Provider 收到摘要占位但拿不到执行值必须 fail-closed。
