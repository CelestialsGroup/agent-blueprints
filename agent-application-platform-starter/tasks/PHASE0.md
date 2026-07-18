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
- 固化 Conversation Workspace、Branch WorkspaceRevision Head、Fork 与 CAS 提交；Sandbox Slot 唯一范围是 WorkOrder，不允许并行 Branch 共享可变文件头；
- 为 Chat、Plan、Tool、Approval、Artifact、Background Task、Usage 和终态定义核心 Event Payload，并由 RunManifest 绑定不可变 Registry ID/Version/Digest；
- 固化 AgentRuntimeInvocation Token 对 Tenant、ProviderRevision、Run、Attempt、Fencing、Policy、Budget、Permissions 和请求摘要的绑定；
- 固化 Terminal `runtime-gateway/v1` 的 Generation、按 Channel Cursor/Sequence、ACK/Window、Control ID + Digest、重连和 Recording Checkpoint；
- 固化 TechnicalUsage 的 MeterDefinition、归属、Evidence、幂等、更正、连续 UsageReport，以及嵌入完整 Report 的 BusinessSettlementEnvelope/Callback；
- 使用 Provider Implementation/BuildProvenance/Port Binding，禁止 Runtime 或 Sandbox 被迫伪装成 Plugin；
- ProviderResolution 固化 Resolver/Input/Candidate/Evidence/Decision；Runtime 与 Sandbox Slot 只引用 Resolution；Sandbox 是否存在由 Capability 决定；
- 固化 PolicyDecision `deny > ask > allow`、Approval 和独立 Sandbox/Gateway Enforcement；
- 发布 Runtime、Sandbox、Runtime Gateway 和 Capability Provider 的内容寻址 Conformance Suite Manifest；
- 保持 Temporal 为 Phase 0 实现选择，不把第三方私有模型提升为平台领域事实。

验收证据：更新后的 Schema/OpenAPI/状态机、Event Registry、Conformance Suite、正反向夹具和兼容性审查通过本地 Gate。GitHub CI 与仓库准入在实施准备阶段补齐；该证据只关闭契约，不计为产品实现或生产证明。

## 0B：持久化脊柱与 Native Runtime Probe

先实现能支撑首条纵向链的 PostgreSQL Migration、事务 Repository、Outbox/Inbox、Temporal Worker、对象存储引用和 Redis 非权威通知路径。首批只包含 Access/Tenant、Conversation、Message、Branch、WorkspaceRevision、WorkOrder、GrantConsumption、WorkflowRun/AgentRun、ProviderResolution、RunManifest 和 CanonicalEvent；Artifact Ledger、TechnicalUsage、Delivery 与 Recording Metadata 随 0D/0E 引入，不在 0B 一次铺满。

同时实现一个独立进程的 Native Minimal AgentRuntimeProvider Contract Probe，覆盖 Start、Status、Cursor Event、Cancel、最小 Checkpoint/Restart 和无 Sandbox 模式，并完整通过 `runtime-core-v1`。它是反框架泄漏探针，不是生产主 Runtime；公共 Schema、Adapter SDK 和 Workbench Projection 不得先按 DeerFlow 定制。

验收证据：

- Migration 可从空库升级并安全回滚；
- 数据库 Constraint 实现 `26_DATA_MODEL_INVARIANTS.md` 中 Phase 0 使用的不变量；
- WorkOrder 与 Workflow Start Outbox 原子提交；
- Redis 清空不影响授权、状态、账本和游标正确性；
- Temporal Workflow 可以 Replay；
- Native Probe 可以在 `sandboxes=[]` 下完成一个可恢复 Run，并产生共享 Runtime Event。

## 0C：Business 到 Conversation

实现参考 Business User、Organization、Free/Pro Membership、不可变 EntitlementRevision、幂等 QuotaReservation 和 CommercialAuthorizationSnapshot。完成 WorkSession Exchange，并用新的 ExecutionGrant 提交 Conversation Turn。

Turn 事务必须先按 `request_contract_id` 验证精确请求摘要，再原子完成 Message 追加、Message Sequence、Branch/WorkspaceRevision Head 校验、GrantConsumption、WorkOrder、Workflow Start Outbox 和 CanonicalEvent。平台从 Grant 使用 `turn_id`，并分配内部 `input_message_id`。

验收证据：重复 Conversation/Turn 请求不会创建第二个 Message、WorkOrder、Reservation 或消费记录；Grant 不能跨 Turn、Tenant 或请求摘要重用；Platform 不查询 Business 会员数据库，也不修改商业余额。

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
