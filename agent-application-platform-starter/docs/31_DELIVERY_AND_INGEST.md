# Artifact Ingest、Delivery 与 Webhook

## 1. 禁止任意 URL

WorkOrder 不接受任意：

- callback_url
- input download URL
- business storage upload URL

这些字段会产生 SSRF、数据泄漏和凭据外带风险。

## 2. Input Artifact

支持：

- 已存在的 Agent ArtifactReference
- Agent Platform Ingest Session
- 预注册 Storage Connector Object

Ingest Session 使用：

- 指定 media type
- size limit
- digest
- 短期上传 URL
- 上传后扫描和确认

## 3. Callback Registration

Business Application 预先注册 Callback：

- callback_registration_id
- endpoint
- audience
- verification key
- allowed event types
- timeout
- retry policy

WorkOrder 只引用 Registration ID。

## 4. Webhook

Delivery Webhook：

- delivery_id 幂等
- timestamp
- content digest
- HTTP Message Signature 或 mTLS
- replay window
- 至少一次发送
- 2XX 确认
- 指数退避
- DLQ

## 5. Delivery Target

`business_managed` 和 `replicated` 使用预注册 Delivery Target：

- Agent-managed Object Storage
- Business Storage Connector
- Enterprise private storage

Target Credential 由 Secret Broker 临时授权，Plugin 不直接获得。

## 6. SSRF 防护

所有注册 Endpoint 经过：

- Scheme Allowlist
- DNS/IP 解析校验
- 私网与元数据策略
- 重定向限制
- DNS Rebinding 防护
- Response Size Limit
- Egress Gateway
