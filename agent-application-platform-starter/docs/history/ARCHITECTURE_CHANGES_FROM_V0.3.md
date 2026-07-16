# v0.3 到 v0.4 的修正

## 已删除或替换

- 删除 Agent Platform 内完整 User/Membership 模型。
- 商业 Entitlement 改为业务系统签发 ExecutionGrant。
- 删除重复 Extension 核心概念，统一为 Plugin。
- Plugin 不再能替换 Event Store、Workflow State、Artifact Metadata 等稳定内核。
- 不再建议自研生产级 Durable Workflow，默认使用 Temporal。
- Event 改为关系当前状态 + Append-only Timeline，不采用全量 Event Sourcing。
- 增加 WorkOrder、UsageReport、DeliveryPackage 和 WorkSession 边界。
- 增加 Artifact Workspace、EditSession 和不可变版本。
- 增加 side-effect classification，限制危险 Fallback。
- 增加 Outbox/Inbox、DLQ、Cancellation 和幂等语义。
- 明确业务前端通过短期 WorkSession 访问 Agent Workbench。
- 第一阶段进一步收敛为 Phase 0 架构骨架。
