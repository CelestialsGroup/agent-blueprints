# 架构决策

本文件只记录当前有效的架构决策。历史审查过程不属于实施事实源；变更以下决策时必须同时更新契约、迁移策略和验证证据。

| 决策 | 理由 | 结果 |
|---|---|---|
| Blueprint 与产品实现独立版本化 | 架构/契约的兼容周期与产品源码、部署和运行证据的生命周期不同；共同目录不能成为隐式耦合 | Blueprint 只拥有架构、公共契约、开发规范和验收标准；实现仓库以精确 Blueprint Revision、Contract Manifest Digest 和 Suite Digest 单向消费。两者可并置开发，也可拆成独立仓库，Blueprint 不跟踪实现进度 |
| Business 与 Agent Platform 分离事实源 | User、Membership、Payment、Entitlement 与执行状态生命周期不同 | Business 签发 CommercialAuthorization/ExecutionGrant；Platform 只拥有技术执行与 Usage |
| 稳定内核加受控 Provider | 核心账本和授权不能被插件替换 | Conversation、WorkOrder、Ledger、Event、Artifact、Usage、Delivery 属于内核；Runtime、Sandbox、Tool、Skill、Renderer、Editor、Converter 可替换 |
| Temporal 编排，PostgreSQL 记账 | 长任务需要恢复，外部副作用需要可对账 | Temporal 管理持久 History；Invocation/Sandbox Ledger、Outbox 和当前状态由 PostgreSQL 管理，不宣称全局 Exactly-once |
| 关系当前态加 CanonicalEvent | 当前查询和审计/Timeline 都必须稳定 | 不采用全量 Event Sourcing；Work Event 使用 `work_sequence`，仅属于 Conversation 的 Event 使用 `aggregate_sequence` |
| Conversation 拥有 Workspace，Branch 拥有 Revision Head | 多轮 Agent 需要保留产物，并行分支不能共享可变文件头 | WorkOrder 只表示一个 Turn；ConversationBranch 用 CAS 维护 Message Head、WorkspaceRevision Head 和活动 WorkOrder |
| Branch Create/Fork 是命令而非 Projection 约定 | Debug rerun 与并行分支若只靠列表模型会迫使实现自行发明 Cut/CAS | Create 绑定 Conversation 初始 WorkspaceRevision；Fork 绑定来源 Branch、Message Cut、WorkspaceRevision Digest 及双 Head CAS，并原子创建 Branch、初始 Revision 与核心事件 |
| 新 Turn 与既有 WorkOrder 控制分离 | Append/Interrupt 既不能暗中创建第二个 WorkOrder，也不能绕过新的商业授权 | ConversationTurnRequest 创建新 WorkOrder；WorkOrderControlRequest 以新 Grant 控制现有 WorkOrder；`interrupt_and_enqueue` 创建明确后继 |
| 用户控制与平台安全减权分离 | 商业授权到期、撤销或紧急停机时，要求新的 Business Grant 会让平台无法停止失控执行；把安全路径做成通用控制又会形成扩权旁路 | 用户控制继续使用 WorkOrderControlRequest + ExecutionGrant；Business 通过 sender-constrained Revocation Notice 撤销自己的授权，唯一 Platform Safety Controller 只可签发不可变 SystemSafetyControl，以触发证据和摘要绑定一个 Tenant/WorkOrder/RuntimeRun 的 Pause/Cancel，禁止 Resume、输入、批准、Checkpoint 和新副作用 |
| Message、Workspace、Active Work 分离 CAS | 单一 Branch Version 会让 Steering 与文件提交互相制造无关冲突 | 三个所有权域分别使用 `message_head_version`、`workspace_head_version`、`active_work_version`；`branch_version` 只作查询 ETag |
| 自研 Native Runtime 是主实现，参考项目不等于适配目标 | 把 DeerFlow、Dify 或其他完整项目设为主 Adapter 会让产品路线、升级和许可证受上游支配 | Native Runtime 通过 AgentRuntimeProvider 实现正式主链；DeerFlow、Dify、OpenHands、LangGraph、OpenAI Agents SDK 等只参考架构、能力与 UX，不列入 Provider 适配计划 |
| Dify 双轨参考、稳定实现 | Dify 2 Beta 的版本号不能证明其代码晚于当前稳定版，Beta Graph/Agent/Sandbox 也不能成为生产可靠性证据 | 以当期最新稳定 Tag/Commit 参考 Workflow、Plugin、RAG、契约生成和 SSE；Dify 2 Beta 仅作 Knowledge Pipeline、Graph 模块和产品 Feature Radar。采纳行为由平台重新实现，不连接或嵌入 Dify |
| Capability、一致性验证和不可变 Resolution | 同名字符串不能证明 Provider 可替换，也不能解释动态路由 | Scenario 解析到精确 Capability/Profile；Resolution 固化 Resolver/Input/Candidate/Evidence/Decision，RunManifest 只引用统一解析事实 |
| 通用 Capability Provider Port | Plugin ID 不能成为 Model、Tool、MCP、Skill、Renderer 或远程服务的稳定前提，执行期限也不能同时撤销平台的取消与对账能力 | `capability-provider-v1` 提供 Invoke/Status/Cancel/Event；请求携带完整执行授权值并绑定 Resolution/Instance/Audience，Invoke 使用 `execution`，后续前驱链 Token 使用无 Artifact/副作用权限的 `safety_control` |
| 非 WorkOrder Artifact 执行复用 ExecutionScope | Preview/Edit/Conversion 若拥有独立 Provider Job、Usage 或 Gateway 模型会产生第二执行事实源；若客户端预先提交 Operation-scoped Policy/Gateway 又形成 Scope 分配循环与授权注入 | 客户端只提交业务授权与 Artifact/Capability 意图；Platform 分配 ArtifactOperation 后派生 Policy/Budget/Permissions/Gateway/ProviderResolution。Capability Invocation/Attempt、TechnicalUsage 与 Settlement 统一绑定该 Scope，Projection 不拥有重试或终态 |
| ArtifactOperation 取消是持久状态而非终态捷径 | 撤销收据若只能直接把 Operation 置为 cancelled，会丢失取消派发、响应丢失和 Provider 已完成竞态 | 所有活动态先记录 `cancel_requested` 与来源收据/Intent/Outbox；已派发进入 `cancelling`，未知结果进入 `cancellation_reconciling` 且禁止重派。已派发 Operation 只投影唯一 Invocation 已提交/对账的 cancelled 事实；成功仅接受取消 CAS 前已提交的 Platform Finalization 证明。该收紧发生在 v0.9.0 未冻结期，不保留旧的直接取消协议 |
| 终态零用量必须有肯定证据 | 启动前失败/取消无法生成非空 UsageReport，缺失又不能解释为零 | Delivery 与 Settlement 在非空 Final/Correction UsageReport 和不可变 NoUsageAttestation 间二选一；未知、Partial 或 Estimated 保持待对账 |
| Checkpoint/Snapshot 兼容由 Platform 判定 | Provider 自报 portable 无法证明目标 Revision 可恢复 | Source/Target ProviderRevision、Runtime Revision、Profile、Suite Digest 与 Evidence 形成不可变 CompatibilityDecision；缺失、失败或不匹配在 Dispatch 前 fail-closed |
| Secret 只经单操作 Credential mediation | `secret_reference_ids` 若直接解析为凭据会绕过用途、工作负载和撤销边界 | SecretGrant 绑定 Tenant/Principal/ExecutionScope/Provider/Workload/Target/Intent Digest；Credential Token 短 TTL、sender-constrained、单次消费并审计，明文与 Handle 禁止持久化或缓存 |
| Artifact Ingest 是分阶段 Platform Ledger | 上传成功或 Scanner 回调若直接创建 Version 会绕过授权、扫描和最终事务；要求客户端提交 Session-scoped Policy/Budget 又会形成 ID 分配循环 | Create 只接收认证身份、业务授权和上传意图；Platform 分配 Session 后派生 Policy/Budget/Permissions。Status/Confirm/Scan/Finalize 幂等推进状态机，只有 Platform Finalize 事务创建 ArtifactVersion 和 Outbox |
| 所有 Provider Token 单操作绑定 | 只在 Claim 中写操作名但不摘要绑定 Path/Query/Body，仍允许合法 Token 被改写成另一状态、取消或事件请求 | Runtime、Capability、Sandbox、Artifact 与兼容 Plugin 的每个受保护操作都绑定正式 Contract、Digest Profile 和请求/规范化描述符摘要；静态 Gate 检查 OpenAPI 映射完整性 |
| 可执行 Gateway Port 与短期操作授权 | 只有 Route ID 或 Staging Session ID 会迫使实现自行发明凭据、上传和网络协议 | Model/Tool 复用 Capability Port；Artifact/Egress 使用独立 OpenAPI、Contract Digest、Audience 和操作 Token；ArtifactStagingGrant 只允许 Quarantine/Commit，不允许 Finalize |
| RunManifest 精确绑定来源请求 | 无 Profile 的裸 `request_digest` 无法证明 Manifest 来自哪一种已授权请求 | Manifest 保存已消费 ExecutionGrant 的 Request Contract ID、Digest Profile 和 Digest；变更请求必须产生新的授权与 Manifest |
| WorkOrder 失败不伪造中间态 | Orchestration Start 前失败、Queued 启动失败、等待拒绝或暂停期间 Provider 失败不应先制造虚假 queued/running | `accepted`、`queued`、`waiting`、`paused` 可依据结构化失败证据直接进入 `failed`，状态更新仍需 Expected-state/Fencing |
| Provider Envelope 与 Build Provenance | Plugin 打包方式不能污染 Runtime、Sandbox 或远程服务 | ProviderRevision 统一绑定 Implementation、稳定 Port、配置和 Conformance；Source Revision、Build、SBOM 与 Provenance 摘要不可变 |
| 明确可失败的执行拓扑 | 强制 WorkOrder、WorkflowRun、Root AgentRun 和 RunManifest 同时存在会让 Orchestration/Provider/Sandbox 准入前失败无法表达 | WorkOrder 启动前可无 WorkflowRun；Start 成功后创建唯一 WorkflowRun；Root Admission 成功后以单次赋值 RootBinding 原子绑定 Root AgentRun/RunManifest。Sub-agent 通过显式 Spawn/Admission 父子关系创建 |
| 平台治理多 Agent 子树 | Runtime 私自 Spawn 会绕过 ProviderResolution、预算、授权、隔离、取消和终态 | Child SpawnRequest 只表达需求；Platform Admission 分配身份、Provider、Sandbox、AgentRunWorkspaceBinding 与仅含资源维度的 AgentRunBudgetAllocation。所有 Run 共享 WorkOrder Budget Ledger，拓扑上限不复制；Pause/Cancel fan-out 以连续版本/前驱摘要持久推进且目标不可变；WorkOrder 终态等待 required Child 收敛并对账孤儿 Run |
| Tenant-qualified 执行与统一 Resolution 引用 | 只靠间接 WorkOrder 关联或复制 Revision 会产生越权和漂移 | WorkflowRun/AgentRun/RunManifest/Runtime Start 显式绑定 Tenant；Runtime 与每个 Sandbox Slot 只引用一个 ProviderResolution |
| 不可变准入与可续期 Runtime 授权分离 | 把短期 ArtifactGrant/Token 写进 RunManifest 会让长任务、Adapter 重启和 Resume 无法恢复，也可能让续期绕过商业期限；反之，一刀切过期又会阻止平台取消或对账失控 Runtime | RunManifest 固化输入、ArtifactAccessRequirement、初始授权上限、CommercialAuthorization ID/Digest/到期上限和续期规则；每个 Attempt 使用内部作用域闭合、带前驱摘要的 RuntimeAuthorization 与同窗 ArtifactGrant，等价/缩权续期，扩权新建 WorkOrder；执行 Token 不越权，独立 `safety_control` 只允许 Status/Event/Cancel/Pause |
| Provider Artifact/Usage 所有权收口 | Provider 直接 Finalize ArtifactVersion 或构造 Platform TechnicalUsageEntry 会形成竞争事实源 | Provider 只写 Staging 并返回 UsageObservation；Platform 校验后 Finalize ArtifactVersion、分配 TechnicalUsage identity/idempotency/recorded_at |
| PrincipalContext 与解析依赖显式化 | 只有一个不透明摘要无法审计身份路由，routing_reason 也不能证明是否使用身份 | ExecutionGrant 内嵌有界 PrincipalContextSnapshot；ProviderResolution 用 identity_dependency 明确声明并绑定摘要 |
| 可执行语义追踪 | 文件存在或函数名标签不能证明约束真的被测试 | 每个 contract_gate Check ID 必须注册并在当前 Gate 执行；DDL/网络/Conformance 责任保留为明确的 Phase 0 待实现证据 |
| Fail-closed 限额与请求体上限 | 空 limits 和无界 JSON 会产生跨实现歧义及资源耗尽 | EffectiveExecutionLimits 全字段必填；各写操作声明 encoded-byte 上限并在解析前以 413 拒绝 |
| 稳定接口最小披露与有界扩展 Map | 公共状态、Event 或 RunManifest 中的 Runtime/Node/Cluster/Cell 会把 Provider 拓扑变成稳定事实，无界 Metadata/Details 会绕过载荷和兼容性治理 | SandboxStatus/ProviderHealth 与 CanonicalEvent Metadata 不保存 Provider 后端 Runtime 或部署拓扑；RunManifest 只保存带摘要的逻辑 Placement；Conversation/Work Metadata 与诊断 Details 使用有界标量 Map，并由静态 Gate 防回归 |
| 最新稳定运行时与可复现构建并存 | 浮动 `latest` 不可复现，Node Current 生命周期又不适合作为生产基线 | Go/Python 固定最新正式稳定补丁，Node 固定最新 Active LTS；精确版本、依赖锁、OCI Digest 和 BuildProvenance 受治理，升级走双版本/Canary/Rollback |
| Phase 0 三语言与保守组件栈 | 稳定内核、Web 体验和 Agent 框架生态的优势语言不同，但无限多语言会放大运维和契约漂移 | Go 负责内核/Worker/Gateway/Controller，TypeScript 负责 Workbench/BFF，Python 只负责 Runtime/ML Adapter；Node 统一 pnpm，跨语言只共享版本化契约、JCS 向量和 Conformance，具体矩阵见 `51_PHASE0_TECHNOLOGY_SELECTION.md` |
| Egress DestinationRevision | 可变 destination_id 不能证明请求使用哪个 Origin/Redirect/DNS/Owner Policy，且资源 ID 不能与权限类别混用 | 请求与 Token 绑定不可变 owner-scoped DestinationRevision ID/Digest/Class；EffectivePermissions 只匹配 destination_class，原始 Origin 始终由 Gateway 私有解析 |
| Runtime Route 不透明 | 原始 Endpoint、Cluster、Region 和 Cell 会把 Provider 基础设施提升为稳定事实 | RuntimeSessionRoute 只保存 Gateway Route 与带摘要的不透明 Provider Route Reference；仅 Gateway Adapter 可解析 Provider 私有 Endpoint |
| 来源身份与 Inbox 去重 | Provider 重试和游标重放不能依赖平台 Event ID 偶然去重 | CanonicalEvent 固化 Producer/ProviderRevision/SourceStream/SourceEvent/Cursor 和 Dedupe Key，Metadata 闭合，Inbox 建唯一约束 |
| Service OAuth、Conversation WorkSession、单次 ExecutionGrant | 后端与浏览器信任级别不同，会员授权不能变成长会话权限 | WorkSession 绑定 Conversation、可缩窄到 WorkOrder；每个可执行 Turn 都需要新的 Business Grant 与额度 Reservation |
| JWS Header 与 Claims 双重类型隔离 | 只有 Claims Schema 时，错误 `typ/alg/kid` 仍可能被 JWT 库默认接受，跨用途 Token 也可能进入错误验证器 | 九类 Token 各自使用闭合 Header Schema 和唯一 `typ`；Header 与 Claims 必须由同一 Profile 同时校验，Issuer/Key/Algorithm 使用预注册 allowlist |
| Runtime Gateway 与按需 SandboxProvider | 双向连接和 Sandbox 生命周期不能依赖 API Pod 或 DeerFlow 内部实现，轻量 Run 也不应被迫创建 Sandbox | 前端只访问短期 Gateway Session；Scenario Capability 决定是否创建 Sandbox；Provider 私有 Pod/VM/Endpoint 不进入稳定模型 |
| Sandbox 能力发现与操作授权分离 | Capability 协商发生在 Sandbox/Operation 建立前，无法合法绑定操作令牌；只绑定裸摘要又允许跨接口和查询游标重放 | Capability 发现只接受已准入控制面 mTLS；其余 14 个操作使用单操作 Token，并以 Contract ID、Digest Profile 和请求/读描述符摘要绑定路径、查询、Attempt 与 Fencing |
| 强制 Model/Tool/Artifact/Egress Gateway | Prompt 约束不能执行预算、审批和网络策略 | 公共 SaaS Runtime 必须通过受治理 Profile；外部副作用进入 Invocation Ledger |
| 类型化 Runtime 事件与 Gateway 帧 | 任意 Payload、隐式重连和无界流无法跨 Adapter 恢复 | 核心 Command/Event、Background Task、Usage 和 `runtime-gateway/v1` 帧均有闭合 Schema；Run 绑定 Runtime Registry，Platform 事件绑定 Platform Registry，CanonicalEvent 按 Producer 所有权保留对应 Registry；Gateway 使用多 Channel Cursor、Sequence、Generation、ACK、Control Digest 和回放边界 |
| Policy 严重度与独立 Sandbox | 配置顺序和 Hook 不能构成安全边界 | 所有规则按 `deny > ask > allow` 合并；Approval、OS Sandbox、Gateway 与 Invocation 各自独立执行 |
| 技术 Usage 与商业 Settlement 分离 | Provider 用量、价格和余额具有不同事实源 | Platform 固化 MeterRevision、Evidence、顺序、更正链并在 Settlement Envelope 中嵌入完整 UsageReport；Business 独占价格、余额和结算结论 |
| 商业撤销收据覆盖全部执行 Scope | 只取消 RuntimeRun 会遗留 ArtifactOperation/Ingest 继续产生副作用 | 收据提交同步建立 deny，并持久枚举 WorkSession、WorkOrder、ArtifactOperation、ArtifactIngest 的 CAS/Outbox intents；WorkOrder 使用 fenced SystemSafetyControl，其余 Scope 按自身状态机 Cancel 并持续对账 |
| Conformance 是内容寻址的准入事实 | Suite 名称或 README 声明无法证明 Provider 可替换或平台边缘安全行为已实现 | Suite 自带 Digest；ProviderRevision 结果绑定 Suite ID/Version/Digest/Profile 和不可变 Evidence，Agent Access 等平台组件以独立 Suite 记录实施验收证据 |
| Runtime 核心与呈现 Adapter 分离 | 同一执行能力需要支持 Workbench、Headless 和未来 IDE | Runtime Session Core 产生统一 Command/Event/Artifact/Usage；REST/SSE、Workbench、Headless 或 ACP 仅是边缘 Adapter |
| 注册制 Ingest/Delivery 与隔离 UI Extension | 任意 URL/JS 会破坏 SSRF 和浏览器信任边界 | 外部 Endpoint 预注册；富 UI 仅允许签名 Bundle、不透明 Origin iframe 和类型化 postMessage |
| 绝对 Schema ID、Strict I-JSON、JCS 和契约清单 | 跨语言摘要与独立发布必须可复现 | 所有实现通过共享正反向向量；兼容性与完整性分别治理 |

Agent Runtime 选型按 Scenario Capability、受治理 Profile、Tenant Binding、成本和运行环境解析，不设平台级全局框架。每个 Run 在准入时锁定一个不可变 ProviderRevision；运行中禁止静默切换框架。标准 Command/Event/Usage/Artifact 可以跨 Provider 归一化，但 Provider 原生 Checkpoint 默认只保证同一兼容性声明范围内恢复。

当前候选版本仍未冻结。以上决策只证明架构边界；生产批准还需要 Phase 0 实现、故障注入、隔离、容量和恢复证据。
