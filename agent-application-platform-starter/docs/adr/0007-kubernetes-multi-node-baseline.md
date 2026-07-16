# ADR-0007：Kubernetes 多节点作为架构基线

## Status

Accepted

## Context

生产环境将使用 Kubernetes 多副本，任务和连接不能依赖单个 Pod。

## Decision Drivers

- 高可用
- 独立扩缩容
- 节点故障恢复

## Considered Options

- 单节点后期改造
- 依赖 Sticky Session
- 从第一阶段按无状态多副本设计

## Decision

Agent API 无状态；Workflow、Event、EditSession 与 Sandbox 状态外置；Runtime Gateway 路由双向连接；不依赖 Sticky Session。

## Consequences

- 减少后期重构
- 本地开发配置更复杂
- 要求共享基础设施

## Risks

- 错误使用 Redis 作为事实源
- Sandbox 泄漏

## Migration Plan

- 提供本地 Compose 和 K8s Base
- 建立多副本测试

## Validation

- Pod 删除测试
- 跨 Pod SSE 恢复
- Sandbox 接管测试
