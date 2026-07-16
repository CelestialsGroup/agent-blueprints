# State Machine Specification — v0.8.2

状态迁移必须以原子 PostgreSQL 更新、append-only Event 与 Transactional Outbox 同时落盘。Temporal 发起命令但不能绕过数据库 fencing/transition guard。

## WorkOrder

`accepted -> queued -> running -> {waiting_input, waiting_approval, succeeded, failed, cancelled}`；waiting 状态可回到 running。终态不可回退。

## Invocation

`pending -> running -> {succeeded, failed, retry_scheduled, reconciling, cancel_requested}`。结果未知必须进入 reconciling；对账可解析为 succeeded/failed、调度新 Attempt 或进入 manual review/abandoned。Attempt append-only，fencing_token 严格递增。

## SandboxOperation v2

权威机器：`contracts/state-machines/sandbox-operation-v2.json`。

| Current | Event | Next |
|---|---|---|
| pending | attempt_started | running |
| running | attempt_succeeded | succeeded |
| running | attempt_known_failed | failed |
| running | retryable_failure | retry_scheduled |
| running | outcome_unknown | reconciling |
| retry_scheduled | retry_due | running |
| reconciling | evidence_succeeded | succeeded |
| reconciling | evidence_failed | failed |
| reconciling | retry_approved | retry_scheduled |
| reconciling | deadline_expired | manual_review_required |
| manual_review_required | resolve_success | succeeded |
| manual_review_required | resolve_failure | failed |
| manual_review_required | retry_approved | retry_scheduled |
| manual_review_required | abandon | abandoned |
| pending/running/retry_scheduled/reconciling/manual_review_required | cancel | cancelled |

平台持久化对象：SandboxOperationRecord（逻辑聚合）、SandboxOperationAttempt（不可变网络尝试）、SandboxReconciliationCase（证据与截止时间）、SandboxManualReviewDecision（不可变人工结论）。Provider API 返回 `SandboxOperationStatus`，不能直接覆盖平台聚合。

## Artifact staging

`staging -> uploaded -> verifying -> finalized`，任何失败进入 `quarantined|failed`。只有 finalized ArtifactVersion 可交付；同一 Artifact 的 version_number 和 current pointer 由数据库约束保护。

## Enforcement

- Schema 约束状态相关字段；
- JSON 状态机定义允许迁移；
- `validate_semantics.py` 验证可达性、重复迁移和 Attempt/Fencing 反例；
- 实现必须使用 `WHERE current_state = expected AND fencing_token < incoming` 形式的条件更新。
