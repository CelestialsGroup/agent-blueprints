# Phase 0 - v0.9.0 产品纵向链路

Phase 0 实现一条真实、可恢复的 Manus-like Conversation 链路。目录骨架、生成代码、Schema 通过或单次 Happy Path 都不算完成。所有阶段按依赖顺序推进；未完成前置阶段时，不并行扩展产品范围。

```text
0A 最小契约闭合
 -> 0B 持久化脊柱与 Native Runtime Probe
 -> 0C Business 到 Conversation
 -> 0D 主 Runtime 与 Sandbox
 -> 0E Workbench 与 Recording
 -> 0F nexu Experience
 -> 0G 第二 Runtime
 -> 0H 故障、安全与恢复证据
```

## 0A：最小契约闭合

开始产品实现前，收敛 Phase 0 实际需要的公共模型：

- 固化 Tenant-qualified `WorkOrder 1 -> 1 WorkflowRun -> 1 Root AgentRun + N Sub-agent AgentRun`，且一个 AgentRun 只绑定一个 RunManifest/AgentRuntimeRun；RunManifest Runtime 只引用一个 ProviderResolution；
- 固化 ExecutionGrant `request_contract_id + digest_profile + request_digest`，分别闭合 WorkOrderRequest 与 ConversationTurnRequest；
- 将 ConversationTurnRequest（新 Turn/WorkOrder）与 WorkOrderControlRequest（现有 Runtime 控制）分开；Interrupt-and-enqueue 建立明确后继，Runtime Command 只引用已授权 Control Input；
- 增加 sender-constrained、幂等的 Business CommercialAuthorizationRevocation 入口和唯一 Platform Safety Controller；在商业授权到期/撤销、Deadline/预算触发或紧急停机时，仅追加 SystemSafetyControl 并只允许对精确 Tenant/WorkOrder/RuntimeRun 发出 Pause/Cancel；与用户 ControlRequest 授权互斥，禁止 Resume、Append、Interrupt、Approval、Checkpoint 和新副作用；
- 固化 RunManifest 对已消费 ExecutionGrant 的 `request_contract_id + request_digest_profile + request_digest` 绑定，以及实际有界输入/不可变引用、ContextPackage、ArtifactAccessRequirement、初始 Budget/Policy/Permissions 上限、CommercialAuthorization ID/Digest/到期上限、授权续期规则和四类 Gateway Binding；Runtime Start 使用本 Attempt 内部作用域闭合且不越过商业期限的短期 RuntimeAuthorization/ArtifactGrant；
- 固化 Conversation Workspace、Branch WorkspaceRevision Head、Fork 与 CAS 提交；Sandbox Slot 唯一范围是 WorkOrder，不允许并行 Branch 共享可变文件头；
- 为 Chat、Plan、Tool、Approval、Artifact、Background Task、Usage 和终态定义核心 Event Payload，并由 RunManifest 绑定不可变 Registry ID/Version/Digest；
- 固化 AgentRuntimeInvocation Token 对 Tenant、ProviderRevision、Run、Attempt、Fencing、Policy、Budget、Permissions 和请求摘要的绑定；执行授权到期后只允许 `safety_control` 做 Status/Event/Cancel/Pause，不允许恢复执行或产生副作用；
- 固化 Service、ExecutionGrant、WorkSession、Plugin、Capability、Artifact、Egress、Runtime 与 Sandbox 的独立闭合 JWS Header Profile；每类唯一 `typ`，Header 与 Claims 同时验证，禁止跨 Profile 接受；
- 固化 Terminal `runtime-gateway/v1` 的 Generation、按 Channel Cursor/Sequence、ACK/Window、Control ID + Digest、重连和 Recording Checkpoint；
- 固化 TechnicalUsage 的 MeterDefinition、归属、Evidence、幂等、更正、连续 UsageReport，以及嵌入完整 Report 的 BusinessSettlementEnvelope/Callback；
- 使用 Provider Implementation/BuildProvenance/Port Binding，禁止 Runtime 或 Sandbox 被迫伪装成 Plugin；
- ProviderResolution 固化 Resolver/Input/Candidate/Evidence/Decision；Runtime 与 Sandbox Slot 只引用 Resolution；Sandbox 是否存在由 Capability 决定；
- ProviderResolution 显式绑定 Tenant/ClientApplication/WorkOrder，并通过 identity_dependency 绑定 PrincipalContextSnapshot；幂等范围固定为 Tenant + ClientApplication + Operation + Key Digest；
- 发布独立 `capability-provider-v1` 与操作级 Capability Token；请求携带完整执行授权值并绑定 ProviderResolution/Instance/Audience，Invoke `execution` 不越过原 deadline/CommercialAuthorization，后续前驱链 `safety_control` 只做 Status/Cancel/Event 且无 Artifact/副作用权限；禁止以 `plugin_id` 作为 Model/Tool/MCP/Skill/Renderer 等公共执行前提；
- Model/Tool Gateway 复用 Capability Port；发布 `artifact-gateway-v1`、`egress-gateway-v1`、ArtifactStagingGrant 与操作 Token，明确 Staging Commit 不能 Finalize ArtifactVersion；
- Capability Status/Event 与 Artifact Read 使用正式 Operation Descriptor；所有 Capability/Artifact Token 绑定 Contract ID、Digest Profile 和摘要，并为 `read_events` 提供正反向 Cursor 证据；
- Egress 使用不可变、Owner-scoped DestinationRevision，Token 绑定 Revision ID/Digest/Class，EffectivePermissions 按 Class 而不是 Destination ID 授权；
- 拆分 Message/Workspace/Active Work CAS；发布 WorkspaceContentManifest，并要求 RuntimeSession 选择 `sandbox_slot_key`；
- CanonicalEvent 固化 Producer/ProviderRevision/SourceStream/SourceEvent/Cursor/Dedupe Key，Metadata 闭合；Platform/标准 Runtime Event 分别绑定所有权匹配的 Platform/Runtime Core Registry 并验证 Payload，持久化 Inbox 唯一责任机器可追踪；
- RuntimeSessionRoute 只保存 Gateway Route 和带摘要的不透明 Provider Route Reference，不得保存或返回原始 Endpoint/Cluster/Region/Cell；
- EffectiveExecutionLimits 全字段必填；写请求声明 encoded-byte 上限并在解析前返回 413；WorkOrder 支持 `accepted -> cancel_requested`，且 `queued`/`waiting`/`paused` 可依据结构化失败证据直接进入 `failed`；
- 固化 PolicyDecision `deny > ask > allow`、Approval 和独立 Sandbox/Gateway Enforcement；
- 发布 Agent Access、Runtime、Sandbox、Runtime Gateway、Capability Provider 和 Artifact/Egress Execution Gateway 的内容寻址 Conformance Suite Manifest；
- 保持 Temporal 为 Phase 0 实现选择，不把第三方私有模型提升为平台领域事实。

验收证据：更新后的 Schema/OpenAPI/状态机、Event Registry、Conformance Suite、正反向夹具和兼容性审查通过本地 Gate。GitHub CI 与仓库准入在实施准备阶段补齐；该证据只关闭契约，不计为产品实现或生产证明。

### 0A.1 到 0B 的决策检查点

1. Wire Closure：Schema/OpenAPI/状态机、正反例和 JCS 摘要同时更新；缺少真实执行值、所有权或上限即停止。
2. Semantic Closure：`semantic-constraints-v1.json` 覆盖关键约束，并将每条约束映射到当前 Validator 及待实现 DDL/Conformance 责任。
3. Local Gate：在 `.tool-versions` 固定的 CPython 3.14.6、Node 24.18.0 Active LTS/pnpm 11.15.1、Go 1.26.5 上运行 `./scripts/bootstrap_contracts.sh && make validate-architecture`，八份 OpenAPI 0 Error/0 Warning、Manifest Python/Node 一致、`git diff --check` 全部通过；CPython 3.13 兼容通道另行验证。
4. Implementation Entry Review：只允许把 0A.1 标记为“架构/契约验证通过”；产品实现、集成链路和生产可靠性仍为未完成。
5. 进入 0B 后先实现 Migration/RLS/Repository/Outbox/Inbox 与空库升级回滚证据，再实现 Native Runtime Probe；不得用框架行为替代领域 Constraint。
6. 0B 组件、语言与升级通道遵循 `docs/51_PHASE0_TECHNOLOGY_SELECTION.md`；其中标记为 Phase 0 候选或 Phase 1 延后的项目不得被误写为已冻结生产选择。

## 0B：持久化脊柱与 Native Runtime Probe

先实现能支撑首条纵向链的 PostgreSQL Migration、事务 Repository、Outbox/Inbox、Temporal Worker、对象存储引用和 Redis 非权威通知路径。首批只包含 Access/Tenant、Conversation、Message、Branch、WorkspaceRevision、WorkOrder、GrantConsumption、WorkflowRun/AgentRun、ProviderResolution、RunManifest、AgentRuntimeCommand/SystemSafetyControl Ledger 和 CanonicalEvent；Artifact Ledger、TechnicalUsage、Delivery 与 Recording Metadata 随 0D/0E 引入，不在 0B 一次铺满。

同时实现一个独立进程的 Native Minimal AgentRuntimeProvider Contract Probe，覆盖 Start、Status、Cursor Event、用户 Cancel、授权到期/Deadline 触发的 Platform Safety Controller + fenced SystemSafetyControl Cancel、最小 Checkpoint/Restart 和无 Sandbox 模式，并完整通过 `runtime-core-v1`。它是反框架泄漏探针，不是生产主 Runtime；公共 Schema、Adapter SDK 和 Workbench Projection 不得先按 DeerFlow 定制。

验收证据：

- Migration 可从空库升级并安全回滚；
- 数据库 Constraint 实现 `26_DATA_MODEL_INVARIANTS.md` 中 Phase 0 使用的不变量；
- WorkOrder 与 Workflow Start Outbox 原子提交；
- SystemSafetyControl、Platform Event、Command/Control Outbox 同事务，旧 Fencing 或系统 Resume/Append/Approval 被拒绝；
- Redis 清空不影响授权、状态、账本和游标正确性；
- Temporal Workflow 可以 Replay；
- Native Probe 可以在 `sandboxes=[]` 下完成一个可恢复 Run，并产生共享 Runtime Event。

## 0C：Business 到 Conversation

实现参考 Business User、Organization、Free/Pro Membership、不可变 EntitlementRevision、幂等 QuotaReservation 和 CommercialAuthorizationSnapshot。完成 WorkSession Exchange，并用新的 ExecutionGrant 提交 Conversation Turn；同时实现 `authorization:revoke` Agent Access 入口、不可变 Revocation Receipt、同步 deny 索引以及 WorkSession/活动 WorkOrder 可恢复 fan-out。

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
 -> Artifact Finalize / Delivery / Business Settlement
```

主 Runtime 可以使用 DeerFlow Adapter，主 Sandbox 可以包装 DeerFlow Built-in Sandbox，但公共 API、数据库和 Event 不得出现 DeerFlow 私有 Thread、Checkpoint、Sandbox 或 Endpoint 字段。

主链路必须支持 Append-input、Interrupt、Pause/Resume、Approval、Background Task/Sub-agent Projection 和 Cancel；所有 Command 仅追加，绑定请求摘要并使用 Fencing。Model、Tool、Artifact 和 Egress 必须经过受治理 Gateway。

执行顺序固定为：解析 Runtime/Sandbox Provider 并记录 Resolution Evidence；按 Capability 可选创建 Sandbox；固化含 WorkspaceRevision 和实际 Sandbox ID 的 RunManifest；最后 Start Runtime。RunManifest 不得引用尚未创建的 Sandbox，也不得让 Sandbox 复制 ProviderRevision Snapshot。

验收证据：Worker/Adapter 重启可恢复；Provider 响应丢失进入对账；旧 Attempt 和旧 Command 结果被拒绝；Artifact 只有通过 Staging 验证后才能 Finalize。

## 0E：Workbench 与 Runtime Recording

实现 Chat、Plan、Timeline、Terminal、Files 和 Artifact 的最小 Workbench。SSE 使用 `work_sequence` 续传；Terminal 通过 Runtime Gateway 建立短期 RuntimeSession。

Runtime Gateway 必须通过 `runtime-gateway-terminal-v1`，验证多 Channel Cursor、ACK Window、Control Digest Conflict 和过期 Gap；至少 Finalize 两个不可变 Terminal Chunk 和一个与 `work_sequence` 对齐的 Recording Manifest。没有实时 Sandbox 时，Workbench 仍能回放 Chat、Plan、Timeline、Tasks、Terminal、Files 和 Artifact。

Browser/Desktop 可以提供受控实时查看，但在 Capture、Consent、Redaction 和容量测试完成前，其录制继续由 Capability Gate 关闭。

验收证据：浏览器集成测试覆盖 Session 过期、SSE 断线续传、Runtime Gateway 重连、只读回放和跨 Tenant 对象拒绝。

## 0F：Experience 与 nexu

至少导入一个 html-anything Template，形成 ExperienceCatalogEntry、不可变 TemplateRevision、源/预览 Artifact 和已认证 ProviderRevision。Scenario 通过 Catalog 发现选项，WorkOrder 和 RunManifest 绑定精确 Revision 摘要。

将 html-to-pptx 或 html-video 实现为 Converter Provider，生成派生 ArtifactVersion。Scenario、Workbench 和 Runtime Adapter 中不得硬编码 Plugin ID。

验收证据：隐藏、撤销、未准入或缺少 Entitlement 的 Revision 无法选择；相同输入固定 Provider/Experience Revision 后可重现相同执行配置和 Artifact 来源链。

## 0G：Agent Runtime 可替换性

将 0B 的 Native Minimal Probe 提升为可重复部署的第二 AgentRuntimeProvider Adapter，或替换为 OpenAI Agents SDK Adapter；选择不构成平台依赖。由于协议探针已在主 Runtime 前运行，本阶段验证的是完整部署、恢复和 Workbench 消费，而不是第一次发现框架泄漏。

两个 Adapter 必须通过 `runtime-core-v1`；主 Runtime 还必须通过 `runtime-general-v1 + governed-v1`。两者使用相同 Start、Command、Status、Cursor Event、Artifact Staging 和 Usage 契约，并可被同一 Workbench、Timeline 和 RuntimeRecording 消费。

验收证据：ProviderResolution 只为新 Run 选择不同 Revision；运行中不自动切换 Provider；不支持的 Capability 明确拒绝；任何稳定 Schema、数据库和 API 都不包含框架私有字段。

## 0H：故障、安全与恢复

至少覆盖：

- ExecutionGrant 超限、重用和跨 Tenant 攻击；
- Runtime 绕过 Model/Tool/Egress Gateway；
- Provider 响应丢失、重复响应、旧 Fencing Token 和非幂等重试；
- Runtime/Recording 中的 Secret、Token 和未加密字节泄漏；
- API、Worker、Provider Controller 和 Sandbox Node 故障；
- Redis 通知丢失、Temporal Replay、跨 Pod SSE 续传；
- NetworkPolicy、RBAC、Pod Security、Artifact 并发提交；
- PostgreSQL、Temporal 和 Object Storage 的最小备份恢复演练；
- 基础容量、队列背压和 Runtime/Sandbox 并发上限。

所有测试必须输出可复现命令、环境、运行日志、指标和结论。失败或未运行项不能记录为通过。

## 完成定义

| 结论 | Phase 0 要求 |
|---|---|
| 本地架构契约通过 | `make validate-architecture` 的 Schema、语义、状态机、JCS、OpenAPI 和候选兼容性检查通过；不包含 GitHub CI/仓库准入 |
| 实现完成 | 0B-0G 的真实组件和纵向链路可以重复部署与运行 |
| 最小可靠性证据 | 0H 的故障、安全和恢复测试有可复现报告 |
| 正式冻结 | 独立完成消费者兼容性、仓库供应链、公共 CI、冻结基线和人工批准 |
| 生产就绪 | 不由 Phase 0 自动授予，仍需独立容量、SLO、安全和生产恢复批准 |

## 不提前实现

- 用户上传的任意 Plugin、完整 Marketplace 或收入分成；
- ACP 平台核心、本地 JSONL/SQLite Session 事实源或 Hook 安全边界；
- 任意远程 JavaScript、完整 Office 编辑器或复杂 UI Extension；
- 持久 Evaluation/Rubric 领域模型；
- 自研 sandbox-runtime 或跨 Provider Process/Checkpoint 恢复；
- 智能成本路由、多区域双活和大规模 Provider 管理界面。
