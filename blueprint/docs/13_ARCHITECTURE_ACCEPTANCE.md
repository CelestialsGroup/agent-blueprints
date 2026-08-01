# 架构与实施验收层级

本文件定义验收条件，不记录某次运行状态。契约通过、0B 实现、0C-0G 集成、0H 可靠性、正式冻结和生产批准是六种独立结论，不得互相替代。实际状态分别查看 Blueprint 验证报告、实现仓库证据和生产治理记录。

## 1. 本地架构候选 Gate

进入 Phase 0 实现前必须满足：

- Contract 工具链可在支持的 Python/Node/Go 版本完成 Bootstrap；
- Contract Scripts 对锁定 Contract Revision 的 `make validate-contract` 通过，9 个 OpenAPI 为 0 错误/0 警告，Bundle 可重复；
- ExecutionGrant 精确绑定 WorkOrderRequest/ConversationTurnRequest/WorkOrderControlRequest Contract ID、Digest Profile 和请求摘要；
- ConversationBranch Create/Fork 命令绑定来源 Message Cut、WorkspaceRevision 与 Head CAS，原子产生新 Branch/初始 Revision/核心事件；并行 Branch 不共享可变文件头；
- Runtime 与 Sandbox Slot 只引用带 Resolver/Input/Candidate/Evidence/Decision 的 ProviderResolution；
- Resolution 显式绑定 Tenant/ClientApplication/WorkOrder 或 ArtifactOperation ExecutionScope；ArtifactIngest 不调度 Provider。依赖身份时通过 identity_dependency 绑定 PrincipalContextSnapshot；
- RunManifest 携带实际输入、ContextPackage、ArtifactAccessRequirement、初始 Budget/Policy/Permissions 上限、商业授权 ID/Digest/到期上限、续期规则和四类 Gateway Binding；Runtime Start 携带本 Attempt 的等价/缩权 RuntimeAuthorization/ArtifactGrant，并拒绝内部作用域不闭合或越过商业/ArtifactGrant 时间窗的授权；
- Conversation Turn 与 WorkOrder Control 分离，三个 CAS 所有权域分离，WorkOrder 可从 accepted 直接请求取消；
- 通用 Capability Provider Port/Token 不要求 `plugin_id`；请求携带完整执行授权值并绑定 ProviderResolution/Instance/Audience，操作级 Token 以正式 Contract/Profile/Digest 绑定 Invoke/Status/Cancel/Event；Invoke `execution` 不越过原 deadline/CommercialAuthorization，后续前驱链 `safety_control` 只做 Status/Cancel/Event 且无 Artifact/副作用权限；`read_events` 有正反向游标证据；
- 锁定 Runtime v1 的 Start/Command/Status/Event 和兼容 Plugin 的 Invoke/Status/Cancel/Event 也以单操作 Contract/Profile/Digest 绑定请求或规范化读描述符；路径、默认查询值和 Cursor 均不可脱离摘要替换；Plugin Invoke `execution` 受 Deadline/Artifact 窗口限制，到期后 `safety_control` 只能 Status/Cancel/Event；
- 锁定 Runtime v1 的 `execution` Token 不越过 RuntimeAuthorization/命令 Deadline；到期后的 `safety_control` 只能 Status/Event/Cancel/Pause，不能恢复执行或产生新副作用；新 Runtime Authority Revision 由 1.1 节单独验收；
- 用户 Runtime 控制继续绑定 WorkOrderControlRequest + ExecutionGrant；Business 撤销通过 sender-constrained、幂等的 CommercialAuthorizationRevocation 接口进入，Platform 不改写商业事实；授权到期/撤销和紧急止损使用唯一 Safety Controller 签发、仅追加的 SystemSafetyControl。两种 Command 授权来源互斥，系统来源与 Token 必须绑定相同 Tenant/WorkOrder/RuntimeRun/action/digest/触发证据，且不能授权 Resume、Append、Interrupt、Approval 或 Checkpoint；
- CommercialAuthorization 撤销收据带 JCS 摘要与同步 deny 生效点，并精确枚举 WorkSession、活动 WorkOrder、ArtifactOperation、ArtifactIngest 的 CAS/Outbox intents；fan-out 可恢复且未完成不得宣称撤销闭合；
- Service/Grant/Session 与六类执行 Token 均有用途专属的闭合 JWS Header Schema，唯一 `typ`、Algorithm/Key allowlist 与 Claims Profile 不得交叉接受；
- Runtime/Capability/Sandbox/Artifact/Egress 执行 Token 的 `nbf` 不早于所绑定 Authorization/Policy/Grant 生效，`exp` 不越过对应执行期限；
- Model/Tool 复用 Capability Port；Artifact/Egress 拥有独立 OpenAPI、操作 Token、Contract ID/Profile/Digest 和 Conformance Profile，ArtifactStagingGrant 不授予 Finalize；Egress 绑定不可变 Owner-scoped DestinationRevision 并按 destination_class 授权；
- Preview/Edit/Conversion 公开请求拒绝 Platform-owned Operation ID、Policy/Budget/Permissions/Gateway/Provider 事实；Platform 分配 ArtifactOperation 后派生 admission facts，并复用 Capability Invocation/Attempt + Artifact Gateway + TechnicalUsage/Settlement。启动前终态不伪造 Resolution/Invocation，Projection 不能成为第二执行事实源；
- Delivery/Settlement 对终态在非空 UsageReport 与 NoUsageAttestation 间显式选择；CompatibilityDecision/Evidence 与 SecretGrant/Credential Gateway 均有 fail-closed 正反例；ArtifactIngest Create 拒绝调用方 Policy/Budget/Permissions，Session 分配后由 Platform 派生，Status/Confirm/Scan/Finalize 由 Platform 最终事务闭合；
- WorkspaceContentManifest、Sandbox Slot 选择、Event 来源 Inbox 去重、闭合且有界的 Event/Conversation/Work Metadata、诊断/审批 Details 和所有 JSON 写接口的 HTTP encoded-body 上限均有可执行契约；
- Platform 与标准 Runtime CanonicalEvent 分别绑定所有权匹配的 Platform/Runtime Core Registry Revision，并按 `(type,data_version)` 验证 Payload；Provider 私有 Registry 不能进入核心流；
- Contract 的 `semantic-constraints-v1.json` 覆盖全部关键语义；每个 Contract Gate Check ID 在当前运行中真实执行，并与待实现 DDL/Conformance 责任明确分离；
- RunManifest 支持 Capability 驱动的零或多个 Sandbox，主 Slot 条件闭合；
- RuntimeSessionRoute 只包含 Gateway 与不透明 Provider Route Reference，不包含原始 Endpoint、Cluster、Region 或 Cell；
- RunManifest Location 只保存 Placement Mode、可空逻辑 Region、Policy Reference 和 Decision Digest；ProviderHealth、SandboxStatus 与 SandboxSpec 不暴露 Cluster/Cell/Node/Runtime 身份，远程 Provider 不被强制伪造本地拓扑；
- Sandbox Capability 发现只接受已准入控制面 mTLS；其余 14 个 Sandbox 操作全部以单操作 Token 绑定正式 Contract ID、Digest Profile 和请求体或规范化读描述符，路径/游标替换有正反向证据；
- `51_PHASE0_TECHNOLOGY_SELECTION.md` 已给出 0B 首选/备选/不选、语言边界、版本策略、许可证复核、Canary 和 Rollback；
- 状态机、JCS、Schema、语义负例与 Python/Node 契约清单一致。

该 Gate 不包含 GitHub CI、仓库供应链准入或冻结基线；通过只表示候选架构可以进入实施。

### 1.1 Runtime 执行契约演进 Gate

已有 Runtime lifecycle/component evidence 可以作为历史实现证据保留，但在真实 Agent Loop、动态 Suite 提升或生产 Runtime caller 接线前，还必须完成：

- Status/Event HTTP 400/429 的权威响应矩阵以新的不可变 AgentRuntimeProvider v1 patch Contract Revision 闭合；
- Runtime Token 新 Revision 将 `execution/observation/reduction_control` 分离：用户 Pause/Cancel 仍走绑定新 WorkOrderControlRequest/ExecutionGrant 的 `execution`，过期读取绑定 ReconciliationCase，只有平台自动 Pause/Cancel 使用绑定 SystemSafetyControl 的 `reduction_control`；
- `PromptPolicyBindingV1` 固化 Policy/Builder/Serializer Revision 与摘要、指令来源 Revision、角色优先级和内容保存策略，但不保存明文 Prompt；
- `ContextPackageV2` 固化 Builder/Policy、选择/遗漏、顺序、预算、信任和 Assembly Digest；独立 `ContextResolverBindingV1` 固化每类引用使用的受治理 Port、Contract、Audience、Route、Digest Profile 和授权要求；
- `EffectiveExecutionLimitsV2` 及受影响 Budget Contract 明确单请求、AgentRun 累计和 WorkOrder 共享作用域；
- `ModelStepEvidenceV1`、`AgentRuntimeCheckpointManifestV2`、`RunManifestV3`、`StartAgentRuntimeRunRequestV2`、`AgentRuntimeEventDataV2` 和 `agent-runtime-core-v2` Registry 发布相容的新版本；
- 新 `runtime-agent-loop-v1` Conformance 覆盖 Context trust/确定性、Prompt injection 不扩权、Step Snapshot、Tool exposure/dispatch、预算、Compaction、Graph revision/有界并行/确定性恢复、Checkpoint/Resume 和未知副作用禁止重发；
- Schema/OpenAPI、semantic constraints、状态机、Registry、Fixture、Example、Manifest、Suite、兼容性报告和消费者双版本测试同步通过 Gate；
- Application 重新锁定新 Blueprint/Contract Revision 后才开始对应实现。

只修改 Blueprint 或叙述性 Contract 文档不算该 Gate 通过；旧 Run 和旧 ProviderRevision 继续使用其原 Contract/Profile，不原地迁移。

### 1.2 Agent 互操作契约 Gate

在宣称 Phase 0 支持 MCP Tool Client 或 Agent Skills/Skill Package 前，必须完成：

- `McpConnectorBindingV1` 固化协议 Revision、Client Feature Profile、`stdio`/`streamable_http` Transport Profile、允许协商版本、Server/Destination/Command、身份/Credential、Tool allowlist、上限、Session/通知策略和 Binding Digest；
- MCP Tool Projection 将 Server/Tool identity、input/output Schema Digest、side-effect、幂等、取消、进度、Artifact 和风险语义映射到 CapabilityDefinition；未知语义采用保守默认并 fail-closed；
- 每次 MCP Tool Call 进入 Capability Invocation/Attempt、Fencing、Budget、Approval、Artifact Staging 和结果对账；Runtime 无直连路径，SDK 不自动重试未知副作用；
- MCP Negotiation Evidence 证明版本/能力交集、Server identity、Tool Set/Schema Digest 和拒绝/降级原因；动态 Tool 变化只能产生新 Step Snapshot；
- `stdio` 与 `streamable_http` 分 Profile 覆盖宿主命令/环境泄漏、Credential、TLS、Redirect、SSRF/DNS rebinding、超限、断连、重复/乱序、取消和旧 Fencing；
- `SkillPackageManifestV1` 与 `SkillImportEvidenceV1` 固化 Format/Package/File Digest、Source、Publisher、License/Notice、Signature、Capability/Dependency、权限请求、Importer/Scanner Revision、逐项结论和输出 Artifact/Experience/Provider Revision；
- Skill Import 的正反向 Fixture 覆盖路径穿越、危险符号链接、重复规范化路径、特殊文件、超限/解压炸弹、远程引用、摘要/签名、脚本隔离、权限扩张、Revision 漂移和许可证证据；
- `mcp-client-tools-v1` 与 `skill-package-import-v1` Suite、Schema、semantic constraints、Fixture、Example、Manifest、兼容性报告和消费者双版本测试同步通过完整 Contract Gate；
- Application 重新锁定新 Blueprint/Contract Revision 后再实现并分别形成 `implemented`、`certified`、`enabled` Evidence。

MCP Server、MCP Resource/Prompt/反向请求、A2A、ACP 和 AG-UI 不因本 Gate 通过而获得支持声明。每一项必须按 `56_AGENT_INTEROPERABILITY_PROTOCOLS.md` 发布自己的 Binding/Mapping/Suite 并独立验收。

## 2. 0B 实现验收

- WorkOrder、Tenant-qualified WorkflowRun、单次赋值 RootBinding、Root/Sub-agent AgentRun、RunManifest 和 AgentRuntimeRun 引用闭合；Orchestration 或 Root Admission 前失败不需要伪造下游对象；
- 自研 Native Runtime 通过 `runtime-core-v1`，支持 Start、Status、Cursor Event、Cancel、最小 Checkpoint/Restart 和无 Sandbox 模式；
- Child Spawn/Admission 覆盖委派输入、Parent/Root/Depth、ProviderResolution、不可降级的 Workspace Mount/Commit/CAS 模式、Sandbox、共享 WorkOrder Budget Ledger、AgentRun Resource Allocation、幂等、拒绝、子树 Pause/Cancel、终态汇总和孤儿对账；
- PostgreSQL Constraint 实现 Tenant、Branch WorkspaceRevision、Outbox/Inbox、Sequence、Ledger、Fencing 和 CAS 不变量；
- WorkOrder/Workflow Start、SystemSafetyControl/Event/Outbox 的事务边界有数据库集成证据；
- Redis 清空不影响授权、状态、Ledger 或 Cursor，Temporal Workflow 可以 Replay，旧 Fencing 被拒绝。

该层只证明持久化脊柱与 Native Runtime Core，不证明 Business 纵向链、Sandbox、Workbench 或生产可靠性。

## 3. 0C-0G 集成验收

- Business → ExecutionGrant → ConversationTurn → Temporal → Runtime/Sandbox → Event/Artifact/Usage 可以重复运行和恢复；
- 自研 Native Runtime 通过 `runtime-general-v1 + governed-v1`，主 SandboxProvider 与强制 Gateway 链路成立；
- Native Runtime 另通过 `runtime-agent-loop-v1`，证明模型步骤上下文与信任边界、Tool exposure/dispatch、累计预算、Compaction、Graph 确定性、Checkpoint/Resume 和副作用对账不依赖框架私有事实；
- MCP Tool Client 和 Skill Package Import 分别通过专用 Suite，并至少完成一个锁定 Transport 的 Gateway 调用和一个 Quarantine/Import/Select/Run 纵向链路；协议 Evidence 不依赖可变 Session、动态 Tool 列表或本地 Skill 目录；
- Workbench、Runtime Gateway、Artifact、Recording、Experience 和 Delivery 使用同一标准事实流；
- 独立 Reference Probe 通过 `runtime-core-v1`，不复用 Native Runtime 私有执行包，也不要求第三方项目适配；
- 0C-0G 各阶段的 Conformance 与纵向验收均绑定精确 Blueprint Revision、Contract Revision/Manifest Digest 和 Suite Digest。

该层证明 Phase 0 产品链路已经集成，不等于故障、安全或恢复证据成立。

## 4. 0H 可靠性证据

- Worker/Adapter 重启、Provider 响应丢失、重复响应和旧 Fencing Token 有可执行测试；
- RuntimeRecording 只持久化经过 Emit-time Scrub/Schema Gate 的 Chunk，并绑定 Redaction Evidence；
- 多租户隔离、NetworkPolicy、RBAC、Pod Security、容量与背压有可复现证据；
- PostgreSQL、Temporal 与 Object Storage 完成最小备份恢复演练。

0H 只形成 Phase 0 最小可靠性证据，仍不自动授予正式冻结或生产批准。

## 5. 正式冻结 Gate

正式冻结前另行完成：

- 消费者契约、历史载荷回放、双版本互操作和人工兼容性审查；
- Git 根 Workflow、供应链 Gate、公共 CI 和受保护冻结基线变量；
- 两个 Runtime Adapter 完整通过要求的 Conformance Profile；
- 破坏性变更已有版本、迁移窗口和 `DECISIONS.md` 记录。

冻结只承诺公共契约兼容边界，不授予生产批准。

## 6. 生产批准

- Temporal Replay、故障注入、多租户隔离、容量/SLO 和备份恢复有可复现运行证据；
- API/Worker 多副本不依赖粘性 Session 或 Pod 本地权威状态；
- Redis 通知丢失、Provider/Controller/Sandbox Node 故障和 Runtime 重路由可恢复或对账；
- 工作负载具备 Probe、资源限制、PDB、Topology、最小 RBAC、NetworkPolicy 和优雅 Draining 证据。

生产批准是独立决策，不能由契约 Gate、实现完成或 CI 结果自动推导。
