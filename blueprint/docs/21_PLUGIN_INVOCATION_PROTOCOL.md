# Plugin Invocation 协议

该协议仅供 `capability-provider-v1` 后面的兼容 Bridge 使用，不是新 Provider 的公共入口。Bridge 必须把已准入 Capability Invocation 的 Tenant、ClientApplication、WorkOrder、Attempt、Fencing、Deadline 和 Request Digest 写入兼容请求/短期 Token，并通过 `legacy-plugin-bridge-token-binding`；外部调用方不得直接取得 Plugin Token 或选择 `plugin_id`。

本协议只服务既有 Plugin 实现兼容，不是通用 Provider Port。新 Model、Tool、MCP、Skill、Renderer、Editor、Converter 和远程服务必须实现 `capability-provider-v1`；Adapter 在内部映射 `plugin_id`，稳定内核与 Capability Token 不依赖它。

## 统一语义

运行模式：

- service
- job
- sandbox_cli
- mcp
- remote_service

传输绑定详见 `30_PLUGIN_MODE_BINDINGS.md`。

## 调用尝试

每个消息必须携带：

- invocation_id
- invocation_attempt_id
- fencing_token

旧 Attempt 结果必须被平台拒绝。

## Token 授权

Plugin Invocation Token 内容：

- typ=`agent-plugin-invocation+jwt`
- `sub` 匹配已认证 Bridge Workload Identity
- audience 绑定 Plugin/Provider Revision
- 绑定 Tenant、ClientApplication、WorkOrder 和完整请求摘要
- 绑定 InvocationAttempt
- 绑定 Capability
- 绑定 Staging Session
- 绑定 approved permissions digest
- 同时绑定原始 Invocation Request Digest，以及当前 Invoke/Status/Cancel/Event 的 Operation、Contract ID、Digest Profile 和请求/规范化读描述符摘要
- 最大 TTL 300 秒；`invoke` 使用 `execution`，不得超过 Invocation Deadline、Artifact 读取或 Staging 有效期；Status/Cancel/Event 使用 `safety_control`，可以在执行窗口结束后完成取消/对账，但不继承已经失效的 Artifact 访问能力，也不能创建新副作用

服务模式同时使用 mTLS Workload Identity。

Invoke Token 不能用于 Status、Cancel 或 Event；Status 的 Path、Cancel Body、Event 的 Path/Attempt/Cursor 都必须进入各自操作摘要。兼容协议不因位于内部 Bridge 后面而放宽 Bearer Token 的防重放要求。

## 请求

- protocol version
- idempotency key
- Capability 精确版本/Profile
- deadline
- structured input
- 仅由 Bridge 从已授权 ArtifactGrant 派生的短期读取 URL
- 仅由 Bridge 从 ArtifactStagingGrant 派生的短期暂存 URL
- Trace Context

## 结果

- structured output
- StagedArtifact
- UsageObservation（由 Platform 归一化为 TechnicalUsageEntry）
- Provider Operation ID
- Attempt/Fencing

## Artifact 暂存区

Plugin 不创建正式 ArtifactVersion，也不返回带 Platform `entry_id/recorded_at` 的 TechnicalUsageEntry。

平台验证：

- Staging Session
- Invocation/Attempt
- Digest
- Media Type
- Size
- Malware
- Tenant
- Capability Artifact 契约

## 信任治理

Manifest 不声明 Trust。

Platform Registry 管理：

- Publisher
- Signature
- Package Digest
- Image Digest
- SBOM
- Provenance
- Vulnerability Scan
- Approved Permissions
- Trust Level

## 配置与凭据

Manifest 必须声明：

- 不可变 Configuration Schema
- credential requirements

ProviderInstance 使用配置 Digest。

Secret Broker 在 Invocation 时提供最小范围短期凭据。
