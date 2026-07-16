# ADR-0020：Canonical Event 使用 Event Type Registry

## Status

Accepted

## Context

统一 Envelope 不能保证 data 结构稳定，且 occurred_at 可能受到来源时钟影响；高频 Token Delta 还可能造成存储和锁竞争。

## Decision Drivers

- Projection 安全
- 数据演进
- 可控留存
- 事件容量

## Considered Options

- 任意 data
- 每个事件独立代码 DTO
- Event Type Registry + Data Schema/Digest

## Decision

每个核心 Event Type 注册 data_version、SchemaReference、分类和留存；事件保存 occurred_at 与 recorded_at；Token Delta 批量合并。

## Consequences

- 消费者可验证
- 需要维护 Registry
- Plugin 私有事件不能直接驱动核心 Projection

## Risks

- 事件 Schema 漂移
- 敏感数据进入 Event
- WorkOrder 热点

## Migration Plan

- 先注册核心事件
- 为旧事件提供 Upcaster

## Validation

- Projection 重建
- Cursor Retention 410
- Delta 容量测试
