# Artifact 导入、交付与 Webhook

## 1. 禁止任意 URL

WorkOrder 不接受任意：

- callback_url
- 输入下载 URL
- Business Storage 上传 URL

这些字段会产生 SSRF、数据泄漏和凭据外带风险。

## 2. 输入 Artifact

支持：

- 已存在的 Agent ArtifactReference
- Agent Platform 导入 Session
- 预注册 Storage Connector Object

Ingest Session 使用：

- 指定 Media Type
- 大小限制
- 摘要
- 短期上传 URL
- 上传后扫描和确认

## 3. Callback 注册

Business Application 预先注册 Callback：

- callback_registration_id
- Endpoint
- Audience
- 验证密钥
- 允许的 Event Type
- 超时
- 重试策略

WorkOrder 只引用 Registration ID。

## 4. Webhook

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

## 5. Delivery Target

`business_managed` 和 `replicated` 使用预注册 Delivery Target：

- Agent 托管 Object Storage
- Business Storage Connector
- 企业私有 Storage

Target Credential 由 Secret Broker 临时授权，Plugin 不直接获得。

## 6. SSRF 防护

所有注册 Endpoint 经过：

- Scheme Allowlist
- DNS/IP 解析校验
- 私网与元数据策略
- 重定向限制
- DNS Rebinding 防护
- 响应大小限制
- Egress Gateway
