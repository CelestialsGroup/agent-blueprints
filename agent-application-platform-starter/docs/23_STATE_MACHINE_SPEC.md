# State Machine Specification — v0.8.3

JSON 状态机是状态名称与迁移的权威事实源；Schema 定义允许状态集合，`validate_semantics.py` 强制两者一致、终态无出边且终态可达。

## WorkOrder

权威文件：`contracts/state-machines/work-order-v1.json`。状态集合与 `work-order-state.schema.json` 完全一致：accepted、queued、running、waiting、paused、cancel_requested、cancelling、completed、partial、failed、cancelled。

`waiting` 的具体原因（input/approval/resource）属于 wait reason，不拆成冲突的顶层状态。取消经过 cancel_requested/cancelling；完成与取消竞态以实际持久化结果为准。

## Invocation

权威文件：`contracts/state-machines/invocation-v1.json`。状态集合与 `invocation-record.schema.json` 一致：prepared、executing、retry_scheduled、outcome_unknown、reconciling、manual_review、succeeded、failed、cancel_requested、cancelled、abandoned。

取消请求不是取消证明。执行中的 Invocation 必须等待 Provider 确认；未知结果进入 outcome_unknown/reconciling。

## SandboxOperation

权威文件：`contracts/state-machines/sandbox-operation-v2.json`。Provider transport 的 outcome_unknown 进入平台 reconciling。running 取消先进入 cancel_requested；reconciling/manual_review_required 只记录 cancellation intent，不能直接进入 cancelled。Provider 或人工证据先进入 `cancellation_confirmed`，终态记录落库后才进入 `cancelled`；平台证明尚未派发或不存在 in-flight Attempt 时可以安全终止。

SandboxOperationRecord、Attempt、ReconciliationCase 和 ManualReviewDecision 均持久化。abandon 必须由 `risk_accepted=true` 的 append-only 决策触发。

## Enforcement

- 状态更新使用数据库 expected-state/fencing 条件；
- 迁移、Event 与 Outbox 同事务；
- Schema 约束状态相关字段；
- 语义 Gate 约束跨字段、状态机/Schema 一致性和取消证据。
