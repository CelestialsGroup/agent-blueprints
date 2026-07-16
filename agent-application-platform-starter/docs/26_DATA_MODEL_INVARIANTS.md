# Data Model Invariants — v0.8.5

以下约束必须由 PostgreSQL migration/constraint 实现，不能只由应用代码约定。

## Identity and work

- `(tenant_id, external_subject)` 唯一；所有业务表显式 tenant_id。
- `work_orders(tenant_id, idempotency_key_digest)` 唯一。
- ExecutionGrant `jti` 单次消费，消费记录唯一；过期时间、request/scenario/idempotency digest 必须匹配。

## Invocation

- `invocations(invocation_id)` 主键；`logical_invocation_key` 唯一。
- `invocation_attempts(attempt_id)` 主键；`(invocation_id, attempt_number)` 唯一。
- `(invocation_id, fencing_token)` 唯一且新 Attempt token 单调递增。
- 一个 Attempt 只能绑定 Result 或 Error；succeeded 必须有 Result，failed/outcome_unknown 必须有相应 Error。
- Invocation active 状态必须绑定 current_attempt_id；`attempt_count <= max_attempts` 必须有 CHECK/事务约束。
- outcome_unknown/reconciling/manual_review 必须绑定 InvocationReconciliationCase；abandoned 与 non-idempotent retry_scheduled 必须同时绑定 resolved Case 和 append-only InvocationManualReviewDecision。Decision 的 case_id/version/digest、证据与 outcome 必须匹配；abandon 还必须 `risk_accepted=true`。
- Invocation 与 Sandbox 的 cancelled 只能引用 `not_started` 或 `stopped_before_effect` 证据；已完成副作用不得记为取消成功。

## Sandbox

- `sandboxes(sandbox_id)` 主键；`(workspace_id, sandbox_slot_key)` 对非终态 Sandbox 唯一。
- `primary_sandbox_slot_key` 必须通过延迟约束/事务校验引用恰好一个 Workspace Sandbox。
- `sandbox_operations(operation_id)` 主键；`logical_operation_key` 唯一；只保存当前 Attempt 指针/编号聚合，不复制 Attempt 结果历史。
- `sandbox_operation_attempts(attempt_id)` 主键；`(operation_id, attempt_number)` 和 `(sandbox_id, fencing_token)` 唯一。
- Attempt append-only；Operation current_attempt_id 只能引用自己的 Attempt；`current_attempt_number <= max_attempts` 必须有 CHECK/事务约束。
- `sandbox_reconciliation_cases(case_id)` 主键；每个未关闭 Operation 最多一个 open Case。
- `sandbox_manual_review_decisions(decision_id)` 主键、decision_digest 唯一、append-only；必须引用 Case 和证据。
- abandoned Operation 必须引用 resolved Case 和 ManualReviewDecision；Decision 必须匹配 Case ID/version/digest/evidence/outcome，且 `decision=abandon` 必须同时满足 `risk_accepted=true`；未知副作用不得仅凭取消请求写入 cancelled。
- 稳定表禁止 Pod/Namespace/Container/VM/Node/raw endpoint 列；Adapter 私有表必须与稳定模型分 schema/权限。

## Provider

- `provider_revisions(provider_revision_id)` 主键、provider_revision_digest 唯一；Update/Delete 权限撤销，只允许 Insert。
- 每个 ProviderRevision（包括 Model/Tool/Skill/Renderer）都必须有 `conformance_set_digest`；CapabilityResolution 的 definition digest、允许 Provider Kind 和 conformance 覆盖必须在 Admission 时校验。
- `provider_admission_decisions(decision_id)` 主键；`(provider_revision_id, decision_sequence)` 唯一且 append-only。
- sequence 必须从 1 连续递增；sequence=1 不得有 supersedes，sequence>1 必须引用同 Revision 紧邻上一 decision；revoked 必须有 reason。
- 新 Run 只能选择 latest decision=certified 的 Revision；RunManifest 保留 revision/decision digest，后续撤销不改写历史 Run。

## Workflow and event

- Temporal Workflow ID 与平台 run_id 唯一绑定；workflow_run_id append-only。
- Canonical Event `(aggregate_type, aggregate_id, aggregate_sequence)` 唯一；event_id 全局唯一。
- Outbox row 与业务变更同事务；Inbox `(consumer, message_id)` 唯一。

## Artifact and delivery

- `(artifact_id, version_number)` 唯一；ArtifactVersion 不可变。
- staging/finalization 使用 expected digest/size；未 finalized 不可交付。
- DeliveryAttempt `(delivery_id, attempt_number)` 唯一；回调只能引用预注册 target，不接受任意 URL。

## Redis prohibition

Redis 不得承载唯一状态、账本、游标真相或授权结论。清空 Redis 后系统必须能从 PostgreSQL、Temporal 和对象存储恢复正确性。
