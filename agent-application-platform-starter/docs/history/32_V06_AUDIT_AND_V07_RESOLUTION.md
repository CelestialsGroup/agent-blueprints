# v0.6 深度审查与 v0.7 修订报告

日期：2026-07-15  
审查结论：**v0.6 不应作为实施冻结基线；v0.7 可批准进入 Codex Phase 0。**

## 1. 审查方法

审查覆盖：

- 系统边界与数据所有权
- OAuth/JWT/ExecutionGrant
- Browser SSE/WebSocket Session
- OpenAPI 与 JSON Schema 可移植性
- Temporal 与 PostgreSQL 一致性
- Invocation/副作用
- Event Cursor/Event Data
- Capability/Plugin SPI
- Artifact Ingest/Edit/Delivery
- DeerFlow 执行治理
- Kubernetes 多节点和运维
- ADR、状态机和 Contract CI

检查方式：

- 文件级人工审查
- 标准 JSON Schema Validator
- 固定版本 Redocly CLI
- OpenAPI Bundle
- 正向/反向 Fixture
- 跨文件矛盾扫描
- Kubernetes Manifest 结构检查

## 2. v0.6 的阻塞问题

### P1：Schema 校验存在假阳性

v0.6 使用 URN `$id` 和文件相对 `$ref`，标准独立 Validator 无法解析；旧脚本通过自定义 `RefResolver` Store 掩盖问题。

**v0.7：**

- 绝对 `$id`
- 对外契约 Schema 自包含
- Capability/Scenario 使用 URI + Digest + Dialect
- 现代 `referencing.Registry`
- Portable Reference Scan
- 固定工具版本

### P1：Browser WorkSession 不安全/不可用

v0.6 返回可重用 Bearer Token，但原生 EventSource 无法设置 Authorization Header，URL/浏览器持久存储 Token 又不安全。

**v0.7：**

- 一次性 Exchange Token
- Workbench Origin HttpOnly Secure Cookie
- Cookie 写操作 CSRF 防护
- Headless SDK 单独 Bearer Profile
- Token Type 互斥验证
- Session Revision/Revocation

### P1：ExecutionGrant Digest 边界有绕过空间

v0.6 把 `metadata` 排除在摘要之外，但 `metadata.locale` 等字段可能影响执行。

**v0.7：**

- 摘要覆盖完整 Request，唯一排除 `execution_grant`
- RFC 8785 JCS/I-JSON 约束
- 跨语言 Test Vector 要求
- 动态 JWK/JWKS URL 禁止

### P1：Invocation Attempt/Fencing 不闭环

v0.6 Complete 逻辑要求 Fencing，但 Result/Error/Progress 没有 Attempt ID 与 Fencing Token。

**v0.7：**

- 所有 Invocation 消息携带 Attempt ID/Fencing
- Staging 绑定 Attempt
- 旧 Fencing 结果拒绝
- Mode Binding 明确定义

### P1：ExecutionGrant 无法真正限制 DeerFlow

若 DeerFlow 直接调用模型、MCP 和公网，Token/Sandbox/网络限制只是文档建议。

**v0.7：**

- Model Gateway
- Tool/MCP Gateway
- Artifact Gateway
- Sandbox Egress Gateway
- ExecutionBudget
- Governed Agent Runtime Conformance

### P1：Capability/Provider 不完全可复现

v0.6 Schema 引用是普通路径字符串，Run 只锁定可变 ProviderInstance。

**v0.7：**

- Immutable SchemaReference
- Namespace Owner/Lifecycle
- ProviderRevision
- Resolution 固化 Manifest/Image/Config/Permission/Conformance Digest
- RunManifest 增加预算、策略、定义和事件版本摘要

### P1：任意 URL 产生 SSRF 边界

v0.6 WorkOrder 允许 Callback URL 和外部文件引用。

**v0.7：**

- Artifact Ingest Session
- Storage Connector
- CallbackRegistration
- DeliveryTarget
- Signed Webhook
- Egress Gateway 与 DNS Rebinding 防护

### P1：Event Data 和留存未冻结

v0.6 只有 Envelope，`data` 没有注册 Schema；缺少 recorded_at、Cursor 过期和高频 Delta 策略。

**v0.7：**

- Event Type Registry
- data_version + Schema Digest
- occurred_at + recorded_at
- 410 Cursor Expired
- Token Delta 批量化

### P2：Temporal 版本治理过度简化

v0.6 笼统写“运行中的 Workflow 固定兼容 Worker”，没有区分 Pinned/Auto-Upgrade、Continue-as-New 和敏感 Payload。

**v0.7：**

- Worker Deployment + Build ID
- Pinned/Auto-Upgrade 按 Workflow 类型选择
- Replay/Patching
- Continue-as-New
- Payload Codec
- History Size/Retention

### P2：Plugin 分发信息不足

v0.6 缺少 Publisher、Config Schema、Credential Requirement、Package Provenance。

**v0.7：**全部补齐，并由 Registry 管理 Trust、Signature、SBOM 和 Scan。

## 3. v0.7 架构评分

| 维度 | v0.6 | v0.7 架构基线 | 说明 |
|---|---:|---:|---|
| 业务边界 | 8.5 | 9.5 | 数据事实源和接入边界明确 |
| 模块化 | 8.5 | 9.2 | 稳定内核与扩展点合理 |
| 灵活性 | 7.5 | 9.0 | Capability 与 Runtime Mode 可扩展 |
| 可替换性 | 7.0 | 9.0 | Schema Digest、Conformance、ProviderRevision |
| 安全设计 | 6.5 | 8.8 | Token 类型、Session、SSRF、Gateway |
| 一致性设计 | 7.5 | 9.0 | Grant/Idempotency/Invocation/Event 不变量 |
| 多节点设计 | 8.0 | 9.0 | 无状态、Runtime Gateway、Temporal、RBAC |
| 可实施性 | 7.5 | 8.8 | Phase 0 范围和 Port 明确 |
| 生产运行设计 | 7.0 | 8.5 | SLO、RPO/RTO、Backpressure、DR |
| 生产运行证据 | 0 | 0 | 尚无实现、压测、故障注入和恢复演练 |

## 4. 最终判断

### 可批准

v0.7 符合成熟平台架构常见原则：

- Bounded Context
- Contract First
- Stable Kernel + Controlled Plugins
- Durable Workflow
- Explicit Side-effect Semantics
- Immutable Artifact/Provider Revision
- Zero-trust Plugin Boundary
- Multi-tenant/Kubernetes First
- Observable and Replayable Execution

因此可以作为 Codex Phase 0 的冻结架构基线。

### 不能声称

不能因为文档和 Contract 通过校验，就声称系统已经：

- 高可用
- 无数据丢失
- 安全合规
- 可承载目标规模
- DeerFlow 预算不可绕过
- 灾难可恢复

这些必须通过代码、部署和演练证明。

## 5. Phase 0 后必须获得的证据

- Grant/Idempotency 并发测试
- 跨租户和 Object Authorization 负向测试
- WorkSession CSRF/Revocation 测试
- Event Sequence 高并发与热 WorkOrder 测试
- Invocation stale fencing/outcome_unknown 故障注入
- Temporal Replay/Worker Versioning
- DeerFlow Model/Tool/Egress 绕过测试
- Artifact Staging/恶意文件测试
- SSRF/DNS Rebinding/Webhook Replay 测试
- Pod/Node/Worker/Provider 故障恢复
- PostgreSQL/Temporal/Object Storage 恢复演练
- 容量和 Backpressure 测试

## 6. 参考规范

- OpenAPI Specification 3.1.1: https://spec.openapis.org/oas/v3.1.1.html
- JSON Schema 2020-12 Core: https://json-schema.org/draft/2020-12/json-schema-core
- JWT Best Current Practices (RFC 8725): https://www.rfc-editor.org/rfc/rfc8725
- OAuth JWT Access Token Profile (RFC 9068): https://www.rfc-editor.org/rfc/rfc9068
- OAuth Security Best Current Practice (RFC 9700): https://www.rfc-editor.org/rfc/rfc9700
- OAuth mTLS (RFC 8705): https://www.rfc-editor.org/rfc/rfc8705
- DPoP (RFC 9449): https://www.rfc-editor.org/rfc/rfc9449
- JSON Canonicalization Scheme (RFC 8785): https://www.rfc-editor.org/rfc/rfc8785
- HTTP Message Signatures (RFC 9421): https://www.rfc-editor.org/rfc/rfc9421
- Kubernetes Pod Lifecycle / NetworkPolicy / PDB official documentation
- Temporal Worker Versioning official documentation

## 7. 最终补齐的 Workbench 稳定契约

v0.7 还补充了以下在 v0.6 中缺失、但对“观察—接管—编辑—交付”必要的稳定接口：

- Pause / Resume WorkOrder
- Approval List / Decision
- Runtime Session（Terminal / Browser / Desktop）
- Preview Session
- Artifact Content Access
- Draft Save / Discard / Commit
- Artifact Ingest Session
- Delivery Webhook

这些接口均遵循 WorkSession Scope、Cookie CSRF、Tenant/Object Authorization 和短期访问语义。

## 8. 审批结果

```text
v0.6：Rejected as implementation baseline
v0.7：Approved for Codex Phase 0
Production Readiness：Not yet proven
```
