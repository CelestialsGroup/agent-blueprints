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

外部文件使用 ArtifactIngest 的 Create/Status/Confirm/Scan/Finalize 分阶段协议。Create 请求只绑定 Tenant、ClientApplication、Principal、CommercialAuthorization、上传意图与请求摘要；Platform 分配 Session 后才生成同 Scope 的 PolicyDecision、ExecutionBudget 与 EffectivePermissions 并写入持久聚合。Status 按所有权授权且不泄漏跨租户存在性；Confirm 对 Session + 上传摘要幂等；Scan 固化 Scanner Revision/Profile/Suite 和精确内容摘要；只有 Platform Finalize 事务能创建 ArtifactVersion 与 Outbox。上传完成或 Scanner `passed` 都不能直接 Finalize。

外部文件先进入 Ingest/Staging，并记录：

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

Preview/Edit/Conversion 的公共执行所有者统一为 ArtifactOperation。客户端只提交 Tenant、ClientApplication、Principal、ArtifactVersion、Capability、CommercialAuthorization、QuotaReservation、幂等键和请求摘要，不能提交 `artifact_operation_id`、Policy/Budget/EffectivePermissions、Gateway、ProviderResolution 或 Invocation。Platform 认证请求并分配 Operation 后生成这些 admission facts。客户端请求摘要与 Provider CapabilityInvocationRequest 摘要分离保存；全部派生授权、唯一 Invocation/Attempt、Artifact Grant/Staging、TechnicalUsage、终态与核心事件都绑定同一个 `artifact_operation` ExecutionScope。EditSession、PreviewSession 和 ConversionJob 只是 Projection，不能调度 Provider、重试或宣告终态。

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

该规则适用于所有 Agent Runtime、Capability、Plugin 和 Sandbox Provider。读取使用带摘要的 ArtifactGrant；写入使用绑定 Tenant/ExecutionScope/InvocationAttempt、Artifact Gateway Contract/Audience、媒体类型和字节/对象上限的 ArtifactStagingGrant，每次读写/Commit 还必须携带最长 300 秒的操作 Token。Provider 权限只有 `read` 或 `stage_new_version`；Staging Commit 仍处于 Quarantine，Finalize 是 Platform 内部、幂等且可对账的 Ledger 事务。
