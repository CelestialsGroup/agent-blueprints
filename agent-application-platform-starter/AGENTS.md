# Agent Application Platform v0.9.0 — implementation rules

## Authority

`START_HERE.md`、本文件、`docs/00_ARCHITECTURE_BASELINE.md`、`docs/DECISIONS.md` 与可执行契约是当前事实源。发生冲突时，Schema、状态机、数据库约束和 Gate 优先于叙述性文档。不得恢复 v0.8.6 或更早设计。

## Frozen boundary impact check

任何架构变更先分类：

1. 文档澄清；
2. 契约变更（Schema/OpenAPI/状态机）；
3. 实现变更；
4. 生产验证变更。

涉及 Business/Platform 所有权、稳定内核字段、Provider 可替换性、可靠性语义或安全边界时，视为边界变更，必须更新 `docs/DECISIONS.md`、契约、兼容性判定和验证报告。

## Domain ownership

- Business：User、Membership、Product、Order、Payment、Entitlement、Commercial Quota Reservation/Settlement。
- Agent Platform：AgentConversation、ConversationBranch、ConversationMessage、WorkOrder、Workspace、Workflow、Invocation、Canonical Event、Artifact、Technical Usage、Delivery、Provider、Sandbox、RuntimeRecording、Experience Catalog、Audit。
- Redis 只允许 Cache、Presence、Wakeup；PostgreSQL/Temporal/Event/Artifact 元数据才是事实源。

## Provider model

```text
Scenario
 -> CapabilityDefinition
 -> ProviderResolution
 -> immutable ProviderRevision
 -> ProviderAdmissionDecision
 -> Plugin / Runtime / Sandbox Provider
```

- ProviderRevision 创建后按摘要不可变。
- certification/revocation 是 append-only ProviderAdmissionDecision，不得回写 Revision。
- RunManifest 固化 Revision 与当时有效 Admission Decision 的摘要快照。
- html-anything、html-to-pptx、模型、工具、Runtime、Sandbox 均通过 Capability/Provider Port 解析，不得写死在稳定内核。
- Template/Skill/Design System 等用户可见 Experience 必须绑定 immutable Catalog Revision + ProviderRevision；不得只保存 mutable template_id。

## Conversation and runtime

- Conversation owns one durable Workspace and append-only Message sequence; WorkOrder is one executable Turn.
- WorkOrder、ExecutionGrant、RunManifest 与 Event 必须绑定 conversation/turn/branch/input_message。
- DeerFlow 只通过 AgentRuntimeProvider v1 接入；DeerFlow Thread/Run/Checkpoint/Event payload 属于 Adapter 私有模型。
- 每个可执行 follow-up 需要新的 Business ExecutionGrant；WorkSession 不能扩大商业授权。

## Reliability

唯一承诺为 At-least-once + Idempotency + Fencing Token + Reconciliation + Transactional Outbox + Immutable Version。不得宣称全局 Exactly-once。

```text
Temporal durable history
+ PostgreSQL current state and ledgers
+ Outbox/Inbox
+ Append-only canonical event
+ Artifact staging/finalization
```

Temporal 决定编排历史；PostgreSQL 决定查询态和账本。任何双写必须经 Outbox/Inbox 或可重放协调器闭合。

## Invocation and Sandbox operation

逻辑 Invocation/Operation 与 Attempt 分离。每次网络尝试拥有唯一 attempt_id 和严格递增 fencing_token；Invocation Attempt 编号从 1 连续，current_attempt_id/attempt_count/request_digest 必须与 append-only 历史一致。响应丢失或结果未知必须进入 reconciling；超时进入 manual_review_required；取消 intent 不等于取消证明。最终只能由证据 resolve success/failure/cancel、retry，或以 `risk_accepted=true` abandon。聚合记录必须引用 ReconciliationCase 和 ManualReviewDecision；Validator 从 Aggregate status 推导 Decision/outcome，并验证 Case 版本、摘要、证据及平台时间顺序。非幂等重试不得走自动重试事件。

Sandbox Provider API 返回的是单次 transport status；平台的 SandboxOperation v2 才是持久化聚合状态机。

## Sandbox isolation

Workspace 通过 `sandboxes[]` 和唯一 `sandbox_slot_key` 支持 `primary-code`、`browser`、`desktop`、`subagent/*`、`isolated/*`。`primary_sandbox_slot_key` 必须恰好引用一个 Slot。

稳定内核禁止保存 Kubernetes Pod/Namespace/Container ID、VM/Node ID 和原始 Runtime Endpoint。Runtime Session 只暴露短期、受授权、可审计的 Gateway Route。

RuntimeRecording 与 live RuntimeSession 分离，由 Runtime Gateway 生成 immutable Artifact chunks 和 playback manifest。录制字节不得进入 PostgreSQL Event payload 或 Temporal History。

## Contract rules

- JSON：Draft 2020-12、绝对 `$id`、Registry 解析、Strict I-JSON、RFC 8785 JCS。
- 复用：SandboxSpec、ProviderRevisionSnapshot 等必须通过 `$ref` 复用，禁止复制展开。
- 语义约束：由 `validate_semantics.py` 与反向 Fixture 执行。
- OpenAPI：原始契约保留绝对 URN；Redocly 只 lint/bundle 由 Registry 投影生成的 `build/openapi-src`，结果必须 0 error/0 warning。
- 兼容性：CI 只与受保护变量指定的冻结基线比较且缺失时 fail-closed；首个冻结基线前必须由受保护变量显式允许 N/A，不得写成 pass。
- 供应链：Python hash lock、npm integrity、Actions full SHA；Git 跟踪文件不得包含 bytecode/`.DS_Store`，monorepo 必须提交 Git 根 Workflow。

## Admission and production claims

必须运行：

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

公共 CI 全绿前不得冻结、不得进入 Phase 1。即使 Contract Gate 全绿，也只证明契约可接纳，不证明生产可靠性。
