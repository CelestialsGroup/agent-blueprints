# Capability SPI

## 1. CapabilityDefinition

Capability 是版本化语义契约，必须定义：

- namespace owner
- semantic version
- kind
- immutable request/result/error SchemaReference
- side-effect class
- idempotency scope
- cancellation
- progress
- status query
- timeout
- Artifact contract
- lifecycle
- conformance suite

SchemaReference 包含：

- absolute URI
- SHA-256 digest
- JSON Schema dialect

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

## 3. Plugin Implements

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

## 5. Conformance

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

## 6. Immutable Resolution

Run 不能只保存 ProviderInstance ID。

ProviderResolution 必须固化：

- Capability Definition Digest
- Provider Revision ID
- Plugin Version
- Manifest Digest
- Image Digest
- Configuration Digest
- Conformance Report Digest

User-visible Experiences add an immutable Catalog revision on top of Provider resolution. A mutable `template_id` alone is never sufficient for WorkOrder admission or Run replay.
