# ADR-0013：Invocation Ledger 保护外部副作用

## Status

Accepted

## Context

Temporal Activity 和网络调用可能重复、超时或产生 outcome unknown。

## Decision Drivers

- 外部副作用安全
- 幂等
- 可对账

## Considered Options

- 依赖 Temporal 重试
- 每个 Provider 自行处理
- 统一 Invocation Ledger

## Decision

所有外部能力调用先登记稳定 Invocation，Attempt 使用 fencing token。结果确认后事务性写 Artifact、Usage、Event 和 Outbox。outcome_unknown 进入 Reconciliation。

## Consequences

- 统一故障语义
- 增加数据模型和清理任务
- Provider 需要 status query 或业务幂等

## Risks

- Ledger 状态与 Provider 状态不一致
- 错误自动重试

## Migration Plan

- 先覆盖 Plugin、Agent Runtime 与 Tool 调用
- 提供对账任务

## Validation

- 故障注入
- 超时成功场景
- stale fencing token 测试
