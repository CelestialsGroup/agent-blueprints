# Workflow 与可靠性

## 1. Temporal

Temporal 是 Durable Workflow Runtime。

Workflow Runtime Port 隔离 SDK，但不得隐藏以下语义：

- Workflow ID
- Worker Deployment
- Build ID
- Versioning Behavior
- Signal
- Cancellation
- Continue-as-New

## 2. WorkOrder 启动

WorkOrder 数据库事务只写 Workflow Start Outbox。

Dispatcher 以稳定 Workflow ID 启动：

```text
work-order/<work_order_id>
```

重复 Dispatch 必须复用同一 Workflow Execution 或安全返回已存在结果。

Workflow 启动后通过幂等 Domain Activity 将 WorkOrder 从 accepted 转为 queued/running。

## 3. 权威状态

PostgreSQL 是 API 当前状态事实源。

Temporal 是执行控制事实源。

所有对外状态变化由幂等 Domain Activity 更新 PostgreSQL，并在同一事务写 Event/Outbox。

Reconciliation 检测 Temporal 与 PostgreSQL 漂移。

## 4. External Side Effects

Temporal 不提供外部副作用 Exactly-once。

所有外部调用通过 Invocation Ledger。

## 5. Worker Versioning

每个 Worker 使用：

- Worker Deployment Name
- Build ID
- 明确 Versioning Behavior

建议：

- 有界 WorkOrder Workflow：Pinned
- 长期 Entity/Conversation Workflow：Auto-Upgrade + Patching，或在 Continue-as-New 边界升级

禁止笼统假设所有运行中 Workflow 永远固定同一版本。

## 6. History 与 Payload

- 大文件和 Artifact 只传 Reference/Digest。
- Prompt 和敏感 Payload 使用加密 Payload Codec。
- Activity Result 大小受限。
- 长期 Workflow 使用 Continue-as-New 控制 History。
- Temporal Namespace Retention 与数据删除策略一致。

## 7. Timeouts

Capability Timeout 映射到：

- Schedule-to-Start
- Start-to-Close
- Heartbeat
- Retry Policy

长任务必须 Heartbeat 并响应 Cancellation。

## 8. Sandbox Workflow

Sandbox 创建、Lease、Exec、Snapshot、Restore、Terminate 都是异步 Operation。

Workflow 必须：

- 使用稳定 Sandbox ID 和 Operation ID
- 重试时复用逻辑操作
- 处理 outcome_unknown
- 等待 durable Sandbox Event 或查询 Operation
- 在取消时先阻止新 Exec，再取消活动 Operation，最后终止 Sandbox
- Lease 续期必须受 ExecutionBudget 限制
