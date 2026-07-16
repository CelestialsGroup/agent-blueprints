# Invocation Ledger 与副作用一致性

## 1. 边界

Temporal Activity 可能重复调度，网络调用可能超时，外部 Provider 可能已经成功但响应丢失。

所有 Agent Runtime、Plugin、Model、Tool 和外部系统调用必须经过 Invocation Ledger，除非明确属于受控 Runtime 内部的纯计算事件。

## 2. 对象

- Invocation：一次逻辑操作
- InvocationAttempt：一次真实提交
- InvocationResult：已确认结果
- ExternalOperation：Provider Operation ID
- ReconciliationCase：Outcome Unknown 对账

## 3. 标识

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

所有 Accepted、Progress、Result、Error、Status、Cancel 都必须携带 Attempt ID 和 Fencing Token。

## 4. Prepare

数据库事务：

- Upsert Invocation
- 比较 Request Digest
- 创建 Attempt
- 原子增加 Fencing Token
- 写 `invocation.prepared` Event
- Commit

## 5. External Call

调用携带：

- invocation_id
- invocation_attempt_id
- idempotency_key
- fencing_token
- deadline
- cancellation context
- Artifact grants

## 6. Complete

数据库事务：

- 验证 Attempt
- 拒绝旧 Fencing Token
- 保存 Result/Error
- 验证并导入 Artifact Staging
- 写 Technical Usage
- 写 Canonical Event
- 写 Outbox
- 更新 Invocation
- Commit

## 7. Outcome Unknown

无法确认结果时：

```text
executing -> outcome_unknown -> reconciling
```

禁止创建新的逻辑 Invocation 盲目重试。

## 8. Provider 约束

Fencing Token 只能防止平台接受旧结果；它不能自动撤销已经发生的外部副作用。

因此：

- idempotent 使用稳定 Provider Key
- externally_idempotent 使用业务唯一键
- non_idempotent 默认不自动重试
- 支持 Status Query 的 Provider 优先

## 9. Sandbox Operation Ledger

Sandbox Operation 与通用 Invocation 使用相同原则：

- 稳定逻辑 Operation
- Attempt
- Fencing
- Outcome Unknown
- Reconciliation

但 Sandbox 生命周期使用专用 SandboxOperation Contract，避免把 Desired/Observed State、Lease、Snapshot 和 RuntimeSession 压缩成通用 Plugin Result。
