# Capability SPI 规范

## 关系模型

```text
Scenario
 -> CapabilityDefinition
 -> ProviderResolution
 -> immutable ProviderRevision
 -> ProviderAdmissionDecision
 -> Plugin / Runtime / Sandbox Provider
```

Scenario 只声明版本范围、Profile、Artifact 和风险要求，不绑定实现。

## CapabilityDefinition

Capability 是版本化语义契约，必须定义：

- Namespace 所有者
- 语义版本
- kind
- 不可变的 Request/Result/Error SchemaReference
- 副作用分类
- 幂等范围
- 取消能力
- 进度
- 状态查询
- 超时
- Artifact 契约
- 生命周期
- 一致性测试套件

SchemaReference 包含：

- 绝对 URI
- SHA-256 摘要
- JSON Schema 方言

## 命名治理

平台核心能力保留稳定短名称：

```text
agent.general
html.generate
artifact.preview.html
converter.html-to-pptx
template.html.generate
runtime.recording.playback
```

第三方专用能力使用发布者命名空间。

Capability Registry 维护 Owner，禁止名称抢占。

## Plugin 实现声明

Plugin 只声明：

```yaml
implements:
  capability: html.generate
  version_range: ">=1.0.0 <2.0.0"
  profiles: [responsive]
```

## 生命周期

- experimental
- stable
- deprecated
- retired

Deprecated 必须声明 Sunset、Replacement 和迁移窗口。

## 一致性验证

ProviderInstance 只有通过目标 Capability Version 的标准套件才能 healthy。

测试包括：

- Schema
- Error
- Idempotency
- Cancel
- Progress
- Timeout
- Status Query
- Artifact Validation
- Budget/Policy Profile（适用时）

## 不可变解析结果

Run 不能只保存 ProviderInstance ID。

ProviderResolution 必须固化：

- CapabilityDefinition 摘要
- ProviderRevision ID
- Plugin 版本
- Manifest 摘要
- Image 摘要
- Configuration 摘要
- Conformance Report 摘要

用户可见的 Experience 在 Provider Resolution 之上增加不可变 Catalog Revision。只有可变 `template_id` 绝不足以支持 WorkOrder 准入或 Run 回放。

Resolver 优先级是 Tenant Binding、ClientApplication Binding、Scenario Requirement、Platform Default、显式安全 Fallback。Fallback 只有在 Capability 与 side-effect policy 允许时才能发生；非幂等外部操作禁止自动切换 Provider。

Sandbox 使用独立 Provider Contract 表达 Desired/Observed State、Lease、Exec、RuntimeSession 和 Snapshot，不能用普通 Plugin Invocation 代替；它仍使用同一 ProviderRevision/Admission/Conformance 治理模型。

## Agent Runtime Provider 解析

Agent Runtime 使用同一 Revision/Admission/Conformance 治理，但不能按平台级默认框架直接选择。Resolver 必须结合 Scenario 所需 Runtime Feature/Profile、Tenant/Client Binding、数据驻留、模型/工具兼容性、容量和健康状态。

每个新 Run 解析并锁定一个 Agent Runtime ProviderRevision。运行中的 Run 不允许因健康、成本或偏好变化自动切换框架；Provider Fallback 只适用于尚未开始的新 Run。框架原生 Checkpoint 只有在源和目标 Revision 明确声明兼容且对应测试通过时才能恢复。

冻结 AgentRuntimeProvider v1 前，至少两个 Adapter 必须通过 `runtime-core-v1`，承担通用 Agent 主链路的 Provider 还必须通过 `runtime-general-v1 + governed-v1`。这用于证明 CapabilityDefinition、ProviderResolution、RunManifest、Workbench Event 和 Artifact/Usage 契约没有按 DeerFlow 或其他单一框架定制。
