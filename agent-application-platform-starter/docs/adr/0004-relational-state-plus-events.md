# ADR-0004：关系当前状态加 Append-only Event

## Status

Accepted

## Context

平台既需要高效读取当前状态，也需要 Timeline、审计、回放与外部集成。

## Decision Drivers

- 查询效率
- 审计
- 事件重放
- 实现复杂度

## Considered Options

- 全量 Event Sourcing
- 仅关系状态
- 关系状态加追加事件

## Decision

PostgreSQL 关系表保存当前权威状态；Canonical Event 保存不可变执行事实；Projection 用于查询优化。事件不是全部领域状态的唯一来源。

## Consequences

- 读取简单
- 需要维护状态与事件的事务一致性
- Projection 可重建

## Risks

- 状态更新成功但事件丢失
- 事件 Schema 演进

## Migration Plan

- 所有状态变更事务内写 Event/Outbox
- 引入 Upcaster

## Validation

- 事务测试
- Projection 重建测试
- 历史事件兼容测试
