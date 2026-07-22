# v0.9.0 架构与实施验收层级

本文件定义验收条件，不记录某次运行状态。实际结果只看 `CONTRACT_VALIDATION_REPORT.md`、实现测试和生产证据，四个层级不得互相替代。

## 1. 本地架构候选 Gate

进入 Phase 0 实现前必须满足：

- `./scripts/bootstrap_contracts.sh` 可在支持的 Python/Node/Go 版本完成；
- `make validate-architecture` 通过，9 个 OpenAPI 为 0 错误/0 警告，Bundle 可重复；
- ExecutionGrant 精确绑定 WorkOrderRequest/ConversationTurnRequest/WorkOrderControlRequest Contract ID、Digest Profile 和请求摘要；
- ConversationBranch Create/Fork 命令绑定来源 Message Cut、WorkspaceRevision 与 Head CAS，原子产生新 Branch/初始 Revision/核心事件；并行 Branch 不共享可变文件头；
- Runtime 与 Sandbox Slot 只引用带 Resolver/Input/Candidate/Evidence/Decision 的 ProviderResolution；
- Resolution 显式绑定 Tenant/ClientApplication/WorkOrder 或 ArtifactOperation ExecutionScope；ArtifactIngest 不调度 Provider。依赖身份时通过 identity_dependency 绑定 PrincipalContextSnapshot；
- RunManifest 携带实际输入、ContextPackage、ArtifactAccessRequirement、初始 Budget/Policy/Permissions 上限、商业授权 ID/Digest/到期上限、续期规则和四类 Gateway Binding；Runtime Start 携带本 Attempt 的等价/缩权 RuntimeAuthorization/ArtifactGrant，并拒绝内部作用域不闭合或越过商业/ArtifactGrant 时间窗的授权；
- Conversation Turn 与 WorkOrder Control 分离，三个 CAS 所有权域分离，WorkOrder 可从 accepted 直接请求取消；
- 通用 Capability Provider Port/Token 不要求 `plugin_id`；请求携带完整执行授权值并绑定 ProviderResolution/Instance/Audience，操作级 Token 以正式 Contract/Profile/Digest 绑定 Invoke/Status/Cancel/Event；Invoke `execution` 不越过原 deadline/CommercialAuthorization，后续前驱链 `safety_control` 只做 Status/Cancel/Event 且无 Artifact/副作用权限；`read_events` 有正反向游标证据；
- Agent Runtime 的 Start/Command/Status/Event 和兼容 Plugin 的 Invoke/Status/Cancel/Event 也以单操作 Contract/Profile/Digest 绑定请求或规范化读描述符；路径、默认查询值和 Cursor 均不可脱离摘要替换；Plugin Invoke `execution` 受 Deadline/Artifact 窗口限制，到期后 `safety_control` 只能 Status/Cancel/Event；
- Runtime `execution` Token 不越过 RuntimeAuthorization/命令 Deadline；到期后的 `safety_control` 只能 Status/Event/Cancel/Pause，不能恢复执行或产生新副作用；
- 用户 Runtime 控制继续绑定 WorkOrderControlRequest + ExecutionGrant；Business 撤销通过 sender-constrained、幂等的 CommercialAuthorizationRevocation 接口进入，Platform 不改写商业事实；授权到期/撤销和紧急止损使用唯一 Safety Controller 签发、仅追加的 SystemSafetyControl。两种 Command 授权来源互斥，系统来源与 Token 必须绑定相同 Tenant/WorkOrder/RuntimeRun/action/digest/触发证据，且不能授权 Resume、Append、Interrupt、Approval 或 Checkpoint；
- CommercialAuthorization 撤销收据带 JCS 摘要与同步 deny 生效点，并精确枚举 WorkSession、活动 WorkOrder、ArtifactOperation、ArtifactIngest 的 CAS/Outbox intents；fan-out 可恢复且未完成不得宣称撤销闭合；
- Service/Grant/Session 与六类执行 Token 均有用途专属的闭合 JWS Header Schema，唯一 `typ`、Algorithm/Key allowlist 与 Claims Profile 不得交叉接受；
- Runtime/Capability/Sandbox/Artifact/Egress 执行 Token 的 `nbf` 不早于所绑定 Authorization/Policy/Grant 生效，`exp` 不越过对应执行期限；
- Model/Tool 复用 Capability Port；Artifact/Egress 拥有独立 OpenAPI、操作 Token、Contract ID/Profile/Digest 和 Conformance Profile，ArtifactStagingGrant 不授予 Finalize；Egress 绑定不可变 Owner-scoped DestinationRevision 并按 destination_class 授权；
- Preview/Edit/Conversion 公开请求拒绝 Platform-owned Operation ID、Policy/Budget/Permissions/Gateway/Provider 事实；Platform 分配 ArtifactOperation 后派生 admission facts，并复用 Capability Invocation/Attempt + Artifact Gateway + TechnicalUsage/Settlement。启动前终态不伪造 Resolution/Invocation，Projection 不能成为第二执行事实源；
- Delivery/Settlement 对终态在非空 UsageReport 与 NoUsageAttestation 间显式选择；CompatibilityDecision/Evidence 与 SecretGrant/Credential Gateway 均有 fail-closed 正反例；ArtifactIngest Create 拒绝调用方 Policy/Budget/Permissions，Session 分配后由 Platform 派生，Status/Confirm/Scan/Finalize 由 Platform 最终事务闭合；
- WorkspaceContentManifest、Sandbox Slot 选择、Event 来源 Inbox 去重、闭合且有界的 Event/Conversation/Work Metadata、诊断/审批 Details 和所有 JSON 写接口的 HTTP encoded-body 上限均有可执行契约；
- Platform 与标准 Runtime CanonicalEvent 分别绑定所有权匹配的 Platform/Runtime Core Registry Revision，并按 `(type,data_version)` 验证 Payload；Provider 私有 Registry 不能进入核心流；
- `contracts/semantic-constraints-v1.json` 覆盖全部关键语义；每个 Contract Gate Check ID 在当前运行中真实执行，并与待实现 DDL/Conformance 责任明确分离；
- RunManifest 支持 Capability 驱动的零或多个 Sandbox，主 Slot 条件闭合；
- RuntimeSessionRoute 只包含 Gateway 与不透明 Provider Route Reference，不包含原始 Endpoint、Cluster、Region 或 Cell；
- RunManifest Location 只保存 Placement Mode、可空逻辑 Region、Policy Reference 和 Decision Digest；ProviderHealth、SandboxStatus 与 SandboxSpec 不暴露 Cluster/Cell/Node/Runtime 身份，远程 Provider 不被强制伪造本地拓扑；
- Sandbox Capability 发现只接受已准入控制面 mTLS；其余 14 个 Sandbox 操作全部以单操作 Token 绑定正式 Contract ID、Digest Profile 和请求体或规范化读描述符，路径/游标替换有正反向证据；
- `51_PHASE0_TECHNOLOGY_SELECTION.md` 已给出 0B 首选/备选/不选、语言边界、版本策略、许可证复核、Canary 和 Rollback；
- 状态机、JCS、Schema、语义负例与 Python/Node 契约清单一致。

该 Gate 不包含 GitHub CI、仓库供应链准入或冻结基线；通过只表示候选架构可以进入实施。

## 2. Phase 0 实现验收

- WorkOrder、Tenant-qualified WorkflowRun、单次赋值 RootBinding、Root/Sub-agent AgentRun、RunManifest 和 AgentRuntimeRun 引用闭合；Orchestration 或 Root Admission 前失败不需要伪造下游对象；
- 自研 Native Runtime 先通过 `runtime-core-v1`，再通过 `runtime-general-v1 + governed-v1`；独立 Reference Probe 在冻结前通过 `runtime-core-v1`，不要求第三方项目适配；
- Child Spawn/Admission 覆盖委派输入、Parent/Root/Depth、ProviderResolution、不可降级的 Workspace Mount/Commit/CAS 模式、Sandbox、共享 WorkOrder Budget Ledger、AgentRun Resource Allocation、幂等、拒绝、子树 Pause/Cancel、终态汇总和孤儿对账；
- PostgreSQL Constraint 实现 Tenant、Branch WorkspaceRevision、Outbox/Inbox、Sequence、Ledger、Fencing 和 CAS 不变量；
- Business → ExecutionGrant → ConversationTurn → Temporal → Runtime/Sandbox → Event/Artifact/Usage 可重复运行和恢复；
- RuntimeRecording 只持久化经过 Emit-time Scrub/Schema Gate 的 Chunk，并绑定 Redaction Evidence；
- Redis 清空、Worker/Adapter 重启、Provider 响应丢失和旧 Fencing Token 有可执行测试。

该层证明真实组件和纵向链存在，不等于生产可靠性。

## 3. 正式冻结 Gate

冻结 `v0.9.0` 前另行完成：

- 消费者契约、历史载荷回放、双版本互操作和人工兼容性审查；
- Git 根 Workflow、供应链 Gate、公共 CI 和受保护冻结基线变量；
- 两个 Runtime Adapter 完整通过要求的 Conformance Profile；
- 破坏性变更已有版本、迁移窗口和 `DECISIONS.md` 记录。

冻结只承诺公共契约兼容边界，不授予生产批准。

## 4. 生产批准

- Temporal Replay、故障注入、多租户隔离、容量/SLO 和备份恢复有可复现运行证据；
- API/Worker 多副本不依赖粘性 Session 或 Pod 本地权威状态；
- Redis 通知丢失、Provider/Controller/Sandbox Node 故障和 Runtime 重路由可恢复或对账；
- 工作负载具备 Probe、资源限制、PDB、Topology、最小 RBAC、NetworkPolicy 和优雅 Draining 证据。

生产批准是独立决策，不能由契约 Gate、实现完成或 CI 结果自动推导。
