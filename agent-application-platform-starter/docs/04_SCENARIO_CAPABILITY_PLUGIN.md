# Scenario、Capability、Provider 与 Plugin

## 1. 关系

```text
Scenario
 -> CapabilityDefinition
 -> ProviderResolution
 -> Immutable ProviderRevision
 -> PluginInstallation
```

## 2. Scenario

声明：

- immutable input SchemaReference
- definition digest
- workflow definition digest
- required/optional Capability Version Range
- delivery formats
- UI slot
- resource class
- risk requirements

## 3. Capability

CapabilityDefinition 是语义来源。

包含：

- owner namespace
- immutable schema refs
- side-effect/idempotency
- timeout/cancel/progress/status
- Artifact contract
- lifecycle
- conformance

## 4. Plugin

Plugin Manifest 声明：

- publisher
- package/runtime
- implements
- configuration schema
- credential requirements
- requested permissions
- provenance/SBOM

Trust 由 Platform Registry 决定。

## 5. ProviderRevision

ProviderInstance 是逻辑配置容器。

每次配置、镜像、权限或 Plugin 变更创建不可变 ProviderRevision。

Run 锁定 Revision，不锁定可变 Instance。

## 6. Resolver

```text
Tenant Binding
 -> ClientApplication Binding
 -> Platform Default
 -> Explicit Safe Fallback
```

Resolution 保存完整 Digest 与原因。

## 7. Fallback

仅在 Capability 与 Side-effect Policy 明确允许时发生。

非幂等外部操作禁止自动切换 Provider。

## 8. Sandbox Provider

Sandbox 是专用 Infrastructure Provider SPI，不使用任意 Plugin Invocation 代替其完整生命周期 Contract。

它仍通过 ProviderInstance/ProviderRevision 进行：

- 配置
- Version/Digest lock
- Capability resolution
- Health/draining
- Conformance

Scenario 和 AgentRuntime 只声明需要的 `sandbox.*` Capability。
