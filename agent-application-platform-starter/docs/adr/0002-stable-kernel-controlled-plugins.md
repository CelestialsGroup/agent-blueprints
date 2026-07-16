# ADR-0002：稳定内核与受控 Plugin

## Status

Accepted

## Context

系统需要高度可扩展，但若 WorkOrder、Event、Artifact 等核心也允许插件替换，平台将无法保持一致性和安全边界。

## Decision Drivers

- 稳定性
- 插件隔离
- 统一审计
- 可替换执行能力

## Considered Options

- 所有模块插件化
- 无插件机制
- 稳定内核加受控扩展点

## Decision

Authentication、Grant、WorkOrder、Workflow State、Invocation Ledger、Event、Artifact Version、Usage、Delivery 和 Audit 属于稳定内核。Agent Runtime、Sandbox、Tool、Renderer、Editor 与 Converter 可以插件化。

## Consequences

- 扩展边界清晰
- 某些定制必须通过核心 API 实现
- 降低插件自由度

## Risks

- 核心接口设计错误会影响全部插件
- 插件能力可能不足

## Migration Plan

- 优先定义 Port
- 通过 Capability 扩展而非修改内核

## Validation

- 架构依赖测试
- 插件权限测试
- 禁止数据库直接访问
