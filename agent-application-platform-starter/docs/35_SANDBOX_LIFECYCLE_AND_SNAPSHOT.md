# Sandbox Lifecycle and Snapshot — v0.8.6

## Two state levels

Provider transport attempt 返回 `SandboxOperationStatus`：accepted/running/succeeded/failed/cancelled/outcome_unknown。平台不得把 outcome_unknown 作为持久化终点；它必须原子转换为 SandboxOperation `reconciling`。

平台逻辑聚合使用 `sandbox-operation-record:v2` 和 `contracts/state-machines/sandbox-operation-v2.json`，支持 retry、reconciliation deadline、manual review、安全取消确认和 abandoned。每个 Attempt 拥有新 attempt_id 与更高 fencing_token，旧响应被拒绝。

## Lease and lifecycle

SandboxRegistry 保存期望状态、租约、Slot 与代数；Provider Adapter 保存实际 Pod/VM/Container/endpoint。Lease 过期由 Temporal 定时器驱动 terminate/reconcile，不能依赖 Redis TTL 作为事实。

## Snapshot

SnapshotManifest 固化 provider_revision_id、level、digest、size、content_reference 和兼容性。workspace 级 Snapshot 可跨符合 Contract 的 Provider 迁移；filesystem/process 级默认只在声明兼容时恢复。

Restore 是标准 mutation envelope：operation_id、attempt_id、fencing_token、idempotency_key、request_digest、deadline_at。恢复后的 Sandbox 使用新 sandbox_id 和显式 slot；Snapshot 本身不可变。

## Reconciliation

Provider response 丢失时，先用 provider_operation_id/idempotency key 查询证据；不得盲目重试非幂等副作用。证据不足到 deadline 后进入人工复核；人工 Decision 必须 append-only、带 evidence references 和 digest。

取消请求只表达 intent。运行中请求先进入 `cancel_requested`；未知结果继续 reconciliation。只有 Provider/人工证据写入 `cancellation_confirmation` 并经过 `cancellation_confirmed`，或平台证明从未派发/当前无 in-flight Attempt，才允许终态 `cancelled`。无法证明时只能继续对账或由 `risk_accepted=true` 的人工决策 abandon。
