# Agent Application Platform v0.9.0 — 实施规则

## 权威来源

`START_HERE.md`、本文件、`docs/00_ARCHITECTURE_BASELINE.md`、`docs/DECISIONS.md` 与可执行契约是当前事实源。发生冲突时，Schema、状态机、数据库约束和 Gate 优先于叙述性文档。不得恢复 v0.8.6 或更早设计。

## 冻结边界影响检查

任何架构变更先分类：

1. 文档澄清；
2. 契约变更（Schema/OpenAPI/状态机）；
3. 实现变更；
4. 生产验证变更。

涉及 Business/Platform 所有权、稳定内核字段、Provider 可替换性、可靠性语义或安全边界时，视为边界变更，必须更新 `docs/DECISIONS.md`、契约、兼容性判定和验证报告。

## 领域所有权

- Business：User、Membership、Product、Order、Payment、Entitlement、Commercial Quota Reservation/Settlement。
- Agent Platform：AgentConversation、ConversationBranch、ConversationMessage、WorkOrder、Workspace、Workflow、Invocation、Canonical Event、Artifact、Technical Usage、Delivery、Provider、Sandbox、RuntimeRecording、Experience Catalog、Audit。
- Redis 只允许 Cache、Presence、Wakeup；PostgreSQL/Temporal/Event/Artifact 元数据才是事实源。

## Provider 模型

```text
Scenario
 -> CapabilityDefinition
 -> ProviderResolution
 -> immutable ProviderRevision
 -> ProviderAdmissionDecision
 -> Plugin / Runtime / Sandbox Provider
```

- ProviderRevision 创建后按摘要不可变。
- ProviderResolution 必须绑定 Resolver Revision、完整输入摘要、逐候选结论、不可变证据和 Decision Digest；只保存“选了谁”不构成可审计解析。
- ProviderResolution 必须显式绑定 `tenant_id + client_app_id + work_order_id`，通过 `identity_dependency` 声明解析是否依赖身份；依赖身份时必须绑定 PrincipalContextSnapshot Digest。幂等记录唯一范围固定为 Tenant + ClientApplication + Operation + Key Digest。
- ProviderRevision 的公共 Envelope 只包含 Provider kind、Implementation、Port、配置、权限、凭据和 Conformance；Runtime、Sandbox 和 Capability Provider 不得被强制包装成 Plugin。
- Implementation 必须绑定不可变 BuildProvenance，包括 Source Revision、Source Tree、Build Artifact、SBOM 和 Provenance Statement 摘要。
- 认证/撤销使用仅追加的 ProviderAdmissionDecision，不得回写 Revision。
- RunManifest 固化 Revision 与当时有效准入决策的摘要快照。
- Conformance 结果必须绑定不可变 Suite ID/Version/Digest/Profile 和 Evidence；README 或 Provider 自报通过不构成认证。
- html-anything、html-to-pptx、模型、工具、Runtime、Sandbox 均通过 Capability/Provider Port 解析，不得写死在稳定内核。
- Template/Skill/Design System 等用户可见 Experience 必须绑定不可变 Catalog Revision + ProviderRevision；不得只保存可变 `template_id`。

## Conversation 与 Runtime

- Conversation 拥有一个持久 Workspace 和仅追加的 Message 序列；WorkOrder 表示一个可执行 Turn。
- WorkOrder、ExecutionGrant、RunManifest 与 Event 必须绑定 Conversation/Turn/Branch/Input Message。
- 一个 WorkOrder 拥有一个平台 WorkflowRun；一个 WorkflowRun 拥有一个根 AgentRun 和零到多个显式父子关系的 Sub-agent AgentRun。一个 AgentRun 只绑定一个 RunManifest 和一个 AgentRuntimeRun；传输重试属于同一 Invocation 的 Attempt，不创建第二个逻辑 Run。
- WorkflowRun、AgentRun、RunManifest 和 Runtime Start 显式携带同一 `tenant_id`；RunManifest 的 Runtime 与每个 Sandbox Slot 都只引用已固化的 ProviderResolution，不复制第二份 Revision/Conformance 事实。
- 所有 Agent Runtime（包括 DeerFlow、LangGraph、OpenAI Agents SDK 或 Native Runtime）都只能通过 AgentRuntimeProvider v1 接入；框架原生 Agent/Thread/Run/Checkpoint/Event 原始载荷属于 Adapter 私有模型。
- 不得把任何单一 Agent 框架设为稳定内核的编译时依赖、领域事实源或唯一合法实现。
- 每个 Run 在准入时锁定 Agent Runtime ProviderRevision；运行中不得自动切换框架。Provider 原生 Checkpoint 只能在明确声明并通过测试的兼容范围内恢复。
- 每个可执行后续输入都需要新的 Business ExecutionGrant；WorkSession 不能扩大商业授权。
- `ConversationTurnRequest` 只创建新 Turn/WorkOrder；`WorkOrderControlRequest` 只控制现有 WorkOrder。`interrupt_and_enqueue` 先记录当前 WorkOrder 取消意图，再创建独立后继 WorkOrder；不得把 Append/Interrupt 偷换成新 Turn。
- ExecutionGrant 必须声明 `request_contract_id` 与固定 Digest Profile，并绑定该精确请求去除 `execution_grant` 后的 JCS 摘要；Turn Grant 绑定 Turn/Message/Scenario，Control Grant 只绑定现有 WorkOrder/ControlRequest，不得携带陈旧 Turn 字段。Grant 内嵌有界 PrincipalContextSnapshot 并校验其摘要。
- Runtime Command 与核心 Runtime Event Payload 必须使用类型化 Schema；Provider 私有 Event 不能直接驱动 Chat、Plan、Task、Usage 或终态 Projection。
- RunManifest 通过 `request_contract_id + request_digest_profile + request_digest` 精确绑定已消费 ExecutionGrant 的原始请求，并固化实际有界输入或不可变引用、ContextPackage、ArtifactAccessRequirement、初始 Budget/Policy/Permissions 上限、授权续期规则和类型化 Model/Tool/Artifact/Egress Gateway Binding；不保存会过期的 bearer Grant。
- Runtime Start 携带与 Manifest 一致的 Input/Context/Gateway，以及本 Attempt 的短期 RuntimeAuthorization。Authorization 以摘要和前驱链仅追加，内部 Budget/Policy/Permissions 必须绑定同一 Tenant/WorkOrder/CommercialAuthorization，且不能越过 RunManifest 固化的商业授权到期上限；Token 过期、Adapter 重启或 Resume 时只能等价/缩权续期并刷新同一授权时间窗内的 ArtifactGrant，扩权必须新建 WorkOrder、ExecutionGrant、ProviderResolution 和 RunManifest。
- Runtime 调用使用短期 AgentRuntimeInvocation Token，绑定 Tenant、ProviderRevision、WorkflowRun/AgentRun/RuntimeRun、RunManifest、RuntimeAuthorization、InvocationAttempt、Fencing、Policy、Budget、Permissions 和请求摘要。
- 通用 Capability 调用只使用 `capability-provider-v1`。请求携带完整 ExecutionBudget/PolicyDecision/EffectivePermissions 与 CommercialAuthorizationBinding，并显式绑定 ProviderResolution、ProviderInstance、ProviderRevision 和 admitted audience。独立 Token 只授权一个 Invoke/Status/Cancel/Event 操作，绑定原始请求与操作请求摘要，并以连续前驱 `jti` 在原 deadline/CommercialAuthorization 内等价续期；不得要求 `plugin_id`。Plugin Invocation 只保留为实现适配层。
- Model/Tool Gateway 复用 `capability-provider-v1`；Artifact 与 Egress 分别使用 `artifact-gateway-v1`、`egress-gateway-v1`。每个 Gateway Binding 必须携带 Contract ID/Digest、Route、Audience 与 Binding Digest。Provider 写入只使用 ArtifactStagingGrant 加更短期 Artifact Gateway 操作 Token，Staging Commit 不等于 ArtifactVersion Finalize。
- RunManifest 绑定 EventTypeRegistry 的 ID/Version/Digest；只有该 Registry 准入的 Payload 可以进入核心 Projection。
- Platform Core Registry 必须覆盖 Conversation、Message、WorkOrder/Control、WorkflowRun、AgentRun、GrantConsumption、Approval、Invocation、Artifact、Usage、Workspace、RuntimeSession/Recording 和 Delivery；Runtime Registry 只承载 Adapter 标准事件。

## 可靠性

唯一承诺为至少一次投递 + 幂等 + Fencing Token + 对账 + 事务 Outbox + 不可变版本。不得宣称全局 Exactly-once。

```text
Temporal 持久 History
+ PostgreSQL 当前状态与 Ledger
+ Outbox/Inbox
+ 仅追加 CanonicalEvent
+ Artifact 暂存/Finalize
```

Temporal 决定编排历史；PostgreSQL 决定查询态和账本。任何双写必须经 Outbox/Inbox 或可重放协调器闭合。

## Invocation 与 Sandbox Operation

逻辑 Invocation/Operation 与 Attempt 分离。每次网络尝试拥有唯一 `attempt_id` 和严格递增 `fencing_token`；Invocation Attempt 编号从 1 连续，`current_attempt_id`/`attempt_count`/`request_digest` 必须与仅追加历史一致。响应丢失或结果未知必须进入 `reconciling`；超时进入 `manual_review_required`；取消意图不等于取消证明。最终只能由证据解析为成功/失败/取消、重试，或以 `risk_accepted=true` 进入 `abandoned`。聚合记录必须引用 ReconciliationCase 和 ManualReviewDecision；Validator 从聚合状态推导决策/结果，并验证 Case 版本、摘要、证据及平台时间顺序。非幂等重试不得走自动重试事件。

Sandbox Provider API 返回的是单次传输状态；平台的 SandboxOperation v2 才是持久化聚合状态机。

## Sandbox 隔离

Conversation 拥有 Workspace，Branch 通过不可变 WorkspaceRevision Head 隔离文件历史。Sandbox 只挂载 RunManifest 固化的 Revision，提交通过 `workspace_head_version` CAS 产生新 Revision。Message、Workspace 与 Active Work 分别使用独立 CAS 版本，不得共享一个 Branch Version 制造假冲突。

Workspace 通过 `sandboxes[]` 和 WorkOrder 内唯一 `sandbox_slot_key` 支持 `primary-code`、`browser`、`desktop`、`subagent/*`、`isolated/*`。Sandbox 由 Scenario Capability 按需创建；数组为空时不得存在 `primary_sandbox_slot_key`，非空时它必须恰好引用一个 Slot。

稳定内核禁止保存 Kubernetes Pod/Namespace/Container ID、VM/Node ID 和原始 Runtime Endpoint。Runtime Session 只暴露短期、受授权、可审计的 Gateway 路由。

RuntimeRecording 与实时 RuntimeSession 分离，由 Runtime Gateway 生成不可变 Artifact Chunk 和回放 Manifest。录制字节不得进入 PostgreSQL Event Payload 或 Temporal History。

Runtime Gateway 使用 `runtime-gateway/v1` 类型化帧、Connection Generation、按 Channel 连续 Sequence、ACK/Window 背压和带摘要的幂等 Control Command。重连携带每个订阅 Channel 的 Cursor；窗口失效必须显式转入只读 Recording 回放，不能伪造连续实时流。`port_forward` 只允许实时传输，不进入 Recording。

未脱敏实时帧只能存在于有界内存缓冲；Emit-time Scrub 与闭合 Schema 校验成功后才允许创建 Recording ArtifactVersion。原始帧不得进入数据库、持久队列、Temporal History 或对象存储。

## Policy、Usage 与一致性

- PolicyDecision 合并 Business、Platform、Tenant、Client、Scenario 和 Runtime Profile 规则，固定使用 `deny > ask > allow`；`ask` 规范化为 Approval，任何 Allow 都不能覆盖 Deny。
- Policy Allow 不替代 OS Sandbox、NetworkPolicy、Gateway 或 Invocation Ledger，Hook、Prompt 和 Provider 自报权限都不是安全边界。
- TechnicalUsage 必须绑定 Tenant、WorkOrder、不可变 MeterDefinition、Producer/ProviderRevision 摘要、幂等键和 Evidence 摘要。Partial/Estimated 不得作为 Confirmed 或零用量结算；更正使用仅追加 Correction Entry。
- Provider 只返回 UsageObservation；`entry_id`、Platform Idempotency Key、归属和 `recorded_at` 由 Platform 校验后创建 TechnicalUsageEntry。
- Provider 只允许读取已准入 ArtifactVersion 或写 Artifact Staging；正式 ArtifactVersion Finalize 是 Platform 内部事务，不能出现在 Provider Grant 或 EffectivePermissions 中。
- UsageReport 与 BusinessSettlementEnvelope 按 Reservation 连续编号并只追加；Settlement Envelope 嵌入完整 Final/Correction UsageReport，Business 才能依据自己的价格事实结算。价格、余额、Settlement 决策和商业 Reconciliation 仍由 Business 拥有。
- 冻结 AgentRuntimeProvider 前，两个 Adapter 必须执行机器可读 `runtime-core-v1`；主 Runtime 还必须通过 `runtime-general-v1 + governed-v1`。Sandbox、Runtime Gateway、Capability Provider 与 Artifact/Egress Execution Gateway 使用各自 Suite Manifest 和不可变证据。

## 契约规则

- JSON：Draft 2020-12、绝对 `$id`、Registry 解析、Strict I-JSON、RFC 8785 JCS。
- 复用：SandboxSpec、ProviderRevisionSnapshot 等必须通过 `$ref` 复用，禁止复制展开。
- 语义约束：由 `validate_semantics.py` 与反向 Fixture 执行。
- 关键 `x-semantic-constraints` 必须进入 `contracts/semantic-constraints-v1.json`。每个 `contract_gate` Check ID 必须由当前 Validator 注册并在本次 Gate 真实执行；无法在契约阶段证明的 DDL/Conformance 责任必须明确标为 `phase0_implementation_required`，不得伪装成通过。
- 空 `limits: {}` 没有合法语义；EffectiveExecutionLimits 全字段必填且缺失即拒绝。HTTP 操作必须声明并执行 encoded-body 上限，超限在解析前返回 413。
- OpenAPI：原始契约保留绝对 URN；Redocly 只对 Registry 投影生成的 `build/openapi-src` 执行 Lint/Bundle，结果必须为 0 个错误、0 个警告。
- 兼容性：CI 只与受保护变量指定的冻结基线比较且缺失时 fail-closed；首个冻结基线前必须由受保护变量显式允许 N/A，不得写成 pass。
- 供应链：当前候选工具链固定 CPython 3.14.6、Node 24.18.0 Active LTS、pnpm 11.15.1 和 Go 1.26.5；Python 摘要锁、pnpm lock 完整性校验、Go toolchain、生产 OCI Digest 与 Actions 完整 SHA 都不得漂移或使用 `latest`。Git 跟踪文件不得包含 Bytecode/`.DS_Store`，Monorepo 必须提交 Git 根 Workflow。

## 准入与生产声明

架构设计阶段必须运行：

```bash
./scripts/bootstrap_contracts.sh
make validate-architecture
```

`make validate-all` 额外包含仓库供应链与 Monorepo/CI 准入，在正式冻结准备阶段启用。当前可以在本地 Architecture Contract Gate 通过后进入 Phase 0 实施；公共 CI 与冻结基线只阻止正式冻结和 Phase 1，不阻止候选架构的 Phase 0 实现。任何 Gate 全绿都不证明产品实现或生产可靠性。
