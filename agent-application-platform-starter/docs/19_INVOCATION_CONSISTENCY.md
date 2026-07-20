# Invocation 账本与副作用一致性

## 边界

Temporal Activity 可能重复调度，网络调用可能超时，外部 Provider 可能已经成功但响应丢失。

所有 Agent Runtime、Capability Provider、兼容 Plugin、Model、Tool 和外部系统调用必须经过 Invocation Ledger，
除非明确属于受控 Runtime 内部的纯计算事件。

## 对象

- Invocation：一次稳定逻辑操作
- InvocationAttempt：一次真实提交
- InvocationResult：已确认结果
- ExternalOperation：Provider Operation ID
- InvocationReconciliationCase：未知结果对账
- InvocationManualReviewDecision：无法自动确认时的仅追加人工裁决

## 稳定标识

Invocation 标识：

```text
workflow_run_id
+ workflow_step_id
+ logical_operation_key
```

Attempt 属性：

- invocation_attempt_id
- attempt_number
- fencing_token
- request_digest

同一个逻辑操作的重试复用 Invocation ID，但创建新的 Attempt。

Capability Provider 的长任务控制不创建新的逻辑 Invocation。Invoke、Status、Cancel 和 Event 各使用操作级短期 Token；Token 同时绑定原始 Invocation Request Digest 与当前操作摘要，续期 sequence 连续并引用紧邻前驱 `jti`。这属于授权续期，不是传输重试，也不能改变 ProviderResolution、Tenant、WorkOrder、Policy、Budget、Permissions 或原 deadline。

## 准备 Attempt

数据库事务：

1. 锁定 Invocation。
2. 比较 Request Digest。
3. 检查 Retry Policy、Deadline、Budget 和 Cancellation。
4. 创建递增 Attempt。
5. 原子增加 Fencing Token。
6. 写 `invocation.attempt.prepared` Event。
7. Commit。

## 外部调用

调用携带：

- invocation_id
- invocation_attempt_id
- attempt_number
- idempotency_key
- fencing_token
- deadline
- cancellation context
- Artifact grants
- Tenant、ClientApplication、Principal Context 和 WorkOrder
- ProviderResolution/Instance/Revision/Audience、完整 PolicyDecision/ExecutionBudget/Permissions、原始与操作 Request Digest、ArtifactGrant 和 ArtifactStagingGrant

通用 Model/Tool/MCP/Skill/Renderer/Converter 调用使用 `capability-provider-v1` 和独立 Capability Invocation Token；`plugin_id` 只允许出现在兼容 Adapter 私有映射中。幂等唯一范围是 `(tenant_id, client_app_id, operation_id, idempotency_key_digest)`，同范围不同 Request Digest 必须返回 409。

## 完成

数据库事务：

1. 验证 Attempt。
2. 拒绝旧 Fencing Token。
3. 保存 Result/Error。
4. 验证并导入 Artifact Staging。
5. 写 Technical Usage。
6. 写 Canonical Event。
7. 写 Outbox。
8. 更新 Invocation。
9. Commit。

## 重试

可重试失败：

```text
Attempt -> failed_retryable
Invocation -> retry_scheduled
```

到达 Retry 时间后：

```text
创建新 Attempt
递增 attempt_number
递增 fencing_token
Invocation -> executing
```

禁止：

- 修改旧 Attempt 为 running
- 使用随机新 Invocation ID
- 在 Outcome Unknown 状态直接重试
- 超过 Invocation Deadline 后继续自动重试

## 未知结果与对账

```text
executing
 -> outcome_unknown
 -> reconciling
 -> succeeded | failed | manual_review
```

对账必须定义：

- Deadline
- Query Strategy
- Evidence
- Backoff
- Maximum Attempts
- Ownership
- Alert

超过 Deadline 进入 `manual_review`，不能永久停留在 `reconciling`。

## 人工复核

允许的决策：

- resolve_success
- resolve_failure
- resolve_cancelled
- retry
- abandon

必须记录：

- operator principal
- evidence references
- decision
- reason
- risk acceptance
- occurred_at

`abandon` 必须显式 `risk_accepted=true`，并由 InvocationRecord 同时引用 ReconciliationCase 和 `decision_id`。Decision 必须绑定 Case ID、版本、摘要及证据。非幂等重试也必须引用结果为 `retry_approved` 的已解决 Case 与决策为 `retry` 的 Decision；普通自动重试事件只适用于可幂等重试。`abandoned` 是独立终态，后续若发现真实结果，只能追加更正 Event，不修改历史决定。

取消请求只表示 intent。执行中先进入 `cancel_requested`；Provider/人工证据证明外部副作用 `not_started` 或 `stopped_before_effect` 后进入 `cancellation_confirmed`，持久化终态后才进入 `cancelled`。已完成的外部副作用不能记录为取消成功。

## 副作用分类

- pure：允许自动重试
- idempotent：稳定 Idempotency Key
- externally_idempotent：Provider 业务唯一键
- non_idempotent：默认不自动重试

Fencing Token 只能防止平台接受旧结果，不能撤销已经发生的外部副作用。

## Sandbox Operation 账本

Sandbox Operation 使用同样的 Attempt/Fencing/Outcome Unknown 原则，但保留专用：

- 期望状态/观测状态
- Lease
- Snapshot
- RuntimeSession
- Generation

不能把完整 Sandbox 生命周期压缩成普通 Plugin Result。
