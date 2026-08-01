# Phase 0 - 产品纵向链路

Phase 0 实现一条真实、可恢复的 Manus-like Conversation 链路。目录骨架、生成代码、Schema 通过或单次 Happy Path 都不算完成。所有阶段按依赖顺序推进；未完成前置阶段时，不并行扩展产品范围。

本文由 Blueprint 定义实现顺序和验收责任，不记录 Application 的实时进度。产品源码、Migration、部署物和阶段证据必须在 Application 中交付，并分别绑定精确 Blueprint Revision、Contract Revision、Contract Manifest Digest 和所执行的 Conformance Suite Digest。

```text
0A 最小契约闭合
 -> 0B 持久化脊柱与 Native Runtime Core
 -> 0C Business 到 Conversation
 -> 0D 主 Runtime 与 Sandbox
 -> 0E Workbench 与 Recording
 -> 0F nexu Experience
 -> 0G Reference Runtime Probe
 -> 0H 故障、安全与恢复证据
```

## 0A：最小契约闭合

开始产品实现前，收敛 Phase 0 实际需要的公共模型：

- 固化可失败的 Tenant-qualified 拓扑：WorkOrder 在 Orchestration Start 成功后唯一绑定 WorkflowRun，WorkflowRun 在 Root Admission 成功后通过单次赋值 RootBinding 绑定 Root AgentRun；启动/准入失败不得伪造下游对象。每个 AgentRun 只绑定一个 RunManifest/AgentRuntimeRun；RunManifest Runtime 只引用一个 ProviderResolution；
- 固化平台治理的 ChildAgentRunSpawnRequest/AdmissionDecision：委派输入、Parent/Root/Depth、required completion、ProviderResolution、Workspace/Sandbox、共享 WorkOrder Budget Ledger、AgentRun Allocation、最大深度/数量/并发、幂等拒绝、子树 Pause/Cancel、终态汇总和孤儿对账全部闭合；
- 固化 ExecutionGrant `request_contract_id + digest_profile + request_digest`，分别闭合 WorkOrderRequest 与 ConversationTurnRequest；
- 将 ConversationTurnRequest（新 Turn/WorkOrder）与 WorkOrderControlRequest（现有 Runtime 控制）分开；Interrupt-and-enqueue 建立明确后继，Runtime Command 只引用已授权 Control Input；
- 删除并拒绝旧的 Pause/Resume/Cancel/Approval Decision 公共写路由；所有用户控制只有 `POST /v1/work-orders/{work_order_id}/control` + 新 ExecutionGrant 一条权威路径，SystemSafetyControl 只保留 Platform Reduction-only 权限；
- 增加 sender-constrained、幂等的 Business CommercialAuthorizationRevocation 入口和带摘要的撤销收据；收据原子建立同步 deny、WorkSession 撤销与全部活动 WorkOrder/ArtifactOperation/ArtifactIngest 的 CAS/Outbox Cancel intents。WorkOrder 由唯一 Platform Safety Controller 对精确 RuntimeRun 仅追加 SystemSafetyControl；所有路径都与用户 ControlRequest 互斥并禁止扩权；
- 固化 RunManifest 对已消费 ExecutionGrant 的 `request_contract_id + request_digest_profile + request_digest` 绑定，以及实际有界输入/不可变引用、ContextPackage、ArtifactAccessRequirement、初始 Budget/Policy/Permissions 上限、CommercialAuthorization ID/Digest/到期上限、授权续期规则和四类 Gateway Binding；Runtime Start 使用本 Attempt 内部作用域闭合且不越过商业期限的短期 RuntimeAuthorization/ArtifactGrant；
- 固化 Conversation Workspace、Branch WorkspaceRevision Head、Fork 与 CAS 提交；Sandbox Slot 唯一范围是 WorkOrder，不允许并行 Branch 共享可变文件头；
- 发布 ConversationBranch Create/Fork 命令，固定来源 Branch、Message Cut、WorkspaceRevision 与两类 Head CAS；Debug Rerun 和 Parallel Branch 必须先创建新 Branch，再创建新的 Turn/Grant/Resolution/Manifest；
- 为 Chat、Plan、Tool、Approval、Artifact、Background Task、Usage 和终态定义核心 Event Payload，并由 RunManifest 绑定不可变 Registry ID/Version/Digest；
- 固化 AgentRuntimeInvocation Token 对 Tenant、ProviderRevision、Run、Attempt、Fencing、Policy、Budget、Permissions 和请求摘要的绑定；锁定 v1 在执行授权到期后只允许 `safety_control` 做 Status/Event/Cancel/Pause，不允许恢复执行或产生副作用；进入真实 Agent Loop 前按本文件后续检查点发布分离 `observation/reduction_control` 的新 Revision；
- 固化 Service、ExecutionGrant、WorkSession、Plugin、Capability、Artifact、Egress、Runtime 与 Sandbox 的独立闭合 JWS Header Profile；每类唯一 `typ`，Header 与 Claims 同时验证，禁止跨 Profile 接受；
- 固化 Terminal `runtime-gateway/v1` 的 Generation、按 Channel Cursor/Sequence、ACK/Window、Control ID + Digest、重连和 Recording Checkpoint；
- 固化 TechnicalUsage 的 MeterDefinition、归属、Evidence、幂等、更正、连续 UsageReport，以及嵌入完整 Report 的 BusinessSettlementEnvelope/Callback；
- 对启动前失败/取消/准入拒绝发布不可变 NoUsageAttestation；Delivery 与 Settlement 在非空 UsageReport 和 NoUsageAttestation 间显式选择，缺失、未知、Partial 或 Estimated 不得解释为零；
- 使用 Provider Implementation/BuildProvenance/Port Binding，禁止 Runtime 或 Sandbox 被迫伪装成 Plugin；
- ProviderResolution 固化 Resolver/Input/Candidate/Evidence/Decision；Runtime 与 Sandbox Slot 只引用 Resolution；Sandbox 是否存在由 Capability 决定；
- ProviderResolution 显式绑定 Tenant/ClientApplication/ExecutionScope；WorkOrder 与 ArtifactOperation 可解析 Provider，ArtifactIngest 明确不调度 Provider。依赖身份时通过 identity_dependency 绑定 PrincipalContextSnapshot；幂等范围固定为 Tenant + ClientApplication + Operation + Key Digest；
- 发布独立 `capability-provider-v1` 与操作级 Capability Token；请求携带完整执行授权值并绑定 ProviderResolution/Instance/Audience，Invoke `execution` 不越过原 deadline/CommercialAuthorization，后续前驱链 `safety_control` 只做 Status/Cancel/Event 且无 Artifact/副作用权限；禁止以 `plugin_id` 作为 Model/Tool/MCP/Skill/Renderer 等公共执行前提；
- 发布 `McpConnectorBindingV1`、MCP Tool Projection/Negotiation Evidence 和 `mcp-client-tools-v1` Conformance；`stdio`/`streamable_http` 分 Profile 固定协议/能力协商、Server/Destination/Command、身份/Credential、Tool Schema/side-effect/幂等、上限和禁用 Feature，Runtime 不得直连 Server；
- 发布 `SkillPackageManifestV1`、`SkillImportEvidenceV1` 和 `skill-package-import-v1` Conformance；Package 经 Quarantine、路径/大小/摘要/签名/来源/许可证/脚本/权限校验后生成不可变 Artifact/Experience/Provider Revision，Importer 不执行包内脚本；
- Model/Tool Gateway 复用 Capability Port；发布 `artifact-gateway-v1`、`egress-gateway-v1`、ArtifactStagingGrant 与操作 Token，明确 Staging Commit 不能 Finalize ArtifactVersion；
- Capability Status/Event 与 Artifact Read 使用正式 Operation Descriptor；所有 Capability/Artifact Token 绑定 Contract ID、Digest Profile 和摘要，并为 `read_events` 提供正反向 Cursor 证据；
- Egress 使用不可变、Owner-scoped DestinationRevision，Token 绑定 Revision ID/Digest/Class，EffectivePermissions 按 Class 而不是 Destination ID 授权；
- 拆分 Message/Workspace/Active Work CAS；发布 WorkspaceContentManifest，并要求 RuntimeSession 选择 `sandbox_slot_key`；
- CanonicalEvent 固化 Producer/ProviderRevision/SourceStream/SourceEvent/Cursor/Dedupe Key，Metadata 闭合；Platform/标准 Runtime Event 分别绑定所有权匹配的 Platform/Runtime Core Registry 并验证 Payload，持久化 Inbox 唯一责任机器可追踪；
- RuntimeSessionRoute 只保存 Gateway Route 和带摘要的不透明 Provider Route Reference，不得保存或返回原始 Endpoint/Cluster/Region/Cell；
- EffectiveExecutionLimits 全字段必填；写请求声明 encoded-byte 上限并在解析前返回 413；WorkOrder 支持 `accepted -> cancel_requested`，且 `queued`/`waiting`/`paused` 可依据结构化失败证据直接进入 `failed`；
- 固化 PolicyDecision `deny > ask > allow`、Approval 和独立 Sandbox/Gateway Enforcement；
- 发布 Agent Access、Runtime、Sandbox、Runtime Gateway、Capability Provider 和 Artifact/Egress Execution Gateway 的内容寻址 Conformance Suite Manifest；
- 为 Preview/Edit/Conversion 发布统一 ArtifactOperation ExecutionScope；公开请求只接受调用方拥有的身份、Artifact/Capability、CommercialAuthorization/QuotaReservation 与幂等摘要，拒绝 Platform-owned Operation ID、Policy/Budget/Permissions/Gateway/Provider 事实；Platform 分配 Operation 后派生并绑定 ProviderResolution、Policy/Budget/Permissions、Gateway 和唯一 Invocation/Attempt，Projection 不得成为第二执行事实源；
- 为 Runtime Checkpoint 与 Sandbox Snapshot 发布 Platform-owned CompatibilityDecision/Evidence 及机器可读 Restore Profile；Source/Target ProviderRevision、Runtime Revision、Suite/Profile/Digest 不完全匹配时在 Dispatch 前 fail-closed；
- 发布 SecretGrant、同步 Revocation、单操作 Credential Gateway Token/Delivery 和 Credential Conformance Suite；账号交互登录、浏览器 Cookie 接管和私有 Git Credential Flow 不在 Phase 0 可声明能力内；
- 补齐 Artifact Ingest 的 Create/Status/Confirm/Scan/Platform Finalize 状态机；Create 拒绝调用方注入 Policy/Budget/Permissions，Platform 分配 Session 后再派生并持久绑定这些事实，上传成功或 Scanner 结果都不能直接创建 ArtifactVersion；
- 保持 Temporal 为 Phase 0 实现选择，不把第三方私有模型提升为平台领域事实。

验收证据：更新后的 Schema/OpenAPI/状态机、Event Registry、Conformance Suite、正反向夹具和兼容性审查通过本地 Gate。GitHub CI 与仓库准入在实施准备阶段补齐；该证据只关闭契约，不计为产品实现或生产证明。

### 0A.1 到 0B 的决策检查点

1. Wire Closure：Schema/OpenAPI/状态机、正反例和 JCS 摘要同时更新；缺少真实执行值、所有权或上限即停止。
2. Semantic Closure：Contract 的 `semantic-constraints-v1.json` 覆盖关键约束，并将每条约束映射到当前 Validator 及待实现 DDL/Conformance 责任。
3. Local Gate：在 Contract Scripts `.tool-versions` 固定的 CPython 3.14.6、Node 24.18.0 Active LTS/pnpm 11.15.1、Go 1.26.5 上，对显式锁定的 Blueprint/Contract 根运行 `make validate-contract`，九份 OpenAPI 0 Error/0 Warning、Manifest Python/Node 一致、`git diff --check` 全部通过；CPython 3.13 兼容通道另行验证。
4. Implementation Entry Review：只允许把 0A.1 标记为“Contract Gate 通过”；产品实现、集成链路和生产可靠性必须由 Application 分别给出证据。
5. Application 锁定通过 Gate 的 Blueprint/Contract Revision 与 Digest 后进入 0B，先实现 Migration/RLS/Repository/Outbox/Inbox 与空库升级回滚证据，再实现 Native Runtime Core；不得用 Runtime 或框架行为替代领域 Constraint。
6. 0B 组件、语言与升级通道遵循 `docs/51_PHASE0_TECHNOLOGY_SELECTION.md`；其中标记为 Phase 0 候选或 Phase 1 延后的项目不得被误写为已冻结生产选择。

### 0A.2 实施与 Conformance 责任索引

以下精确 ID 被 Contract 的 `semantic-constraints-v1.json` 以 `phase0_implementation_required` 引用。它们是进入 0B 后必须产出真实 DDL、组件测试或集成证据的责任，不会因 Contract Gate 通过而自动完成。

| Check ID | Phase 0 实施证据 |
|---|---|
| `stable_semantic_constraint_implementation_evidence` | 每个稳定语义约束对应 Migration、Repository、Conformance 或集成测试证据 |
| `provider_revision_conformance_evidence` | Suite 结果绑定精确 ProviderRevision、Build、环境与不可变 Evidence |
| `policy_complete_requirement_evaluation` | Policy 输入覆盖完整商业、平台、租户、客户端、场景与 Runtime Profile 规则 |
| `policy_defense_in_depth_enforcement` | Allow 后仍由 Sandbox、Gateway 和 Ledger 独立强制执行 |
| `technical_usage_platform_ownership` | Provider 只能提交 Observation，Platform 分配 Entry 与 Idempotency |
| `technical_usage_evidence_resolution` | Meter、Attempt、Provider 与 Evidence 引用可解析且摘要匹配 |
| `technical_usage_unknown_not_zero` | Partial/Estimated/Unknown 不进入 Final Report 或 NoUsage |
| `unknown_usage_never_zero` | 对账未完成时 Delivery/Settlement 保持 Pending |
| `business_settlement_dedupe_and_evidence_immutability` | Business 按 Envelope ID/Digest 幂等并保留不可变收据 |
| `business_settlement_technical_facts_only` | Platform Envelope 不包含 Price、Currency、Balance 或商业结论 |
| `workspace_manifest_admission` | Workspace Content Manifest 在挂载与 Commit 前验证 |
| `artifact_operation_platform_finalization` | Edit/Conversion 成功结果只引用 Platform 已 Finalize ArtifactVersion |
| `artifact_operation_cancellation_reconciliation` | 已派发 Operation 的 Cancel 经唯一 Invocation 派发并在响应丢失后恢复对账；无取消证据不得记为 cancelled，取消分支不得重派执行 |
| `commercial_authorization_revocation_fanout` | 收据提交同步 deny，并可从 CAS/Outbox intents 恢复 WorkSession、WorkOrder、ArtifactOperation 与 ArtifactIngest 撤销 |
| `compatibility_restore_dispatch_guard` | Missing/Incompatible/Mismatched Decision 在 Provider Dispatch 前拒绝 |
| `compatibility_suite_evidence_authenticity` | Suite/Profile/Run Evidence 的签名、摘要、环境与 Source/Target Revision 可验证 |
| `artifact_ingest_authorization` | Create 绑定认证 Tenant/Client/Principal、CommercialAuthorization 与请求摘要；Session 分配后由 Platform 派生 Policy/Budget/Permissions，Confirm 只能消费该持久绑定 |
| `artifact_ingest_authorized_status` | Status 读取按 Tenant/Principal/Object Ownership 授权且不泄漏存在性 |
| `artifact_ingest_scan_evidence` | Scanner Revision/Profile/Suite 与精确 Content Digest Evidence 可验证 |

## 0B：持久化脊柱与 Native Runtime Core

先实现能支撑首条纵向链的 PostgreSQL Migration、事务 Repository、Outbox/Inbox、Temporal Worker、对象存储引用和 Redis 非权威通知路径。首批只包含 Access/Tenant、Conversation、Message、Branch Create/Fork、WorkspaceRevision、WorkOrder、GrantConsumption、WorkflowRun/RootBinding/AgentRun、Child Spawn/Admission、共享 Budget Ledger/AgentRun Allocation、ProviderResolution、RunManifest、AgentRuntimeCommand/SystemSafetyControl/Fanout Ledger 和 CanonicalEvent；Artifact Ledger、TechnicalUsage、Delivery 与 Recording Metadata 随 0D/0E 引入，不在 0B 一次铺满。

同时实现自研 Native Runtime 的 Core Profile，覆盖 Start、Status、Cursor Event、用户 Cancel、授权到期/Deadline 触发的 Platform Safety Controller + fenced SystemSafetyControl Cancel、最小 Checkpoint/Restart 和无 Sandbox 模式，并完整通过 `runtime-core-v1`。这是产品主 Runtime 的第一阶段；公共 Schema、Provider SDK 和 Workbench Projection 不得按其内部 Agent Loop 定制。

当前 Runtime lifecycle、Provider process、Port/HTTP adapter 和 installed cross-language component 可以在旧 Contract Revision 下形成有界证据。进入动态 Runtime Suite 提升、真实 Agent Loop 或生产 caller/composition 前，必须先执行 `54_AGENT_RUNTIME_EXECUTION_ARCHITECTURE.md` 定义的 Runtime 执行契约演进检查点：关闭 Status/Event 400/429 authority gap，发布分离 `execution/observation/reduction_control` 的 Token Revision，以及 `PromptPolicyBindingV1`、`ContextPackageV2`、`ContextResolverBindingV1`、`EffectiveExecutionLimitsV2` 与受影响 Budget、`ModelStepEvidenceV1`、`AgentRuntimeCheckpointManifestV2`、`RunManifestV3`、`StartAgentRuntimeRunRequestV2`、`AgentRuntimeEventDataV2`、`agent-runtime-core-v2` Registry 和 `runtime-agent-loop-v1`。Application 重新锁定通过 Gate 的 Blueprint/Contract Revision 后才能继续对应实现；不得用已有组件代码反向决定新 Contract。

MCP Tool Client 与 Skill Package Import 同样必须先执行 `56_AGENT_INTEROPERABILITY_PROTOCOLS.md` 和 `13_ARCHITECTURE_ACCEPTANCE.md` 1.2 的 Contract Gate。既有 Plugin Manifest 的 MCP Transport 字段、Provider `skill` kind 和 Catalog `skill_pack` kind 只是可复用底座，不能作为协议已实现或已认证证据。

验收证据：

- Migration 可从空库升级并安全回滚；
- 数据库 Constraint 实现 `26_DATA_MODEL_INVARIANTS.md` 中 Phase 0 使用的不变量；
- WorkOrder 与 Workflow Start Outbox 原子提交；
- SystemSafetyControl、Platform Event、Command/Control Outbox 同事务，旧 Fencing 或系统 Resume/Append/Approval 被拒绝；
- Redis 清空不影响授权、状态、账本和游标正确性；
- Temporal Workflow 可以 Replay；
- Native Runtime Core 可以在 `sandboxes=[]` 下完成一个可恢复 Run，并产生共享 Runtime Event；WorkflowRun 在 Root Admission 前失败时不产生伪造 RootBinding。

## 0C：Business 到 Conversation

实现参考 Business User、Organization、Free/Pro Membership、不可变 EntitlementRevision、幂等 QuotaReservation 和 CommercialAuthorizationSnapshot。完成 WorkSession Exchange，并用新的 ExecutionGrant 提交 Conversation Turn；同时实现 `authorization:revoke` Agent Access 入口、不可变 Revocation Receipt、同步 deny 索引，以及 WorkSession 和全部活动 WorkOrder/ArtifactOperation/ArtifactIngest 的可恢复 fan-out。

Turn 事务必须先按 `request_contract_id` 验证精确请求摘要，再原子完成 Message 追加、Message Sequence、Branch/WorkspaceRevision Head 校验、GrantConsumption、WorkOrder、Workflow Start Outbox 和 CanonicalEvent。平台从 Grant 使用 `turn_id`，并分配内部 `input_message_id`。

验收证据：重复 Conversation/Turn 请求不会创建第二个 Message、WorkOrder、Reservation 或消费记录；Grant 不能跨 Turn、Tenant 或请求摘要重用；Platform 不查询 Business 会员数据库，也不修改商业余额。重复 Revocation Notice 不重复撤销 Session 或创建第二个 SafetyControl，摘要冲突/跨 Tenant/Client/Authorization 被拒绝；收据提交后新授权和 Gateway 副作用 fail-closed，旧连接断开与 Runtime Cancel fan-out 可从数据库恢复。

## 0D：主 Runtime 与 Sandbox

实现以下主链路：

```text
PostgreSQL / Outbox
 -> Temporal WorkOrder Workflow
 -> ProviderResolution / RunManifest
 -> 主 AgentRuntimeProvider
 -> primary-code SandboxProvider
 -> Invocation / SandboxOperation Ledger
 -> CanonicalEvent / Artifact Staging / TechnicalUsage
 -> ArtifactOperation / Artifact Ingest / Artifact Finalize
 -> Delivery / UsageReport 或 NoUsageAttestation / Business Settlement
```

主 Runtime 是自研 Native Runtime，主 Sandbox 是平台 SandboxProvider。DeerFlow、Dify、OpenHands 等项目只提供架构、功能和 UX 参考；公共 API、数据库和 Event 不得出现任何参考项目的私有 Thread、Checkpoint、Sandbox 或 Endpoint 字段。

主链路必须支持 Append-input、Interrupt、Pause/Resume、Approval、Background Task、平台治理的 Child Spawn/Admission 和 Cancel；所有 Command 仅追加，绑定请求摘要并使用 Fencing。Model、Tool、Artifact 和 Egress 必须经过受治理 Gateway。多 Agent 验收必须证明共享预算不会因并行 Child 被重复消费，Root 成功不遗留活动 Child，WorkOrder Cancel 覆盖全部 RuntimeRun，失联 Child 可被对账器发现。

主链路至少通过一个锁定 MCP Client Transport Profile 调用已准入 Tool。协商结果、Tool Projection 和 Step Snapshot 必须绑定同一 Tool Set/Schema Digest；Tool Call 进入 Capability Invocation/Attempt，断连或响应丢失按副作用语义对账，Runtime 无法取得原始 MCP Endpoint/Credential 或绕过 Gateway。

执行顺序固定为：解析 Runtime/Sandbox Provider 并记录 Resolution Evidence；按 Capability 可选创建 Sandbox；固化含 WorkspaceRevision 和实际 Sandbox ID 的 RunManifest；最后 Start Runtime。RunManifest 不得引用尚未创建的 Sandbox，也不得让 Sandbox 复制 ProviderRevision Snapshot。

验收证据：Worker/Adapter 重启可恢复；Provider 响应丢失进入对账；旧 Attempt 和旧 Command 结果被拒绝；Artifact 只有通过 Staging/Ingest Scan 验证后才能由 Platform Finalize；ArtifactOperation 的 Projection 无法绕过唯一 Invocation Ledger；Secret 只能经 Credential Gateway 单次获取且不落入持久介质。

## 0E：Workbench 与 Runtime Recording

实现 Chat、Plan、Timeline、Terminal、Files 和 Artifact 的最小 Workbench。SSE 使用 `work_sequence` 续传；Terminal 通过 Runtime Gateway 建立短期 RuntimeSession。

Runtime Gateway 必须通过 `runtime-gateway-terminal-v1`，验证多 Channel Cursor、ACK Window、Control Digest Conflict 和过期 Gap；至少 Finalize 两个不可变 Terminal Chunk 和一个与 `work_sequence` 对齐的 Recording Manifest。没有实时 Sandbox 时，Workbench 仍能回放 Chat、Plan、Timeline、Tasks、Terminal、Files 和 Artifact。

Browser/Desktop 可以提供受控实时查看，但在 Capture、Consent、Redaction 和容量测试完成前，其录制继续由 Capability Gate 关闭。

验收证据：浏览器集成测试覆盖 Session 过期、SSE 断线续传、Runtime Gateway 重连、只读回放和跨 Tenant 对象拒绝。

## 0F：Experience 与 nexu

至少导入一个 html-anything Template，形成 ExperienceCatalogEntry、不可变 TemplateRevision、源/预览 Artifact 和已认证 ProviderRevision；同时导入一个锁定格式的 Skill Package，形成 Quarantine/Import Evidence、不可变 Artifact/`skill_pack` Experience 和按需 Skill ProviderRevision。Scenario 通过 Catalog 发现选项，WorkOrder、RunManifest 和 Step Snapshot 绑定精确 Revision 摘要。

将 html-to-pptx 或 html-video 实现为 Converter Provider，生成派生 ArtifactVersion。Scenario、Workbench 和 Runtime Adapter 中不得硬编码 Plugin ID。

验收证据：隐藏、撤销、未准入或缺少 Entitlement 的 Revision 无法选择；相同输入固定 Provider/Experience Revision 后可重现相同执行配置和 Artifact 来源链；路径穿越、危险符号链接、超限包、远程引用、无效摘要/签名、安装期脚本和权限扩张均被拒绝，包内容变化产生新 Revision。

## 0G：Agent Runtime Port 可替换性

实现一个与 Native Runtime 代码路径独立的最小 Reference AgentRuntimeProvider，只承担 Contract/Recovery 验证，不适配任何完整第三方 Agent 项目。它不能复用 Native Runtime 的私有 Checkpoint、事件模型或状态存储。

Native Runtime 与 Reference Provider 必须通过 `runtime-core-v1`；Native Runtime 还必须通过 `runtime-general-v1 + governed-v1`。两者使用相同 Start、Command、Status、Cursor Event、Artifact Staging 和 Usage 契约，并可被同一 Workbench、Timeline 和 RuntimeRecording 消费。

验收证据：ProviderResolution 只为新 Run 选择不同 Revision；运行中不自动切换 Provider；不支持的 Capability 明确拒绝；任何稳定 Schema、数据库和 API 都不包含框架私有字段。

## 0H：故障、安全与恢复

至少覆盖：

- ExecutionGrant 超限、重用和跨 Tenant 攻击；
- Runtime 绕过 Model/Tool/Egress Gateway；
- MCP 版本无交集、能力谎报、Tool Schema/列表漂移、宿主命令/环境泄漏、SSRF/DNS rebinding、重复/丢失响应与未知副作用重试；
- Skill Package 路径穿越、符号链接、重复路径、解压炸弹、远程下载、恶意脚本、Prompt injection、权限扩张和 Revision 漂移；
- Provider 响应丢失、重复响应、旧 Fencing Token 和非幂等重试；
- Runtime/Recording 中的 Secret、Token 和未加密字节泄漏；
- SecretGrant 过期/撤销/重放、Credential Gateway Audit 不可用、跨 Workload Token 重放和持久化扫描；
- Checkpoint/Snapshot 缺失、失败、Source/Target/Profile 不匹配的 CompatibilityDecision；
- NoUsage 虚假证明、未知用量被解释为零，以及 Settlement Release 重放；
- API、Worker、Provider Controller 和 Sandbox Node 故障；
- Redis 通知丢失、Temporal Replay、跨 Pod SSE 续传；
- NetworkPolicy、RBAC、Pod Security、Artifact 并发提交；
- PostgreSQL、Temporal 和 Object Storage 的最小备份恢复演练；
- 基础容量、队列背压和 Runtime/Sandbox 并发上限。

所有测试必须输出可复现命令、环境、运行日志、指标和结论。失败或未运行项不能记录为通过。

## 完成定义

| 结论 | Phase 0 要求 |
|---|---|
| Contract Gate 通过 | Contract Scripts 对锁定 Contract Revision 完成 Schema、语义、状态机、JCS、OpenAPI、Manifest 和候选兼容性检查；不包含 GitHub CI/仓库准入 |
| 0B 实现完成 | 持久化脊柱、Native Runtime Core、数据库事务、Replay 与 `runtime-core-v1` 有真实证据 |
| 0C-0G 集成完成 | Business 纵向链、主 Runtime/Sandbox、MCP Tool Client、Skill Import/Experience、Workbench/Recording 与 Reference Probe 可以重复部署与运行 |
| 0H 最小可靠性证据 | 故障、安全、隔离、容量和恢复测试有可复现报告 |
| 正式冻结 | 独立完成消费者兼容性、仓库供应链、公共 CI、冻结基线和人工批准 |
| 生产就绪 | 不由 Phase 0 自动授予，仍需独立容量、SLO、安全和生产恢复批准 |

## 不提前实现

- 用户上传的任意 Plugin、完整 Marketplace 或收入分成；
- MCP Server/Resource/Prompt/反向请求、A2A、ACP 或 AG-UI 产品 Adapter；
- ACP 平台核心、本地 JSONL/SQLite Session 事实源或 Hook 安全边界；
- 任意远程 JavaScript、完整 Office 编辑器或复杂 UI Extension；
- 持久 Evaluation/Rubric 领域模型；
- 自研 sandbox-runtime 或跨 Provider Process/Checkpoint 恢复；
- 智能成本路由、多区域双活和大规模 Provider 管理界面。
