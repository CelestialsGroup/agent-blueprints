# v0.8 架构验收

## Contract Tooling

- [ ] 所有 Schema 有绝对 `$id`。
- [ ] 跨 Schema `$ref` 可在标准 Registry 中解析。
- [ ] SchemaReference Digest 与发布内容一致。
- [ ] 固定工具版本。
- [ ] 3 份 OpenAPI 0 error / 0 warning。
- [ ] OpenAPI Bundle 成功。

## Identity / Session

- [ ] Service Access Token 有严格 Profile、audience 和 sender constraint。
- [ ] client_app_id 只来自认证上下文。
- [ ] WorkSession 使用一次性 Exchange + HttpOnly Cookie。
- [ ] Cookie 写操作有 CSRF 防护。
- [ ] JWT typ/aud/claims 验证互斥。
- [ ] Delegated WorkSession 有显式 Scope、Policy 和 Audit。

## Grant

- [ ] Grant 单次消费，最大 TTL 300 秒。
- [ ] JCS Digest 覆盖除 execution_grant 外的完整请求。
- [ ] JWKS/Key 预注册，拒绝动态 Key URL。
- [ ] Grant、Idempotency、WorkOrder、Workspace、Outbox 同事务。

## Workflow / Invocation

- [ ] WorkOrder 使用稳定 Temporal Workflow ID。
- [ ] PostgreSQL/Temporal Reconciliation 定义完成。
- [ ] Worker Versioning Profile 明确。
- [ ] 每个 Invocation 消息带 Attempt ID 与 Fencing Token。
- [ ] outcome_unknown 不自动重试。
- [ ] 敏感和大 Payload 不进入 Temporal History。

## Execution Mediation

- [ ] DeerFlow 模型调用经过 Model Gateway。
- [ ] 外部 Tool/MCP 调用经过 Tool Gateway 和 Invocation Ledger。
- [ ] Sandbox 出站经过 Egress Gateway。
- [ ] Execution Budget 可在运行时强制执行。

## Event

- [ ] SSE 使用 work_sequence。
- [ ] Event 有 recorded_at 和 data_version。
- [ ] Event Type Registry 固化 data Schema。
- [ ] Cursor 过期返回 410。
- [ ] 高频 Token Delta 不逐条持久化。

## Capability / Plugin

- [ ] Capability Schema 使用 URI + Digest。
- [ ] Namespace Owner 和生命周期明确。
- [ ] ProviderResolution 固化不可变 ProviderRevision。
- [ ] Plugin 不自报 Trust。
- [ ] Plugin 有 Publisher、Config Schema、Credential Requirements 和 Provenance。
- [ ] 每种 Runtime Mode 有确定 Transport Binding。

## Artifact / Delivery

- [ ] ArtifactVersion 内容不可变。
- [ ] Plugin 输出只进入 Staging。
- [ ] 外部输入使用 Ingest/Connector，不接受任意 URL。
- [ ] Callback 和 Delivery Target 预注册。
- [ ] Webhook 有签名、重放窗口、幂等、重试和 DLQ。

## Kubernetes / Operations

- [ ] API 无状态，不依赖 Sticky Session。
- [ ] Sandbox Provisioner 使用最小 RBAC。
- [ ] NetworkPolicy 与 Egress Gateway 职责不混淆。
- [ ] PDB 不被视为故障恢复方案。
- [ ] RPO/RTO、Backpressure、Fairness、Retention、DR 已冻结。

## Phase 0 完成证据

- [ ] 架构依赖测试。
- [ ] 跨租户负向测试。
- [ ] 幂等/Grant 并发测试。
- [ ] Event Sequence 并发测试。
- [ ] Invocation Fencing 测试。
- [ ] Artifact Commit 冲突测试。
- [ ] Worker Replay/Versioning 测试骨架。

## Sandbox Provider

- [ ] DeerFlow Sandbox 和 sandbox-runtime 使用同一 Provider Contract。
- [ ] SandboxSpec 不包含具体后端专用字段。
- [ ] Capability Negotiation 无静默降级。
- [ ] Create/Exec/Snapshot/Terminate 支持幂等、Attempt 和 Fencing。
- [ ] Desired/Observed State 与 Generation 已定义。
- [ ] Runtime endpoint 不直接暴露给浏览器。
- [ ] Workspace 输出只进入 Artifact Staging。
- [ ] Network 默认拒绝并经过 Egress Gateway。
- [ ] Snapshot 明确 Level、Portable 和 Compatibility。
- [ ] ProviderRevision 通过 Conformance。
- [ ] RunManifest 锁定 Sandbox Revision 和 Spec Digest。
