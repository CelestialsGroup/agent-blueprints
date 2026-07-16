# AGENTS.md

本文件是 Codex 和其他编码 Agent 的最高优先级约束。

## 1. 当前阶段

只执行 `prompts/CODEX_PHASE0_BOOTSTRAP.md`，不得自行进入 Phase 1。

实施前必须运行：

```bash
python3 -m pip install -r requirements-contracts.txt
npm ci
./scripts/lint_contracts.sh
```

任何契约、Bundle 或一致性检查失败，必须先修复。

## 2. 系统边界

Business Application 是以下数据的唯一事实源：

- User / Login
- Membership / Product
- Order / Payment / Refund
- Commercial Entitlement / Quota / Price

Agent Platform 是以下数据的唯一事实源：

- ClientApplication / InternalTenant
- WorkOrder / Workspace
- GrantConsumption / Idempotency
- WorkflowRun / AgentRun / Invocation
- CanonicalEvent / EventTypeRegistry
- Artifact / ArtifactVersion / ArtifactStaging
- TechnicalUsage / Delivery
- ProviderRevision / Resolution
- SandboxRegistry / SandboxOperation / SandboxLease

严禁跨数据库查询和直接操作对方内部对象。

## 3. 认证与授权

- Service API 使用 OAuth2 Client Credentials。
- 生产 Token 遵循 RFC 9068 Profile 或等价严格 Profile，并使用 audience restriction。
- 推荐 mTLS 或 DPoP sender constraint。
- `client_app_id` 只来自认证上下文。
- Browser Workbench 使用一次性 Exchange + HttpOnly WorkSession Cookie。
- 不把长期 Bearer Token 放入 URL、localStorage、sessionStorage 或 WebSocket Query。
- 每次资源访问校验 Token Type、Scope、Tenant、WorkOrder Binding、Ownership 和 Session Revision。

不同 JWT 必须使用互斥 `typ`、audience、Claims 和 Key Namespace：

- `at+jwt`
- `agent-execution-grant+jwt`
- `agent-work-session+jwt`
- `agent-plugin-invocation+jwt`

## 4. ExecutionGrant

- Compact JWS，算法白名单 EdDSA / ES256。
- 单次消费，最大 TTL 300 秒。
- 不信任 Token Header 中的动态 JWK/JWKS URL。
- Request Digest 使用 RFC 8785 JCS，覆盖完整 WorkOrder Request，唯一排除 `execution_grant`。
- GrantConsumption、IdempotencyRecord、WorkOrder、Workspace 和 Start Outbox 同事务。

## 5. Work、Workflow 与 Event

- PostgreSQL 保存对外当前状态。
- Temporal 保存 Durable Execution History。
- WorkOrder Workflow 使用稳定 Workflow ID。
- 对外状态变化由幂等 Domain Activity 写 PostgreSQL、Event 和 Outbox。
- SSE 使用 WorkOrder 级 `work_sequence`，不得使用 AgentRun 局部序列。
- Event 同时包含 `aggregate.sequence`、`occurred_at` 和 `recorded_at`。
- Event `data` 必须由 Event Type Registry 的不可变 Schema 约束。
- 不逐 Token 持久化模型 Delta。

## 6. 外部副作用与 Invocation

所有 Agent Runtime、Model、Tool、Plugin 和外部系统调用必须通过 Invocation Ledger。

每个传输消息必须带：

- invocation_id
- invocation_attempt_id
- fencing_token

`outcome_unknown` 禁止盲目重试，必须 Reconcile。

旧 Fencing Token 的结果不得覆盖新 Attempt。

## 7. 执行治理

平台管理的 SaaS Runtime 必须经过：

- Model Gateway
- Tool / MCP Gateway
- Artifact Gateway
- Sandbox Egress Gateway

DeerFlow 或其他 Agent Runtime 不得绕过这些 Gateway 直接使用平台长期模型凭据或任意公网。

## 8. Capability 与 Provider

CapabilityDefinition 必须定义：

- Owner Namespace
- Immutable Schema URI + Digest
- Request / Result / Error
- Side Effect / Idempotency
- Cancel / Progress / Status Query / Timeout
- Artifact Contract
- Lifecycle
- Conformance Suite

Plugin 只声明 `implements`。

Run 锁定不可变 ProviderRevision，而不是可变 ProviderInstance。

ProviderRevision 至少固定：

- Plugin Version
- Manifest / Package / Image Digest
- Configuration Digest
- Approved Permission Digest
- Conformance Report Digest

## 9. Plugin

- Plugin 不可自行声明 Trust。
- Plugin 不可访问平台数据库。
- Plugin 只能写 Artifact Staging。
- Plugin Manifest 必须声明 Publisher、Configuration Schema、Credential Requirements 和 Provenance。
- Runtime Mode 仅允许 `service`、`job`、`sandbox_cli`、`mcp`、`remote_service`。
- 每种 Mode 必须遵守 `docs/30_PLUGIN_MODE_BINDINGS.md`。

## 10. Artifact 与 Delivery

- ArtifactVersion 内容不可变。
- 外部输入使用 Ingest Session、已有 Artifact 或预注册 Connector。
- WorkOrder 禁止任意 Input URL、Callback URL 和 Delivery Upload URL。
- Callback 和 Delivery Target 必须预注册。
- Webhook 使用 mTLS 或 HTTP Message Signature，并按 delivery_id/webhook_id 幂等。

## 11. Kubernetes

- Agent API 无状态，不依赖 Sticky Session。
- Redis 不是 Event 或 Session 权威存储。
- Sandbox 生命周期独立。
- 只有专用 Sandbox Provisioner 拥有最小 Kubernetes RBAC。
- Sandbox/Plugin 任意出站经 Egress Gateway。
- Migration 使用独立 Job。
- Kubernetes RollingUpdate 不替代 Temporal Worker Versioning。
- Provider 下线先进入 draining。

## 12. Contract First

Source of Truth：

- OpenAPI 3.1.1
- JSON Schema 2020-12
- Transition Tables
- ADR

必须满足：

- Redocly 0 error / 0 warning
- Schema 使用绝对 `$id`
- 跨 Schema `$ref` 可移植
- SchemaReference 带 URI、Digest、Dialect
- 正向和反向 Fixtures
- OpenAPI Bundle 成功
- 不使用 `@latest` 或未固定工具版本

## 13. 技术基线

除非先创建 ADR，不得改变：

- Agent API / Worker：Go
- Web：Next.js / React
- Workflow：Temporal
- Current State：PostgreSQL
- Artifact Blob：S3-compatible
- Cache/Presence/Wakeup：Redis
- DeerFlow：独立 Python Runtime Service

## 14. Sandbox Provider Contract

- SandboxRegistry、Lease、Operation、RuntimeSession 和 Usage 属于稳定内核。
- DeerFlow Built-in Sandbox 与 `sandbox-runtime` 都必须通过 SandboxProvider Port 接入。
- Agent Platform 不得依赖 DeerFlow、Kubernetes、CRI、containerd、VM 或 Apple Container 专用字段。
- SandboxSpec 只能由 Agent Platform 根据 ExecutionBudget、Policy 和 Capability 生成。
- Provider 必须支持 Capability Negotiation，不支持时明确拒绝，禁止静默降级。
- 所有修改操作必须携带 operation_id、attempt_id、fencing_token 和 idempotency_key。
- Provider 只返回内部 Runtime Endpoint，浏览器连接必须经过 Runtime Gateway。
- Workspace 固定语义为 `/inputs`、`/workspace`、`/outputs`、`/tmp`。
- Sandbox 输出只能进入 Artifact Staging。
- 默认网络 none/restricted，任意出站必须经过 Egress Gateway。
- ProviderRevision 必须通过 Sandbox Conformance Profile。
- RunManifest 必须锁定 Sandbox ProviderRevision、Runtime Profile、Spec Digest 和 Conformance Report Digest。
- `sandbox-runtime` 只有在替代 Kubernetes Node Runtime 时才需要实现 CRI；普通 Provider 不需要。
