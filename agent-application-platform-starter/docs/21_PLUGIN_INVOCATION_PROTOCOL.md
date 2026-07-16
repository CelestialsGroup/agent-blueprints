# Plugin Invocation Protocol

## 1. 统一语义

运行模式：

- service
- job
- sandbox_cli
- mcp
- remote_service

传输绑定详见 `30_PLUGIN_MODE_BINDINGS.md`。

## 2. Attempt

每个消息必须携带：

- invocation_id
- invocation_attempt_id
- fencing_token

旧 Attempt 结果必须被平台拒绝。

## 3. Token

Plugin Invocation Token：

- typ=`agent-plugin-invocation+jwt`
- audience 绑定 Plugin/Provider Revision
- 绑定 InvocationAttempt
- 绑定 Capability
- 绑定 Staging Session
- 绑定 approved permissions digest
- 最大 TTL 不超过 Invocation Deadline

服务模式同时使用 mTLS Workload Identity。

## 4. Request

- protocol version
- idempotency key
- capability exact version/profile
- deadline
- structured input
- short-lived Artifact Read Grants
- Artifact Staging Grant
- Trace Context

## 5. Result

- structured output
- StagedArtifact
- Technical Usage
- Provider Operation ID
- Attempt/Fencing

## 6. Artifact Staging

Plugin 不创建正式 ArtifactVersion。

平台验证：

- Staging Session
- Invocation/Attempt
- Digest
- Media Type
- Size
- Malware
- Tenant
- Capability Artifact Contract

## 7. Trust

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

## 8. 配置与凭据

Manifest 必须声明：

- immutable configuration schema
- credential requirements

ProviderInstance 使用配置 Digest。

Secret Broker 在 Invocation 时提供最小范围短期凭据。
