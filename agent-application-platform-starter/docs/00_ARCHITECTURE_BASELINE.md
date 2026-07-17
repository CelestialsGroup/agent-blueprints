# v0.9.0 架构基线候选版本

Agent Application Platform 为多个 Business Application 提供受治理的多轮 Conversation、Agent 执行、工作流、Sandbox、Artifact、Runtime Recording 和 Delivery 能力。Business 与 Platform 不共享领域数据库。

## 所有权

- Business：User、Membership、Product、Order、Payment、Entitlement、Commercial Quota Reservation/Settlement。
- Platform：Conversation、Message、WorkOrder、Workspace、Workflow、Invocation、Event、Artifact、Technical Usage、Delivery、Provider、Sandbox、RuntimeRecording、Experience Catalog、Audit。

## 稳定内核与执行平面

稳定内核只保存可复现、可审计、与后端无关的标识和状态。Agent Runtime 框架、Sandbox 后端、模型、工具、Template、Renderer/Converter 都是 Provider Adapter。DeerFlow、LangGraph/Deep Agents、OpenAI Agents SDK 等只能作为参考或可选 Runtime 实现，不得成为平台能力前提。`Conversation binding + ProviderRevision + ProviderAdmissionDecision + ExperienceRevision + RunManifest` 固化一次 Run 的可重放输入。

## 持久化与可靠性

Temporal 保存持久 Workflow History；PostgreSQL 保存当前状态、Ledger、Outbox/Inbox 和元数据；兼容 S3 的 Storage 保存 Artifact Blob；Redis 仅用于 Cache/Presence/Wakeup。

系统承诺至少一次投递、幂等、Fencing、对账、事务 Outbox 和不可变版本，不承诺全局 Exactly-once。

## Sandbox

Conversation Workspace 拥有多个 Sandbox Slot。DeerFlow Built-in Sandbox 可作为首个参考 Sandbox Adapter，未来 `sandbox-runtime` 或其他实现使用相同契约；稳定内核禁止后端基础设施标识和原始 Endpoint。Runtime Gateway 可产生独立、加密、受保留策略管理的 RuntimeRecording。

## 状态

v0.9.0 是产品边界候选版本，不是已冻结基线，更不是生产就绪版本。
