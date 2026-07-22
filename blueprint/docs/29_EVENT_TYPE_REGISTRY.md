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
artifact.operation.*
artifact.ingest.*
approval.*
delivery.*
usage.*
compatibility.*
secret.grant.*
credential.*
sandbox.*
runtime_session.*
runtime_recording.*
```

Provider 私有 Event 必须带发布者 Namespace，且不能直接驱动核心 Projection。

平台领域事件注册表位于 Contract 资源 `contracts/event-types/platform-core-v1.json`，其闭合 Payload 位于 `platform-core-event-data:v1`，覆盖 Conversation/Branch Create-Fork/Message、WorkOrder/Control/SystemSafetyControl、WorkflowRun/RootBinding、AgentRun Admission/State/ControlFanout、Grant、Approval、Invocation、Artifact/ArtifactOperation/ArtifactIngest、Usage/NoUsage、CompatibilityDecision、SecretGrant/Credential Audit、Workspace、RuntimeSession/Recording 和 Delivery。ArtifactOperation/Ingest 事件绑定精确 ExecutionScope 且不伪造 Conversation/Work 字段；SecretGrant 事件携带其 Grant Scope；CompatibilityDecision 不拥有执行 Scope。Agent Runtime 标准化事件注册表位于 Contract 资源 `contracts/event-types/agent-runtime-core-v1.json`，只表达 Provider 的 Message/Plan/Task/Tool/Checkpoint/Run 流以及类型化 Child Spawn Request。Provider Event 只能提出 Spawn 需求，不能自行产生平台 AdmissionDecision 或 Child AgentRun。两类 Registry 不能混成 Provider 私有 Registry。Registry 本身拥有 ID/Version/Digest；RunManifest 固化 Runtime Registry，Platform 领域 Event 固化 Platform Registry，平台接受的标准 Runtime Event 以 Provider 来源身份和同一 Runtime Registry Revision 进入 CanonicalEvent。CanonicalEvent 必须按 Producer 所有权选择其中一个 Registry，并校验精确 Digest、`type + data_version` 与 Payload Schema；任意 Provider 私有 Registry 均 fail-closed。其中 URI 可以指向 Schema `$defs`。Data Schema 使用 `rfc8785-schema-closure-v1`，对根 Schema 与按绝对 `$id` 排序的传递外部依赖一起执行 JCS + SHA-256；`type + data_version` 在一个 Registry Revision 中唯一。

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
