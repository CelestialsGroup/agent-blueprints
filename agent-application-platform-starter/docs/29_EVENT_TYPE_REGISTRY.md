# Event Type 注册表

## 目标

仅统一 CanonicalEvent Envelope 不足以保证消费者可安全解析 `data`。

每个核心 Event Type 必须注册：

- type
- data_version
- 不可变 `data_schema` URI + 摘要
- 数据分类
- 保留类别
- Projection Consumer

## 命名

核心事件：

```text
work_order.*
conversation.*
message.*
workspace.*
workflow.*
agent.*
invocation.*
artifact.*
approval.*
delivery.*
usage.*
sandbox.*
runtime_session.*
runtime_recording.*
```

Provider 私有 Event 必须带发布者 Namespace，且不能直接驱动核心 Projection。

平台领域事件注册表位于 `contracts/event-types/platform-core-v1.json`，其闭合 Payload 位于 `platform-core-event-data:v1`，至少覆盖 Conversation/Message、WorkOrder/Control、WorkflowRun/AgentRun、Grant、Approval、Invocation、Artifact、Usage、Workspace、RuntimeSession/Recording 和 Delivery。Agent Runtime 标准化事件注册表位于 `contracts/event-types/agent-runtime-core-v1.json`，只表达 Adapter 的 Message/Plan/Task/Tool/Checkpoint/Run 流。二者不能混成 Provider 私有 Registry。Registry 本身拥有 ID/Version/Digest；RunManifest 固化 Runtime Registry，Platform Event Ingest 固化对应 Platform Registry Revision。其中 URI 可以指向 Schema `$defs`。Data Schema 使用 `rfc8785-schema-closure-v1`，对根 Schema 与按绝对 `$id` 排序的传递外部依赖一起执行 JCS + SHA-256，避免只哈希根文件而漏掉 `$ref` 变化；`type + data_version` 在一个 Registry Revision 中唯一。

## 时间

事件同时保存：

- occurred_at：来源发生时间
- recorded_at：平台持久化时间

WorkOrder Timeline 使用 `work_sequence` 排序，不使用 `occurred_at` 排序。

## 高频事件

禁止将每个模型 Token 作为独立持久化 Event。

Delta 必须按以下任一策略合并：

- 时间窗口
- 字节大小
- 语义消息块

最终的 Message Completed Event 必须持久化完整可重建结果或 Artifact Reference。

Runtime 的 `message.delta` 可以短期传输或批量合并；`message.completed`、`plan.updated`、`task.completed`、`usage.reported` 和 Run 终态必须有持久、可重建的引用。Headless/Workbench/IDE Adapter 只能投影同一核心流，不创建竞争事实源。

## 留存

当 SSE Cursor 早于最早保留序列时返回 410，并提供：

- earliest_available
- latest_available
- Snapshot/Timeline API 指引

## 内容安全

Event 默认不保存：

- Secret
- 长期凭据
- 原始 Authorization Header
- 完整大文件
- 未脱敏高敏内容

用户内容应通过外部引用、加密 Payload 或受控保留策略保存。
