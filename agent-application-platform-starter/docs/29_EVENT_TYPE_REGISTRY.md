# Event Type 注册表

## 1. 目标

仅统一 CanonicalEvent Envelope 不足以保证消费者可安全解析 `data`。

每个核心 Event Type 必须注册：

- type
- data_version
- 不可变 `data_schema` URI + 摘要
- 数据分类
- 保留类别
- Projection Consumer

## 2. 命名

核心事件：

```text
work_order.*
conversation.*
message.*
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

Plugin 私有 Event 必须带发布者 Namespace，且不能直接驱动核心 Projection。

## 3. 时间

事件同时保存：

- occurred_at：来源发生时间
- recorded_at：平台持久化时间

WorkOrder Timeline 使用 `work_sequence` 排序，不使用 `occurred_at` 排序。

## 4. 高频事件

禁止将每个模型 Token 作为独立持久化 Event。

Delta 必须按以下任一策略合并：

- 时间窗口
- 字节大小
- 语义消息块

最终的 Message Completed Event 必须持久化完整可重建结果或 Artifact Reference。

## 5. 留存

当 SSE Cursor 早于最早保留序列时返回 410，并提供：

- earliest_available
- latest_available
- Snapshot/Timeline API 指引

## 6. 内容安全

Event 默认不保存：

- Secret
- 长期凭据
- 原始 Authorization Header
- 完整大文件
- 未脱敏高敏内容

用户内容应通过外部引用、加密 Payload 或受控保留策略保存。
