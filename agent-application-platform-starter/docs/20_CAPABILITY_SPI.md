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

## 1. CapabilityDefinition

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

## 2. 命名治理

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

## 3. Plugin 实现声明

Plugin 只声明：

```yaml
implements:
  capability: html.generate
  version_range: ">=1.0.0 <2.0.0"
  profiles: [responsive]
```

## 4. 生命周期

- experimental
- stable
- deprecated
- retired

Deprecated 必须声明 Sunset、Replacement 和迁移窗口。

## 5. 一致性验证

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

## 6. 不可变解析结果

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
