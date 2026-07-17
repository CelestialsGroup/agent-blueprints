# v0.9.0 Architecture Baseline Candidate

Agent Application Platform 为多个 Business Application 提供受治理的多轮 Conversation、Agent 执行、工作流、Sandbox、Artifact、Runtime Recording 和 Delivery 能力。Business 与 Platform 不共享领域数据库。

## Ownership

- Business：User、Membership、Product、Order、Payment、Entitlement、Commercial Quota Reservation/Settlement。
- Platform：Conversation、Message、WorkOrder、Workspace、Workflow、Invocation、Event、Artifact、Technical Usage、Delivery、Provider、Sandbox、RuntimeRecording、Experience Catalog、Audit。

## Stable kernel and execution plane

稳定内核只保存可复现、可审计、与后端无关的标识和状态。DeerFlow、Sandbox 后端、模型、工具、Template、Renderer/Converter 都是 Provider Adapter。`Conversation binding + ProviderRevision + ProviderAdmissionDecision + ExperienceRevision + RunManifest` 固化一次 Run 的可重放输入。

## Persistence and reliability

Temporal 保存 Durable Workflow History；PostgreSQL 保存当前状态、Ledger、Outbox/Inbox 和元数据；S3-compatible Storage 保存 Artifact Blob；Redis 仅 Cache/Presence/Wakeup。

系统承诺 At-least-once、Idempotency、Fencing、Reconciliation、Transactional Outbox 和 Immutable Version，不承诺全局 Exactly-once。

## Sandbox

Conversation Workspace 拥有多个 Sandbox Slot。DeerFlow Built-in Sandbox 与未来 `sandbox-runtime` 实现相同 Contract；稳定内核禁止后端基础设施标识和 raw endpoint。Runtime Gateway 可产生独立、加密、受保留策略管理的 RuntimeRecording。

## Status

v0.9.0 是产品边界候选版本，不是已冻结基线，更不是 Production Ready。
