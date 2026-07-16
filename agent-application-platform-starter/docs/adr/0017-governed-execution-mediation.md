# ADR-0017：Agent Runtime 必须经过执行治理中介

## Status

Accepted

## Context

ExecutionGrant 声明模型 Token、工具、网络和审批限制，但 DeerFlow 若可直连模型、MCP 或公网，这些限制无法被平台强制执行。

## Decision Drivers

- 预算强制执行
- 统一 Usage
- Secret 最小化
- 外部副作用审计

## Considered Options

- 仅 Prompt 约束
- 每个 Runtime 自行实现
- 平台 Model/Tool/Egress Gateway

## Decision

公共 SaaS Runtime 必须通过 Model Gateway、Tool/MCP Gateway、Artifact Gateway 和 Sandbox Egress Gateway，并通过 Governed Runtime Conformance。

## Consequences

- Grant 变为可执行策略
- 增加 Gateway 复杂度和延迟
- 私有可信部署可使用不同 Profile

## Risks

- Runtime 绕过 Gateway
- Gateway 成为容量瓶颈
- 模型流式响应计量偏差

## Migration Plan

- Phase 0 建立 Port
- DeerFlow Adapter 拦截模型与工具
- 逐步迁移直连 Provider

## Validation

- 预算硬限制测试
- 绕过检测
- Usage 对账
- Egress 负向测试
