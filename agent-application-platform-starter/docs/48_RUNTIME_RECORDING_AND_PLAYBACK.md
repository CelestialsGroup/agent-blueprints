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
- Runtime Gateway 在 Finalize 前对 Secret 和授权材料脱敏。
- Chunk 使用加密 Artifact Storage 和对象级 Grant。
- `recording:read` 与 `runtime:view` 权限相互独立。
- 删除和法律保留遵循 Artifact Policy；Audit 保留决策，不保留已删除内容。
- 部分失败或 Finalize 失败必须可见，不得表现为完整录制。
