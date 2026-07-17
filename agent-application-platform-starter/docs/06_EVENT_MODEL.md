# Canonical Event v2

## 1. 存储模型

```text
PostgreSQL Current State
+ Append-only Canonical Event
+ Projection
```

不采用全系统 Event Sourcing。

## 2. WorkOrder Cursor

每个 WorkOrder 维护 `next_work_sequence`。

所有 WorkOrder 相关事件都携带完整 `work_order_id + turn_id + branch_id + input_message_id + work_sequence` 绑定，并共享严格递增 `work_sequence`，用于：

- SSE
- Timeline
- 回放
- 断点续传

## 3. Aggregate Cursor

事件包含：

```text
aggregate.type
aggregate.id
aggregate.sequence
```

用于 WorkflowRun、AgentRun、Invocation、Artifact 等局部顺序。

ConversationMessage 另有严格递增 `message_sequence`；RuntimeRecordingChunk 以 channel-local sequence 存储并用 `work_sequence` 与 Timeline 对齐。Canonical Aggregate 明确支持 conversation、conversation_message、sandbox、sandbox_operation、runtime_session 和 runtime_recording。

文档中统一使用 Schema 字段名 `aggregate.sequence`，不再使用不存在的平铺字段。

## 4. 时间

- occurred_at：来源时间
- recorded_at：平台事务持久化时间

WorkOrder 流排序只使用 work_sequence。Conversation 创建、archive/delete 等非执行事件不伪造 WorkOrder 上下文，按 `aggregate.sequence` 排序。

## 5. Event Type Registry

`data` 必须符合 EventTypeRegistry 中 type + data_version 对应的不可变 Schema。

核心 Projection 不消费未注册 Plugin 私有事件。

## 6. 写入事务

1. 按 `(provider_instance_id, source_stream_id, source_cursor)` 去重。
2. 对 WorkOrder 事件原子分配 work_sequence；Conversation-only 事件省略完整 Work 上下文组。
3. 原子分配 aggregate sequence。
4. 写 Event。
5. 更新必要 Projection。
6. 写 Outbox。
7. Commit。

## 7. SSE

```http
GET /v1/work-orders/{id}/events?after_work_sequence=152
```

支持 Last-Event-ID。

- heartbeat 至少每 15 秒
- `Cache-Control: no-store`
- Token 到期/Session 撤销时关闭
- Cursor 过期返回 410
- Redis 只用于唤醒，不是事实源

## 8. 高频 Delta

模型 Token 不逐 Token 持久化。

Delta 进行批量合并，最终 Completed Event 或 Artifact 必须可独立重建结果。

Terminal/Browser/Desktop 录制字节进入加密 Artifact chunks，CanonicalEvent 只保存 recording/chunk 引用，不保存视频或完整终端流。
