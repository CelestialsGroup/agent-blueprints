# 规范事件模型 v2

## 存储模型

```text
PostgreSQL 当前状态
+ 仅追加 CanonicalEvent
+ Projection
```

不采用全系统 Event Sourcing。

## WorkOrder 游标

每个 WorkOrder 维护 `next_work_sequence`。

所有 WorkOrder 相关事件都携带完整 `work_order_id + turn_id + branch_id + input_message_id + work_sequence` 绑定，并共享严格递增 `work_sequence`，用于：

- SSE
- Timeline
- 回放
- 断点续传

## 聚合游标

事件包含：

```text
aggregate.type
aggregate.id
aggregate.sequence
```

用于 WorkflowRun、AgentRun、Invocation、Artifact 等局部顺序。

ConversationMessage 另有严格递增 `message_sequence`；WorkspaceRevision 按 Branch `revision_number` 递增并通过 Branch CAS 推进；RuntimeRecordingChunk 以 channel-local sequence 存储并用 `work_sequence` 与 Timeline 对齐。Canonical Aggregate 明确支持 conversation、conversation_branch、conversation_message、workspace_revision、sandbox、sandbox_operation、runtime_session 和 runtime_recording。

文档中统一使用 Schema 字段名 `aggregate.sequence`，不再使用不存在的平铺字段。

## 时间

- occurred_at：来源时间
- recorded_at：平台事务持久化时间

WorkOrder 流排序只使用 `work_sequence`。Conversation 创建、归档/删除等非执行 Event 不伪造 WorkOrder 上下文，按 `aggregate.sequence` 排序。

## Event Type 注册表

`data` 必须符合 EventTypeRegistry 中 type + data_version 对应的不可变 Schema。

核心 Projection 不消费未注册 Plugin 私有事件。

AgentRuntimeProvider 的核心事件使用 `contracts/event-types/agent-runtime-core-v1.json`。Registry 自带内容摘要，RunManifest 固化 ID/Version/Digest。Chat、Plan、Tool/Approval、Artifact、Background Task、Usage 和 Runtime 终态均绑定 `agent-runtime-event-data-v1` 的闭合 Payload；新增核心类型必须发布新的 Registry Revision，不能向任意 `data` 偷渡字段。

## 写入事务

1. 按 `(tenant_id, producer_id, source_stream_id, source_event_id)` 写 Inbox 唯一键并校验 Dedupe Key；Provider 来源额外绑定不可变 `provider_revision_id`，Cursor 只用于恢复读取，不作为唯一事件身份。
2. 对 WorkOrder Event 原子分配 `work_sequence`；仅属于 Conversation 的 Event 省略完整 Work 上下文组。
3. 原子分配 Aggregate Sequence。
4. 写 Event。
5. 更新必要 Projection。
6. 写 Outbox。
7. 提交事务。

CanonicalEvent Metadata 是闭合对象，只允许标准 Trace/Correlation/Causation 和少量平台注册字段。Provider 私有 Metadata 与 Trace 原始载荷留在只读 Evidence，不得进入核心 Projection。

## SSE

```http
GET /v1/work-orders/{id}/events?after_work_sequence=152
```

支持 Last-Event-ID。

- heartbeat 至少每 15 秒
- `Cache-Control: no-store`
- Token 到期/Session 撤销时关闭
- Cursor 过期返回 410
- Redis 只用于唤醒，不是事实源

## 高频增量事件

模型 Token 不逐 Token 持久化。

Delta 进行批量合并，最终 Completed Event 或 Artifact 必须可独立重建结果。

Prompt Queue 和 Interjection 不新增本地 Session 事实源：客户端 Control Input 经授权后由平台分配内部 Input/Message ID，并通过连续、仅追加且带请求摘要、引用已授权 `control_request_id` 的 `append_input` 或 `interrupt` Runtime Command 传递。Sub-agent、后台命令、Monitor 和 Scheduler 统一投影为 `runtime.task.*`；Sub-agent Task 显式绑定 Child AgentRun，PID 与本地队列仍是 Runtime 私有状态。`runtime.usage.reported` 只传递可去重的 UsageObservation Batch，Platform 校验并创建 TechnicalUsageEntry 后再形成跨来源 UsageReport。

Terminal/Browser/Desktop 录制字节进入加密 Artifact chunks，CanonicalEvent 只保存 recording/chunk 引用，不保存视频或完整终端流。
