# 状态机规范 — v0.9.0

JSON 状态机是状态名称与迁移的权威事实源；Schema 定义允许状态集合，`validate_semantics.py` 强制两者一致、同一 `(from,event)` 唯一、终态无出边且全部状态从初始状态可达。

## WorkOrder

权威文件：`contracts/state-machines/work-order-v1.json`。状态集合与 `work-order-state.schema.json` 完全一致：accepted、queued、running、waiting、paused、cancel_requested、cancelling、completed、partial、failed、cancelled。

`waiting` 的具体原因（Input/Approval/Resource）属于等待原因，不拆成冲突的顶层状态。`accepted`、`queued`、`running`、`waiting` 和 `paused` 都可记录取消意图；取消经过 `cancel_requested`/`cancelling`，完成、部分完成或失败与取消竞态以先持久化的真实终态证据为准。`cancel_requested` 在取消派发开始前可以依据真实结果直接进入 `completed`/`partial`/`failed`；`accepted`、`queued`、`waiting` 和 `paused` 收到结构化且已确认的失败证据时可直接进入 `failed`，不得先制造虚假的 `queued` 或 `running` 迁移。

## Invocation

权威文件：`contracts/state-machines/invocation-v2.json`。状态集合与 `invocation-record.schema.json` 一致：prepared、executing、retry_scheduled、outcome_unknown、reconciling、manual_review、cancel_requested、cancellation_confirmed、succeeded、failed、cancelled、abandoned。

取消请求不是取消证明。执行中的 Invocation 必须等待 Provider 确认；未知结果进入 `outcome_unknown`/`reconciling`。InvocationRecord、Attempt、InvocationReconciliationCase 和 InvocationManualReviewDecision 均持久化；Decision 通过 `case_id + case_version + case_digest` 绑定准确 Case 快照。非幂等 Invocation 只能在已解决 Case 证明可重试且仅追加 Decision 明确批准后进入 `retry_scheduled`；`abandon` 只能由 `risk_accepted=true` 的决策触发。

## SandboxOperation

权威文件：`contracts/state-machines/sandbox-operation-v2.json`。Provider 传输层的 `outcome_unknown` 进入平台 `reconciling`。`running` 取消先进入 `cancel_requested`；`reconciling`/`manual_review_required` 只记录取消意图，不能直接进入 `cancelled`。Provider 或人工证据先进入 `cancellation_confirmed`，终态记录落库后才进入 `cancelled`；平台证明尚未派发或不存在执行中的 Attempt 时可以安全终止。

SandboxOperationRecord、Attempt、ReconciliationCase 和 ManualReviewDecision 均持久化。`abandon` 必须由 `risk_accepted=true` 的仅追加决策触发。

## Conversation

权威文件：`contracts/state-machines/conversation-v1.json`。`active` 可进入 `archived`，或在确认后进入 `deleted`；`archived` 可恢复或删除；`deleted` 是不可恢复 Tombstone。`archived`/`deleted` 状态分别要求审计时间，删除内容和保留审计记录是两项独立策略。

## AgentRuntimeRun

权威文件：`contracts/state-machines/agent-runtime-run-v1.json`。运行、等待输入、等待批准和暂停都只能先进入 `cancel_requested`，Provider 确认后才进入 `cancelled`。`outcome_unknown` 不是终态；只能通过 Invocation Ledger 的查询/对账证据回到活动状态或进入 `succeeded`/`failed`/`cancelled`。终态必须记录 `completed_at`，成功绑定结果，失败绑定结构化错误。

## RuntimeRecording

权威文件：`contracts/state-machines/runtime-recording-v1.json`。Capture 停止后进入 `finalizing`，只有完整 Manifest 原子提交后才能进入 `ready`；Capture/Finalization 失败进入带错误证据的 `failed`。`ready`/`failed` 内容可按保留策略删除，`deleted` 是不可逆 Tombstone。

## 强制执行

- 状态更新使用数据库 Expected-state/Fencing 条件；
- 迁移、Event 与 Outbox 同事务；
- Schema 约束状态相关字段；
- 语义 Gate 约束跨对象引用闭包、状态机 `(from,event)` 确定性、状态机/Schema 一致性和取消证据。
