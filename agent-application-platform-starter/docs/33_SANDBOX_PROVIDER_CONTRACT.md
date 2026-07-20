# Sandbox Provider 契约

## 目标

平台前期可以使用 DeerFlow Built-in Sandbox 作为首个参考实现，但不把它设为前置依赖；后期可以切换到自研 `sandbox-runtime` 或其他符合契约的 Provider。

两者必须实现同一个稳定接口：

```text
Agent Platform 稳定内核
  SandboxRegistry / Lease / Operation / RuntimeSession / Usage
          ↓
Sandbox Provider 契约
          ↓
DeerFlow Sandbox Adapter | sandbox-runtime | 其他 Provider
```

替换 Provider 时不得修改：

- WorkOrder
- Workflow
- AgentRun
- Invocation
- CanonicalEvent
- Artifact
- Runtime Gateway
- 前端
- Usage / Delivery

## 核心归属

### Agent Platform 稳定内核

- SandboxRegistry
- Sandbox 期望状态
- Lease 策略
- Provider Resolution
- Tenant/WorkOrder/Workspace 映射
- SandboxOperation 账本
- RuntimeSession 用户授权
- Artifact Staging
- Technical Usage 标准化
- Audit

### Sandbox Provider

- 后端 Provisioning
- 观测状态
- Exec
- 内部 Runtime Endpoint
- Snapshot/Restore
- 后端资源计量
- 清理

Provider 不拥有业务授权和 Artifact 元数据。

## Provider Port

权威传输契约是 [`sandbox-provider-v1.yaml`](../contracts/openapi/sandbox-provider-v1.yaml)，Provider Adapter 必须实现其中的操作族：

- Capability 发现
- 创建/查询/期望状态/Lease/终止
- 执行/取消/结果
- Runtime Session
- Snapshot/Manifest/恢复
- Operation 查询与 Event Stream

具体语言接口由该 OpenAPI 生成或薄封装，不在叙述性文档中复制方法签名。

## 传输授权与摘要绑定

Capability 发现发生在 Sandbox 和 SandboxOperation 建立之前，因此 `/v1/capabilities` 只接受已准入控制面的 mTLS 身份，不接受也不要求无法构造的 Sandbox Operation Token。它不是用户或 Runtime 可直接调用的公共发现接口。

其余 14 个操作同时要求 mTLS 与最长 300 秒的单操作 Token。Token 必须绑定：

- 当前调用工作负载 `sub` 与唯一 Provider Instance audience；
- Tenant、WorkOrder、ProviderRevision、Sandbox、Operation、Attempt 和 Fencing Token；
- 唯一 `operation`、`request_contract_id`、`request_digest_profile` 与 `request_digest`；
- Policy Digest 和本次授权 `deadline_at`。

9 个写操作固定使用 `rfc8785-request-excluding-request-digest-v1`，摘要覆盖去除 `request_digest` 的完整请求体；路径中的 `sandbox_id` 还必须与 Token 一致。状态、Operation、Exec Result、Snapshot Manifest 和 Event Stream 5 个读操作固定使用各自正式 Descriptor 与 `rfc8785-full-document-v1`；Provider 从 Token、HTTP Path 和按 OpenAPI 默认值归一化后的 Query 合成 Descriptor 后再验证摘要。修改 Path、Operation、Attempt、Fencing 或 `after_sequence` 都必须拒绝，不能让一个合法 Token 跨接口重放。

Capability 发现和每个受令牌保护的操作映射由 OpenAPI 扩展与静态 Gate 强制检查；真正的签名验证、`jti` 重放拒绝、旧 Fencing 拒绝和多节点一致性仍属于 Sandbox Conformance 与实现证据，不能由 Schema 通过替代。

Sandbox Operation Token 的 `nbf` 不得早于所绑定 PolicyDecision，`exp` 不得晚于该 Operation Deadline。商业执行窗口结束后仍允许平台创建新的 Cancel/Terminate 治理 Operation，但不能复用旧执行 Token 或恢复执行权限。

## Capability 协商

Provider 必须显式声明支持能力和版本：

- sandbox.exec
- sandbox.terminal
- sandbox.browser
- sandbox.desktop
- sandbox.port-forward
- sandbox.workspace.persistent
- sandbox.snapshot.workspace
- sandbox.snapshot.filesystem
- sandbox.snapshot.process
- sandbox.restore
- sandbox.network-policy
- sandbox.gpu
- sandbox.nested-container
- sandbox.user-namespace

Scenario/Agent Runtime 只声明需要的 Sandbox Capability，不依赖具体 Provider。

不支持时返回：

```text
SANDBOX_CAPABILITY_UNSUPPORTED
```

禁止静默降级。

## SandboxSpec

SandboxSpec 是平台解析 Policy、ExecutionBudget 和 Provider Capability 后产生的规范。

必须包含：

- 内部 Sandbox/Tenant/Work/Workspace ID
- 不可变 ProviderRevision
- OCI Image 引用 + 摘要
- Runtime Profile
- 资源限制
- 必需/可选 Capability
- 网络模式/策略
- Workspace 模式/Snapshot
- Lease
- Placement 约束
- 安全基线

外部业务系统不能直接构造 SandboxSpec。

## 期望状态与观测状态

Agent Platform 保存期望状态，Provider 返回观测状态。

```text
desired_state: ready | suspended | terminated
observed_state:
  requested | provisioning | ready | suspending | suspended
  | resuming | terminating | terminated | expired | failed
```

使用：

```text
generation
observed_generation
```

用于实现乐观并发和 Controller 对账。

## Operation、Attempt 与 Fencing 机制

所有修改操作携带：

- operation_id
- attempt_id
- fencing_token
- idempotency_key
- request_digest（适用时）
- deadline

旧 Attempt 或旧 Fencing Token 结果不得覆盖新状态。

Provider 可能已经产生副作用时，平台只接受当前 Attempt 的状态更新；无法确认时进入 `outcome_unknown`。

## Runtime Session

Provider 只返回内部 Endpoint 引用。

```text
Sandbox Provider
  -> SandboxRuntimeSessionEndpoint
  -> Agent Runtime Gateway
  -> User RuntimeSession
```

Provider 的内部 Pod IP、Node IP 和凭据不得直接返回给浏览器。

用户创建 RuntimeSession 时必须指定 RunManifest 中的逻辑 `sandbox_slot_key`；Gateway 再解析 Provider 私有路由。多 Sandbox WorkOrder 不能依赖“第一个 Sandbox”或裸 Sandbox ID 猜测目标。

支持：

- terminal
- browser
- desktop
- port_forward

## Workspace 路径

Provider 对 Agent 暴露固定语义：

```text
/inputs      只读 Artifact 输入
/workspace   可变工作区
/outputs     Artifact Staging 输出
/tmp         临时文件
```

宿主机、平台数据库、业务存储不通过文件系统暴露。

`/workspace` 不是 Conversation 级共享可变目录。SandboxSpec 固化 ProviderResolution、Branch WorkspaceRevision ID/Digest 和 `base_workspace_head_version`；只读任务不提交，写任务以 `cas_new_revision` 创建新 Revision，并通过 Workspace Head Version CAS 推进 Head。Message 和 Active Work 的版本变化不应导致 Workspace 假冲突。

## OCI 与底层 Runtime

- Sandbox Image 必须兼容 OCI Image 规范。
- Provider 自研底层 Container Runtime 时，应兼容 OCI Runtime 规范。
- 只有作为 Kubernetes Node Runtime 替代 containerd/CRI-O 时才需要实现 CRI。
- Kubernetes 多 Runtime 场景推荐映射 RuntimeClass。
- Sandbox Provider Contract 不暴露 Kubernetes Pod、CRI 或某个 VM 后端细节。

## 标准错误

- SANDBOX_SPEC_INVALID
- SANDBOX_CAPABILITY_UNSUPPORTED
- SANDBOX_POLICY_DENIED
- SANDBOX_QUOTA_EXCEEDED
- SANDBOX_IMAGE_NOT_FOUND
- SANDBOX_IMAGE_PULL_FAILED
- SANDBOX_PROVISIONING_FAILED
- SANDBOX_UNAVAILABLE
- SANDBOX_LEASE_EXPIRED
- SANDBOX_GENERATION_CONFLICT
- SANDBOX_STALE_FENCING_TOKEN
- SANDBOX_EXEC_FAILED
- SANDBOX_EXEC_OUTCOME_UNKNOWN
- SANDBOX_SESSION_EXPIRED
- SANDBOX_SNAPSHOT_FAILED
- SANDBOX_RESTORE_INCOMPATIBLE
- SANDBOX_TERMINATION_FAILED

错误必须使用 StandardError，并为外部执行结果提供 `known_failed` 或 `outcome_unknown` 语义。

## 多 Sandbox 与 Slot

一个 Conversation Workspace 可以拥有多个 Sandbox；每个 WorkOrder 的 RunManifest 只绑定本次 Turn 实际使用的 Slot。Sandbox 由 Scenario/Runtime Capability 按需创建，纯聊天、远程 Tool 或不需要文件系统的 Run 可以使用空 `sandboxes[]`。

平台使用 `sandbox_slot_key` 表达 WorkOrder 内的逻辑用途；唯一约束是 `(work_order_id, sandbox_slot_key)`，因此不同 Branch 可以并行使用同名 `primary-code`：

```text
primary-code
browser
desktop
subagent/<agent-run-id>
isolated/<capability>
```

Provider Resolution 可以为不同 Slot 选择不同：

- ProviderRevision
- Runtime Profile
- 隔离类别
- 资源类别
- Region/Cell

同一 Slot 的后端重建通过 Generation 表达；不同用途使用不同 Slot。

## Provider 私有模型

公共 SandboxStatus 只允许：

```text
provider_state_reference
runtime_endpoint_reference
```

它们都是受权限控制的不透明引用。

公共状态不得携带 `runtime_id`、Region、Cluster、Cell、Node、Pod、VM、Container 或原始 Endpoint；逻辑 `runtime_profile` 不属于后端身份，可以保留。拓扑和后端运行时身份只能存在于 Provider Adapter 私有存储。

实际的 Pod、VM、Container 和 Endpoint 数据保存在 Adapter 私有存储，
不得进入 CanonicalEvent、RunManifest、用户 API 或稳定内核表。

RunManifest 使用 `sandboxes[]` 锁定多个 Sandbox Slot。每个 Slot 只引用一个 Sandbox ProviderResolution，不复制 ProviderRevision；数组非空时用 `primary_sandbox_slot_key` 标识默认工作环境，为空时该字段必须不存在。禁止重新收缩为单一 Sandbox 字段或强制所有 Runtime 创建 Sandbox。

## 生命周期、Lease 与 Snapshot

Provider 单次传输 Attempt 返回 `SandboxOperationStatus`：`accepted`/`running`/`succeeded`/`failed`/`cancelled`/`outcome_unknown`。平台不得把 `outcome_unknown` 作为持久化终点；它必须原子转换为 SandboxOperation `reconciling`。

平台逻辑聚合使用 `sandbox-operation-record:v2` 和 `contracts/state-machines/sandbox-operation-v2.json`，支持重试、对账 Deadline、人工复核、安全取消确认和 `abandoned`。每个 Attempt 拥有新 `attempt_id` 与更高 `fencing_token`，旧响应必须被拒绝。

SandboxRegistry 保存期望状态、租约、Slot 与代数；Provider Adapter 保存实际 Pod/VM/Container/Endpoint。Lease 过期由 Temporal 定时器驱动终止/对账，不能依赖 Redis TTL 作为事实。

SnapshotManifest 固化 `provider_revision_id`、Level、摘要、Size、`content_reference` 和兼容性。Workspace 级 Snapshot 可跨符合契约的 Provider 迁移；Filesystem/Process 级默认只在声明兼容时恢复。Restore 使用标准变更 Envelope，并为恢复后的 Sandbox 分配新的 `sandbox_id` 和显式 Slot；Snapshot 本身不可变。

## 对账与取消

Provider 响应丢失时，先用 `provider_operation_id`/幂等键查询证据；不得盲目重试非幂等副作用。到达 Deadline 后证据仍不足则进入人工复核；人工 Decision 必须仅允许追加，并带证据引用和摘要。

取消请求只表达意图。运行中请求先进入 `cancel_requested`；未知结果继续对账。只有 Provider/人工证据写入 `cancellation_confirmation` 并经过 `cancellation_confirmed`，或平台证明从未派发/当前没有执行中的 Attempt，才允许终态 `cancelled`。无法证明时只能继续对账，或由 `risk_accepted=true` 的人工决策进入 `abandoned`。
