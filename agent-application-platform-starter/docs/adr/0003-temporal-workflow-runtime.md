# ADR-0003：Temporal 作为 Durable Workflow Runtime

## Status

Accepted

## Context

Agent 工作可能持续数分钟到数天，并包含重试、Signal、Timer、取消、人工审批和子工作流。

## Decision Drivers

- 重启恢复
- 多节点 Worker
- 长时间等待
- Worker Versioning

## Considered Options

- 自研数据库状态机
- 普通任务队列
- Temporal

## Decision

使用 Temporal 管理 Durable Workflow。平台通过 WorkflowRuntime Port 隔离 Temporal SDK；外部副作用仍必须经过 Invocation Ledger。

## Consequences

- 减少自研工作流引擎风险
- 引入独立基础设施和运维成本
- Workflow 代码需遵循确定性约束

## Risks

- 错误地认为 Temporal 提供全局 Exactly-once
- 不兼容 Worker 升级

## Migration Plan

- Phase 0 建立 Port 和本地环境
- 所有发布使用 Build ID

## Validation

- Worker 重启恢复
- Signal/Timer/Cancel 测试
- 版本兼容测试
