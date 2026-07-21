# Artifact 导入、交付与 Webhook

## 禁止任意 URL

WorkOrder 不接受任意：

- callback_url
- 输入下载 URL
- Business Storage 上传 URL

这些字段会产生 SSRF、数据泄漏和凭据外带风险。

## 输入 Artifact

支持：

- 已存在的 Agent ArtifactReference
- Agent Platform 导入 Session
- 预注册 Storage Connector Object

Ingest Session 是可恢复状态机，不是一次 upload-session URL。公共流程固定为 Create -> authorized Status -> Confirm -> Scan -> Platform Finalize：

- 指定 Media Type
- 大小限制
- 摘要
- 短期上传 URL
- 上传后扫描和确认

Create 请求绑定 Tenant、ClientApplication、PrincipalContext Digest、CommercialAuthorization、上传意图、Idempotency-Key 和请求摘要，不接受调用方提交的 Policy/Budget/Permissions。Platform 分配 `ingest_session_id` 后生成同 Scope 的 PolicyDecision、ExecutionBudget 与 EffectivePermissions，并在返回上传能力前持久绑定到 Session。Confirm 绑定上述 Session，按 Confirmation Digest 幂等；Scan 绑定 Scanner Revision/Profile/Suite、Evidence 和精确 Content Digest。Finalize Command 只能由 Platform 内部主体签发，并在一个事务中唯一创建 ArtifactVersion、推进 Session 和写 Outbox；调用方、Storage Connector 与 Scanner 都不能 Finalize。

Delivery 在终态仍必须明确携带 `usage_accounting`。存在已确认用量时嵌入非空 UsageReport；只有证明没有 Runtime/Capability/Sandbox/Gateway Attempt 且没有 TechnicalUsageEntry 时才能嵌入 NoUsageAttestation。缺失、Partial、Estimated 或仍在对账的用量保持 Delivery pending，绝不能当作零。

## Callback 注册

Business Application 预先注册 Callback：

- callback_registration_id
- Endpoint
- Audience
- 验证密钥
- 允许的 Event Type
- 超时
- 重试策略

WorkOrder 只引用 Registration ID。

## Webhook

Delivery Webhook 内容：

- delivery_id 幂等
- 时间戳
- 内容摘要
- HTTP Message Signature 或 mTLS
- Replay Window
- 至少一次发送
- 2XX 确认
- 指数退避
- DLQ

## Delivery Target

`business_managed` 和 `replicated` 使用预注册 Delivery Target：

- Agent 托管 Object Storage
- Business Storage Connector
- 企业私有 Storage

Target Credential 由 Secret Broker 临时授权，Plugin 不直接获得。

## SSRF 防护

所有注册 Endpoint 经过：

- Scheme Allowlist
- DNS/IP 解析校验
- 私网与元数据策略
- 重定向限制
- DNS Rebinding 防护
- 响应大小限制
- Egress Gateway
