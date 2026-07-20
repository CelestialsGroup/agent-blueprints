# Artifact Workspace 规范

## Workspace

v1：一个 AgentConversation 对应一个内部持久 Workspace；每个 ConversationBranch 保存不可变 WorkspaceRevision Head。多个 WorkOrder/AgentRun 共享版本化 Artifact 集合，但不共享可变文件头。一次性调用创建隐式 Conversation/Workspace/Main Branch/初始 Revision。

```text
Workspace
 -> Branch A -> WorkspaceRevision 1 -> 2 -> 3
 -> Branch B -> forked_from Revision 2 -> WorkspaceRevision 1 -> 2
```

WorkOrder 准入时固化 Branch Head Revision；Sandbox 只挂载该 Revision。成功提交生成新 Revision，并用 `workspace_head_version` CAS 推进 Head；Message 追加使用 `message_head_version`，Steering 使用 `active_work_version`，互不制造假冲突。冲突必须显式合并、重试或创建新 Branch，不能覆盖另一分支的文件状态。

WorkspaceRevision 的 Manifest Artifact 必须验证 `workspace-content-manifest-v1`：路径为规范化相对 POSIX 路径，File 固化 Mode/Digest/Size，计数与总字节闭合，Symlink 默认禁止；允许时也只能指向 Workspace Root 内且不得借其他 Symlink 穿越。

负责：

- Sandbox 文件上下文
- Artifact 集合
- Ingest
- 预览/编辑
- 转换
- Delivery
- Runtime Recording Chunk/回放 Manifest

## 稳定内核

- Artifact Metadata
- ArtifactVersion
- Relation
- Staging
- IngestSession
- EditSession
- Commit
- Conflict
- Lifecycle/Audit

## 生命周期

ArtifactVersion 内容不可变，生命周期状态单独变化：

- ready
- quarantined
- deleted
- retained_for_legal_hold

## 数据导入

外部文件先进入 Ingest/Staging：

- size
- media type
- digest
- malware
- tenant
- content policy

验证后创建 ArtifactVersion。

## 编辑

```text
Version
 -> EditSession(base)
 -> Draft
 -> Commit
 -> New Version
```

提交使用 CAS 与 Idempotency-Key。

## 转换

```text
源 Version
 -> Invocation
 -> Converter
 -> Staging
 -> Validation
 -> Derived Artifact Version
```

保留 `converted_from` 关系。

## 代码

代码以 Sandbox Workspace 为编辑源。

Artifact 负责 Snapshot、Diff、Version、导出和交付。

## 预览安全

HTML 使用隔离 Origin、Sandboxed iframe、CSP 和受控出站访问。

Office/PDF/Image/Video 先扫描，宏和主动内容默认不执行。

## Sandbox Workspace 契约

```text
/inputs      read-only Artifact
/workspace   mutable working tree
/outputs     Artifact Staging
/tmp         ephemeral
```

WorkspaceRevision 的内容 Manifest Artifact 是平台版本事实；Workspace Snapshot 是 Sandbox Provider 对该 Revision 的可移植或 Provider 私有恢复表示。两者通过摘要绑定，但 Snapshot 不能取代 Branch Head。

Sandbox Provider 不直接创建 ArtifactVersion；平台验证 `/outputs` 或 Staging Manifest 后提交。

该规则适用于所有 Agent Runtime、Capability、Plugin 和 Sandbox Provider。Provider ArtifactGrant/EffectivePermissions 只有 `read` 或 `stage_new_version`；Finalize 是 Platform 内部、幂等且可对账的 Ledger 事务。
