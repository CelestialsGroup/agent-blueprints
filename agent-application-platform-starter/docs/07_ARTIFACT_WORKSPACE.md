# Artifact Workspace 规范

## 1. Workspace

v1：一个 AgentConversation 对应一个内部持久 Workspace；Conversation 的多个 WorkOrder/AgentRun 共享该 Workspace 的版本化 Artifact 视图。一次性调用创建隐式 Conversation/Workspace。

负责：

- Sandbox 文件上下文
- Artifact 集合
- Ingest
- 预览/编辑
- 转换
- Delivery
- Runtime Recording Chunk/回放 Manifest

## 2. 稳定内核

- Artifact Metadata
- ArtifactVersion
- Relation
- Staging
- IngestSession
- EditSession
- Commit
- Conflict
- Lifecycle/Audit

## 3. 生命周期

ArtifactVersion 内容不可变，生命周期状态单独变化：

- ready
- quarantined
- deleted
- retained_for_legal_hold

## 4. 数据导入

外部文件先进入 Ingest/Staging：

- size
- media type
- digest
- malware
- tenant
- content policy

验证后创建 ArtifactVersion。

## 5. 编辑

```text
Version
 -> EditSession(base)
 -> Draft
 -> Commit
 -> New Version
```

提交使用 CAS 与 Idempotency-Key。

## 6. 转换

```text
源 Version
 -> Invocation
 -> Converter
 -> Staging
 -> Validation
 -> Derived Artifact Version
```

保留 `converted_from` 关系。

## 7. 代码

代码以 Sandbox Workspace 为编辑源。

Artifact 负责 Snapshot、Diff、Version、导出和交付。

## 8. 预览安全

HTML 使用隔离 Origin、Sandboxed iframe、CSP 和受控出站访问。

Office/PDF/Image/Video 先扫描，宏和主动内容默认不执行。

## 9. Sandbox Workspace 契约

```text
/inputs      read-only Artifact
/workspace   mutable working tree
/outputs     Artifact Staging
/tmp         ephemeral
```

Workspace Snapshot 是 Sandbox 与 Artifact Workspace 的连接点。

Sandbox Provider 不直接创建 ArtifactVersion；平台验证 `/outputs` 或 Staging Manifest 后提交。
