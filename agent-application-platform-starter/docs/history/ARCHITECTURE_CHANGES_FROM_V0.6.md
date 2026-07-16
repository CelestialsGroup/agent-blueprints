# v0.6 到 v0.7 的结构性修订

- 修复 JSON Schema URN `$id` 与相对 `$ref` 导致的不可移植校验。
- 使用固定版本、现代 Registry 和 OpenAPI Bundle Gate。
- Browser WorkSession 改为一次性 Exchange + HttpOnly Cookie。
- 增加 WorkSession/JWT 类型隔离、CSRF 和撤销语义。
- ExecutionGrant Digest 覆盖完整 Request（除 execution_grant）。
- Invocation 所有消息增加 Attempt ID 与 Fencing Token。
- 增加 Model Gateway、Tool Gateway、Egress Gateway 和 ExecutionBudget。
- Capability Schema 使用 URI + Digest，增加 Namespace/Lifecycle。
- Run 从 ProviderInstance 改为锁定 Immutable ProviderRevision。
- Plugin 增加 Publisher、Config Schema、Credential Requirement 和 Provenance。
- 增加 Event Type Registry、recorded_at、Cursor 410 和 Delta batching。
- 移除任意 Input/Callback/Delivery URL，改为 Ingest/Connector/Registry。
- 增加 Delivery Webhook OpenAPI 与签名语义。
- 完善 Temporal Worker Versioning、Payload、History 和 Reconciliation。
- 增加数据唯一约束、RLS、Sandbox Provisioner RBAC 和运维验收。
