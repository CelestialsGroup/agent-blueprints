# Runtime 录制与回放

## 职责分离

RuntimeSession 是短期实时连接。RuntimeRecording 是 Platform 拥有的不可变回放资源。Sandbox Snapshot 捕获的是状态，不是录制。

Runtime Gateway 已经中介 Terminal、Browser 和 Desktop 流量，因此由它录制已授权通道。Sandbox Provider 提供内部流端点，但不决定用户同意、保留策略或回放授权。

生命周期遵循 `contracts/state-machines/runtime-recording-v1.json`；只有完整不可变 Manifest 提交后才能进入 `ready`，Finalize 失败必须明确保持失败状态。

## 数据模型

```text
RuntimeRecording
 -> channels[]
 -> RuntimeRecordingChunk[]
    -> 不可变 ArtifactVersion
 -> RuntimeRecordingManifest
```

支持 Terminal、Browser、Desktop 和文件增量通道。每个 Chunk 都有通道内序列、墙上时间范围和 WorkOrder `work_sequence` 范围。回放以 `work_sequence` 同步；时间戳仅作为展示元数据。

## 格式

- Terminal：兼容 asciicast，或使用带 UTF-8/脱敏 Profile 的其他已注册媒体类型。
- Browser/Desktop：分段 WebM/MP4，或已注册的事件/截图格式。
- 文件变更：按摘要寻址的增量，或 ArtifactVersion 引用。

大块字节数据不得进入 PostgreSQL、Temporal History 或 CanonicalEvent。Event 只引用 Recording/Chunk Artifact。

处于 `ready` 状态的 `RuntimeRecording.manifest_digest` 与根级 `RuntimeRecordingManifest.manifest_digest` 是两个分离的摘要槽，保存相同值。计算时先移除这两个槽，再使用 RFC 8785 JCS + SHA-256；同时排除二者可以避免循环自引用，并仍然绑定完整录制元数据和 Chunk 列表。

## 安全与生命周期

- 捕获前固定录制策略、数据分类、保留期限和用户同意。
- 未脱敏 Frame 只存在于 Runtime Gateway 的有界内存缓冲，不进入数据库、持久消息、Temporal History 或对象存储。
- Runtime Gateway 先执行 Emit-time Secret/Home Path Scrub、长度限制和闭合 Schema 校验；失败时丢弃 Frame 并将 Recording 标记为部分失败或失败，不能 Fail-open。
- 只有脱敏验证成功的字节才能进入 Artifact Staging 并创建不可变 Chunk ArtifactVersion；Chunk 固化 Redaction Profile/Evidence Digest。
- Chunk 使用加密 Artifact Storage 和对象级 Grant。
- `recording:read` 与 `runtime:view` 权限相互独立。
- 删除和法律保留遵循 Artifact Policy；Audit 保留决策，不保留已删除内容。
- 部分失败或 Finalize 失败必须可见，不得表现为完整录制。

```text
Live Frame
 -> bounded memory buffer
 -> emit-time scrub + schema validation
 -> encrypted Artifact Staging
 -> immutable sanitized Chunk ArtifactVersion
 -> Recording Manifest
```

## 调试副本与重新运行

RuntimeRecording 回放始终只读。Agent Engineering Workbench 可以把 Recording、CanonicalEvent、RunManifest、ArtifactVersion 和 TechnicalUsage 组合为调试投影，但该投影不能修改原始证据。

```text
不可变 Run Evidence
 -> 只读回放
 -> 显式创建调试副本
 -> 新 ConversationBranch + WorkOrder + ExecutionGrant
 -> 新 Run
```

- 调试副本记录来源 Run、Recording Manifest、Event Cursor 范围、Artifact 摘要和 ProviderRevision。
- 修改 Prompt、消息、Tool、Model 或变量只作用于调试副本；原始证据不变。
- 重新运行必须重新执行 Business 授权、ProviderResolution、预算和 Gateway 策略，不得沿用旧 Run 的 ExecutionGrant。
- 新 Run 产生独立的 Event、Usage、Artifact 和 Recording；结果不得追加到旧 Recording。
- 导入的第三方 Trace 只能作为带来源标记的外部证据或调试输入，不能提升为平台执行成功的证明。

本节不定义新的 v0.9 持久化对象；实现可以先使用只读投影和短期调试状态。若后续需要长期保存调试副本或评测结果，必须先新增正式契约、授权、保留和删除语义。
