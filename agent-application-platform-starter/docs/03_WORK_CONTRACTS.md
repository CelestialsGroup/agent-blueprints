# Business 与 Agent Platform 契约

## Conversation 与 WorkOrder

AgentConversation 拥有持久 Workspace 和仅追加的 Message 序列。每个可执行用户 Turn 创建一个不可变 WorkOrder。一次性调用在同一事务中创建隐式 Conversation。

业务后端使用 Sender-constrained Service Token 提交：

```http
POST /v1/work-orders
Idempotency-Key: ...
```

返回 202。

client_app_id 不出现在请求正文。

外部 WorkOrder/ConversationTurn 与 ExecutionGrant 都绑定 `conversation_id`、`turn_id`、`branch_id` 和 `client_message_id`。平台在同一事务中分配内部 `input_message_id`，Business 不签发平台内部 Message ID。

## 请求摘要

ExecutionGrant 显式声明 `request_contract_id`，其 `request_digest` 绑定该精确 WorkOrderRequest、ConversationTurnRequest 或 WorkOrderControlRequest，唯一排除 `execution_grant`。三种请求使用相同 Digest Profile，但不能互换 Contract ID。前两种创建新 WorkOrder，Control Request 只操作已有 WorkOrder。

使用 RFC 8785 JCS 与固定跨语言 Test Vector。

## 输入 Artifact

WorkOrder 只接受：

- 已有 Artifact ID/Version
- Ingest Reference
- 预注册 Connector Object

禁止任意下载 URL。

## 交付

WorkOrder 只引用：

- callback_registration_id
- delivery_target_id

禁止任意 Callback/Upload URL。

## WorkSession

业务后端创建 Conversation-bound 一次性 Exchange Token，并附带当前 CommercialAuthorizationSnapshot。可选 `work_order_id` 只能进一步收窄权限。

Browser Exchange 后获得 HttpOnly Cookie。

每个可执行 follow-up 仍需要新的 ExecutionGrant；WorkSession 不能自行扩大会员权益或商业配额。

## 用量

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

## Delivery Webhook

- 至少一次
- delivery_id/webhook_id 幂等
- mTLS 或 HTTP Message Signature
- Callback Registry
- Replay Window
- Retry/DLQ
