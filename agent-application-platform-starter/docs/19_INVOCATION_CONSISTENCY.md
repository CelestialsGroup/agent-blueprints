# Invocation Ledger 与副作用一致性

## 1. 边界

Temporal Activity 可能重复调度，网络调用可能超时，外部 Provider 可能已经成功但响应丢失。

所有 Agent Runtime、Plugin、Model、Tool 和外部系统调用必须经过 Invocation Ledger，
除非明确属于受控 Runtime 内部的纯计算事件。

## 2. 对象

- Invocation：一次稳定逻辑操作
- InvocationAttempt：一次真实提交
- InvocationResult：已确认结果
- ExternalOperation：Provider Operation ID
- ReconciliationCase：Outcome Unknown 对账
- ManualReviewCase：无法自动确认时的人工裁决

## 3. 稳定标识

Invocation：

```text
workflow_run_id
+ workflow_step_id
+ logical_operation_key
```

Attempt：

- invocation_attempt_id
- attempt_number
- fencing_token
- request_digest

同一个逻辑操作的重试复用 Invocation ID，但创建新的 Attempt。

## 4. Prepare Attempt

数据库事务：

1. 锁定 Invocation。
2. 比较 Request Digest。
3. 检查 Retry Policy、Deadline、Budget 和 Cancellation。
4. 创建递增 Attempt。
5. 原子增加 Fencing Token。
6. 写 `invocation.attempt.prepared` Event。
7. Commit。

## 5. External Call

调用携带：

- invocation_id
- invocation_attempt_id
- attempt_number
- idempotency_key
- fencing_token
- deadline
- cancellation context
- Artifact grants

## 6. Complete

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

## 7. Retry

Retryable Failure：

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

## 8. Outcome Unknown 与 Reconciliation

```text
executing
 -> outcome_unknown
 -> reconciling
 -> succeeded | failed | manual_review
```

Reconciliation 必须定义：

- Deadline
- Query Strategy
- Evidence
- Backoff
- Maximum Attempts
- Ownership
- Alert

超过 Deadline 进入 `manual_review`，不能永久停留在 reconciling。

## 9. Manual Review

允许的决策：

- resolve_success
- resolve_failure
- abandon

必须记录：

- operator principal
- evidence references
- decision
- reason
- risk acceptance
- occurred_at

`abandoned` 是独立终态，后续若发现真实结果，只能追加 Correction Event，不修改历史决定。

## 10. Side-effect Class

- pure：允许自动重试
- idempotent：稳定 Idempotency Key
- externally_idempotent：Provider 业务唯一键
- non_idempotent：默认不自动重试

Fencing Token 只能防止平台接受旧结果，不能撤销已经发生的外部副作用。

## 11. Sandbox Operation Ledger

Sandbox Operation 使用同样的 Attempt/Fencing/Outcome Unknown 原则，但保留专用：

- Desired/Observed State
- Lease
- Snapshot
- RuntimeSession
- Generation

不能把完整 Sandbox 生命周期压缩成普通 Plugin Result。
