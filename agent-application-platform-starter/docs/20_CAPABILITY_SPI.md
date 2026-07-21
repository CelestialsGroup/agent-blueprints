# Capability SPI 规范

## 关系模型

```text
Scenario
 -> CapabilityDefinition
 -> ProviderResolution
 -> immutable ProviderRevision
    -> ProviderImplementation + BuildProvenance
    -> ProviderPortBinding
 -> ProviderAdmissionDecision
 -> Capability / Runtime / Sandbox Provider
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

## Provider Implementation 与 Plugin

ProviderRevision 的公共部分不使用 `plugin_id/plugin_version`。它统一固化：

- `ProviderImplementation`：实现 ID/版本、分发类型与摘要；
- `BuildProvenance`：Source Revision、Source Tree、Build Artifact、SBOM 和 Provenance Statement 摘要；
- `ProviderPortBinding`：稳定协议、版本、契约摘要和部署绑定摘要；
- 配置、权限、凭据和 Conformance 摘要。

Plugin 只是 Tool、Skill、Template 等实现的一种打包方式，PluginManifest 不得污染 Agent Runtime、Sandbox、内置 Bundle 或远程服务的公共 Revision。

## 通用 Capability Provider Port

权威传输契约是 `contracts/openapi/capability-provider-v1.yaml`，覆盖 Invoke、Status、Cancel 和 attempt-local Event。Model、Tool、MCP、Skill、Template、Renderer、Editor、Converter 与 Catalog-backed Provider 均实现或适配该 Port；`plugin-invocation-v1` 只保留为旧 Plugin 的兼容协议，不能作为新 Provider 的公共前提。

CapabilityInvocationRequest 必须携带完整 ExecutionBudget、PolicyDecision、EffectivePermissions 与 CommercialAuthorizationBinding，并绑定 Tenant、ClientApplication、PrincipalContextSnapshot Digest、WorkOrder、ProviderResolution、ProviderInstance、ProviderRevision、admitted audience、Capability Schema Digest、InvocationAttempt、Fencing、Request Digest、ArtifactGrant 与 ArtifactStagingGrant。Provider 不得依赖未定义的摘要反查接口获取真实执行值。

Bearer Token 只授权一个 `invoke`、`status`、`cancel` 或 `read_events` 操作，同时绑定原始 Invocation Request Digest，以及当前操作的 `operation_contract_id + operation_digest_profile + operation_request_digest`。Status/Event 使用正式逻辑 Descriptor，HTTP 查询参数按 OpenAPI 默认值归一化后再计算摘要；初始 sequence 1 Token 使用 `execution` 且不越过原 request deadline/CommercialAuthorization，后续 Token 必须连续、引用紧邻前驱 `jti` 并固定为 `safety_control`，可在执行窗口结束后继续 Status/Cancel/Event 对账，但不继承已经过期的 ArtifactGrant/StagingGrant，也不能创建新副作用。所有 Token 最长 300 秒。ArtifactGrant/ArtifactStagingGrant 是非 Bearer 的有界执行授权；每次 Read/Stage/Commit 还必须使用绑定正式 Contract/Profile、Grant Digest 与操作摘要的 Artifact Gateway Token。Provider 不得接受只有 `plugin_id`、宽泛权限或未绑定摘要的令牌。写请求具有明确 encoded-byte 上限，超限必须在 JSON 解析前返回 413。

Provider 输出只包含 Structured Result、StagedArtifact 和 UsageObservation。UsageObservation 没有 Platform `entry_id`、Tenant/WorkOrder 归属、Idempotency Key 或 `recorded_at`；Platform 校验 Meter/Evidence/Attempt 后才创建 TechnicalUsageEntry。Provider 只能读取已授权 ArtifactVersion 或写 Staging，不能 Finalize 正式 ArtifactVersion。

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

- Tenant、ClientApplication、WorkOrder 执行范围，显式 `identity_dependency` 声明，以及身份参与解析时的 PrincipalContextSnapshot Digest；

- Resolver ID/Version/Digest；
- 完整解析输入摘要，包括 Capability、Policy、Placement、Health 和 Capacity；
- 每个候选的 Revision、Bearer Audience、结论、Reason Code 与 Evidence Digest；
- 不可变 Resolution Evidence Reference/Digest 和 Decision Digest；
- CapabilityDefinition 摘要
- ProviderRevision ID
- Implementation ID/版本和分发摘要
- BuildProvenance 与 Manifest 摘要
- 适用时的 Image 摘要
- Port Contract/Binding 摘要
- Configuration 摘要
- Conformance Suite ID/Version/Digest/Profile 与 Report 摘要

用户可见的 Experience 在 Provider Resolution 之上增加不可变 Catalog Revision。只有可变 `template_id` 绝不足以支持 WorkOrder 准入或 Run 回放。

Resolver 优先级是 Tenant Binding、ClientApplication Binding、Scenario Requirement、Platform Default、显式安全 Fallback。ProviderHealth 必须绑定精确 ProviderInstance、ProviderRevision 和 Health Generation；Cluster、Cell、Pod、Node 等可变部署拓扑不进入健康契约或历史解析证据。只保存可变 Instance 状态不能作为历史解析证据。Fallback 只有在 Capability 与 side-effect policy 允许时才能发生；非幂等外部操作禁止自动切换 Provider。

空 `limits` 没有默认或无限语义。商业授权、ExecutionGrant、ExecutionBudget 与 Provider 请求使用全字段 EffectiveExecutionLimits；任何缺失或无法解释的版本都 fail-closed。

Sandbox 使用独立 Provider Contract 表达 Desired/Observed State、Lease、Exec、RuntimeSession 和 Snapshot，不能用普通 Plugin Invocation 代替；它仍使用同一 ProviderRevision/Admission/Conformance/Resolution 治理模型。RunManifest 的 Sandbox Slot 只引用 `resolution_id`，不得再复制 Revision Snapshot。

## Agent Runtime Provider 解析

Agent Runtime 使用同一 Revision/Admission/Conformance 治理，但不能按平台级默认框架直接选择。Resolver 必须结合 Scenario 所需 Runtime Feature/Profile、Tenant/Client Binding、数据驻留、模型/工具兼容性、容量和健康状态。

每个新 Run 解析并锁定一个 Agent Runtime ProviderRevision。运行中的 Run 不允许因健康、成本或偏好变化自动切换框架；Provider Fallback 只适用于尚未开始的新 Run。框架原生 Checkpoint 只有在源和目标 Revision 明确声明兼容且对应测试通过时才能恢复。

冻结 AgentRuntimeProvider v1 前，自研 Native Runtime 与独立 Reference Contract Probe 必须通过 `runtime-core-v1`，Native Runtime 还必须通过 `runtime-general-v1 + governed-v1`。这用于证明 CapabilityDefinition、ProviderResolution、RunManifest、Workbench Event 和 Artifact/Usage 契约没有按主实现内部模型定制，不要求适配 DeerFlow 或其他参考项目。

Profile 与 Test ID 以 `contracts/conformance/` 下的机器可读 Suite 为准。Suite 自带内容摘要；测试结果必须绑定 Suite ID/Version/Digest/Profile、ProviderRevision、环境和不可变 Evidence。Runtime、Sandbox、Runtime Gateway、通用 Capability Provider 和 Artifact/Egress Execution Gateway 使用各自 Suite；README 中的测试名称或人工声明不能构成认证。
