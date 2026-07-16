# v0.8.3 Architecture Baseline Candidate

Agent Application Platform 为多个 Business Application 提供受治理的 Agent 执行、工作流、Sandbox、Artifact 和 Delivery 能力。Business 与 Platform 不共享领域数据库。

## Ownership

- Business：User、Membership、Product、Order、Payment、Commercial Quota。
- Platform：WorkOrder、Workspace、Workflow、Invocation、Event、Artifact、Technical Usage、Delivery、Provider、Sandbox、Audit。

## Stable kernel and execution plane

稳定内核只保存可复现、可审计、与后端无关的标识和状态。DeerFlow、Sandbox 后端、模型、工具、Renderer/Converter 都是 Provider Adapter。`ProviderRevision + ProviderAdmissionDecision + RunManifest` 固化一次 Run 的可重放输入。

## Persistence and reliability

Temporal 保存 Durable Workflow History；PostgreSQL 保存当前状态、Ledger、Outbox/Inbox 和元数据；S3-compatible Storage 保存 Artifact Blob；Redis 仅 Cache/Presence/Wakeup。

系统承诺 At-least-once、Idempotency、Fencing、Reconciliation、Transactional Outbox 和 Immutable Version，不承诺全局 Exactly-once。

## Sandbox

Workspace 拥有多个 Sandbox Slot。DeerFlow Built-in Sandbox 与未来 `sandbox-runtime` 实现相同 Contract；稳定内核禁止后端基础设施标识和 raw endpoint。

## Status

v0.8.3 是已完成本地 re-hardening、等待 Git 根 Workflow 集成和 public CI re-admission 的候选版本，不是已冻结基线，更不是 Production Ready。
