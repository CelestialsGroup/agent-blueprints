# Plugin Invocation 协议

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
- audience 绑定 Plugin/Provider Revision
- 绑定 InvocationAttempt
- 绑定 Capability
- 绑定 Staging Session
- 绑定 approved permissions digest
- 最大 TTL 不超过 Invocation Deadline

服务模式同时使用 mTLS Workload Identity。

## 请求

- protocol version
- idempotency key
- Capability 精确版本/Profile
- deadline
- structured input
- 短期 Artifact 读取 Grant
- Artifact 暂存 Grant
- Trace Context

## 结果

- structured output
- StagedArtifact
- Technical Usage
- Provider Operation ID
- Attempt/Fencing

## Artifact 暂存区

Plugin 不创建正式 ArtifactVersion。

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
