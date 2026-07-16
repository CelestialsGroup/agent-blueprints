# ADR-0009：WorkOrder 范围 Event Cursor

## Status

Accepted

## Context

一个 WorkOrder 可以包含多个 AgentRun、Artifact 和 Conversion 事件；AgentRun 局部 sequence 无法支持 WorkOrder SSE 断点续传。

## Decision Drivers

- 无歧义 SSE
- 多 Run Timeline
- 跨 Pod 恢复

## Considered Options

- AgentRun sequence
- 全局数据库 sequence
- WorkOrder sequence 加 Aggregate sequence

## Decision

每个 WorkOrder 原子分配 work_sequence；每个 Aggregate 另有 aggregate_sequence。SSE 使用 work_sequence 和 Last-Event-ID。

## Consequences

- Timeline 顺序明确
- 每个 WorkOrder 有一个写入热点
- 需数据库原子更新

## Risks

- 高事件量 WorkOrder 行锁竞争
- 错误的 source cursor 去重

## Migration Plan

- Phase 1 使用 PostgreSQL 原子更新
- 高吞吐时可演进为单 Work Event Ingestor

## Validation

- 并发 sequence 唯一测试
- 多 AgentRun SSE 测试
