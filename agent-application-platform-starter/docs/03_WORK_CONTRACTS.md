# Business 与 Agent Platform 契约

## 1. Conversation and WorkOrder

AgentConversation owns the durable Workspace and append-only Message sequence. Each executable user Turn creates one immutable WorkOrder. One-shot calls create an implicit Conversation in the same transaction.

业务后端使用 Sender-constrained Service Token 提交：

```http
POST /v1/work-orders
Idempotency-Key: ...
```

返回 202。

client_app_id 不出现在请求正文。

WorkOrder and ExecutionGrant both bind `conversation_id`、`turn_id`、`branch_id` and `input_message_id`.

## 2. Request Digest

ExecutionGrant 绑定完整 WorkOrder Request，唯一排除 `execution_grant`。

使用 RFC 8785 JCS 与固定跨语言 Test Vector。

## 3. Input Artifact

WorkOrder 只接受：

- 已有 Artifact ID/Version
- Ingest Reference
- 预注册 Connector Object

禁止任意下载 URL。

## 4. Delivery

WorkOrder 只引用：

- callback_registration_id
- delivery_target_id

禁止任意 Callback/Upload URL。

## 5. WorkSession

业务后端创建 Conversation-bound 一次性 Exchange Token，并附带当前 CommercialAuthorizationSnapshot。可选 `work_order_id` 只能进一步收窄权限。

Browser Exchange 后获得 HttpOnly Cookie。

每个可执行 follow-up 仍需要新的 ExecutionGrant；WorkSession 不能自行扩大会员权益或商业配额。

## 6. Usage

Agent Platform 只报告技术事实。

数量使用 Meter 注册的整数基础单位，例如：

- token
- millisecond
- byte
- count

同时标记：

- platform_metered
- provider_reported
- reconciled

## 7. Delivery Webhook

- 至少一次
- delivery_id/webhook_id 幂等
- mTLS 或 HTTP Message Signature
- Callback Registry
- Replay Window
- Retry/DLQ
