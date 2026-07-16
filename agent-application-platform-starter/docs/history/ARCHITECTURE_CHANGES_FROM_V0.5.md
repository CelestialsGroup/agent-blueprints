# v0.5 到 v0.6

v0.6 将架构从“概念完整”提升为“Contract-complete”。

主要修正：

- Service OAuth 与 WorkSession 双认证模型
- client_app_id 只来自认证上下文
- ExecutionGrant 单次消费和请求摘要绑定
- WorkOrder 级 work_sequence
- CanonicalEvent v2 Aggregate 模型
- Invocation Ledger 与 outcome_unknown
- CapabilityDefinition 与 Conformance
- Plugin Manifest v2 严格 oneOf
- Plugin trust 移入 Platform Registry
- Plugin Invocation Protocol
- Artifact Staging
- 完整 Artifact/Edit/Conversion Schema
- OpenAPI security、operationId、4XX、5XX
- 正式状态转换表
- RPO/RTO、背压、Worker Versioning、数据保留
- ADR 标准化
