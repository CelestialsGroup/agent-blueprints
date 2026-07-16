# ADR-0021：Sandbox 使用独立 Provider Contract

## Status

Accepted

## Context

当前平台先使用 DeerFlow Built-in Sandbox，未来将切换到自研 `sandbox-runtime`。
Sandbox 拥有生命周期、Lease、Exec、RuntimeSession、Snapshot、网络和资源计量，
无法仅靠通用 Plugin Invocation 完整表达。

## Decision Drivers

- 不绑定 DeerFlow 内部实现
- 支持 Kubernetes、多 Runtime 和多节点
- 可安全切换 Provider
- 前端与 Artifact 协议保持稳定
- 明确安全和资源治理

## Considered Options

- 直接依赖 DeerFlow Sandbox API
- 将 Sandbox 作为普通 Plugin Capability
- 建立独立 Sandbox Provider Contract

## Decision

Agent Platform 稳定内核拥有 SandboxRegistry、Desired State、Lease、
Operation、RuntimeSession 授权和 Usage 归一化。

DeerFlowSandboxAdapter 与 `sandbox-runtime` 实现同一 Sandbox Provider API。
Run 锁定不可变 Sandbox ProviderRevision、RuntimeProfile、Spec Digest 和
Conformance Report Digest。

## Consequences

- 后续切换不修改 WorkOrder、Workflow、Artifact 和前端
- 需要维护专用 Sandbox OpenAPI、Schema 和 Conformance Suite
- Provider 必须处理幂等、Generation、Attempt 和 Fencing
- 后端专用字段只能存在于 Adapter 内部

## Risks

- Provider 声明 Capability 与实际行为不一致
- Snapshot 被误认为跨 Provider 可移植
- Runtime Endpoint 泄漏
- Controller 故障产生孤儿 Sandbox

## Migration Plan

1. 建立 SandboxProvider Port。
2. 用 DeerFlowSandboxAdapter 包装现有实现。
3. sandbox-runtime 通过 Conformance。
4. Shadow/Canary。
5. 默认 Binding 切换。
6. DeerFlow Provider Draining。

## Rollback Plan

将新 WorkOrder Binding 切回 DeerFlow ProviderRevision；运行中 Sandbox 按原
Revision 完成或取消。只有声明兼容的 Workspace Snapshot 才允许跨 Provider 恢复。

## Validation

- Provider API OpenAPI lint/bundle
- Schema positive/negative fixtures
- Lifecycle/Concurrency/Security Conformance
- Multi-node failure injection
- Canary and rollback drill
