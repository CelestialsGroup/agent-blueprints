# Artifact Workspace

## 1. Workspace

v1：一个 AgentConversation 对应一个内部 durable Workspace；Conversation 的多个 WorkOrder/AgentRun 共享该 Workspace 的版本化 Artifact 视图。一次性调用创建隐式 Conversation/Workspace。

负责：

- Sandbox file context
- Artifact collection
- Ingest
- Preview/Edit
- Conversion
- Delivery
- Runtime Recording chunks/playback manifests

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

## 4. Ingest

外部文件先进入 Ingest/Staging：

- size
- media type
- digest
- malware
- tenant
- content policy

验证后创建 ArtifactVersion。

## 5. Edit

```text
Version
 -> EditSession(base)
 -> Draft
 -> Commit
 -> New Version
```

Commit 使用 CAS 与 Idempotency-Key。

## 6. Conversion

```text
Source Version
 -> Invocation
 -> Converter
 -> Staging
 -> Validation
 -> Derived Artifact Version
```

保留 converted_from Relation。

## 7. 代码

代码以 Sandbox Workspace 为编辑源。

Artifact 负责 Snapshot、Diff、Version、Export 和 Delivery。

## 8. Preview Security

HTML 使用隔离 Origin、sandbox iframe、CSP 和受控 Egress。

Office/PDF/Image/Video 先扫描，宏和主动内容默认不执行。

## 9. Sandbox Workspace Contract

```text
/inputs      read-only Artifact
/workspace   mutable working tree
/outputs     Artifact Staging
/tmp         ephemeral
```

Workspace Snapshot 是 Sandbox 与 Artifact Workspace 的连接点。

Sandbox Provider 不直接创建 ArtifactVersion；平台验证 `/outputs` 或 Staging Manifest 后 Commit。
