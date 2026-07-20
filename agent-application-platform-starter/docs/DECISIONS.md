# 架构决策

本文件只记录当前有效的架构决策。历史审查过程不属于实施事实源；变更以下决策时必须同时更新契约、迁移策略和验证证据。

| 决策 | 理由 | 结果 |
|---|---|---|
| Business 与 Agent Platform 分离事实源 | User、Membership、Payment、Entitlement 与执行状态生命周期不同 | Business 签发 CommercialAuthorization/ExecutionGrant；Platform 只拥有技术执行与 Usage |
| 稳定内核加受控 Provider | 核心账本和授权不能被插件替换 | Conversation、WorkOrder、Ledger、Event、Artifact、Usage、Delivery 属于内核；Runtime、Sandbox、Tool、Skill、Renderer、Editor、Converter 可替换 |
| Temporal 编排，PostgreSQL 记账 | 长任务需要恢复，外部副作用需要可对账 | Temporal 管理持久 History；Invocation/Sandbox Ledger、Outbox 和当前状态由 PostgreSQL 管理，不宣称全局 Exactly-once |
| 关系当前态加 CanonicalEvent | 当前查询和审计/Timeline 都必须稳定 | 不采用全量 Event Sourcing；Work Event 使用 `work_sequence`，仅属于 Conversation 的 Event 使用 `aggregate_sequence` |
| Conversation 拥有 Workspace，Branch 拥有 Revision Head | 多轮 Agent 需要保留产物，并行分支不能共享可变文件头 | WorkOrder 只表示一个 Turn；ConversationBranch 用 CAS 维护 Message Head、WorkspaceRevision Head 和活动 WorkOrder |
| 新 Turn 与既有 WorkOrder 控制分离 | Append/Interrupt 既不能暗中创建第二个 WorkOrder，也不能绕过新的商业授权 | ConversationTurnRequest 创建新 WorkOrder；WorkOrderControlRequest 以新 Grant 控制现有 WorkOrder；`interrupt_and_enqueue` 创建明确后继 |
| Message、Workspace、Active Work 分离 CAS | 单一 Branch Version 会让 Steering 与文件提交互相制造无关冲突 | 三个所有权域分别使用 `message_head_version`、`workspace_head_version`、`active_work_version`；`branch_version` 只作查询 ETag |
| 平台拥有 AgentRuntimeProvider，不依赖单一 Agent 框架 | DeerFlow 或其他框架的内部 Agent/Thread/Run/Checkpoint、持久化和升级节奏都不稳定 | DeerFlow 只是首个参考 Adapter；LangGraph/Deep Agents、OpenAI Agents SDK、Microsoft Agent Framework、Google ADK、Mastra 或 Native Runtime 均可实现同一 Port |
| Capability、一致性验证和不可变 Resolution | 同名字符串不能证明 Provider 可替换，也不能解释动态路由 | Scenario 解析到精确 Capability/Profile；Resolution 固化 Resolver/Input/Candidate/Evidence/Decision，RunManifest 只引用统一解析事实 |
| 通用 Capability Provider Port | Plugin ID 不能成为 Model、Tool、MCP、Skill、Renderer 或远程服务的稳定前提 | `capability-provider-v1` 提供 Invoke/Status/Cancel/Event；独立 Token 绑定租户、客户端、主体、WorkOrder、Attempt、Fencing、请求、策略、预算、权限和 Staging |
| Provider Envelope 与 Build Provenance | Plugin 打包方式不能污染 Runtime、Sandbox 或远程服务 | ProviderRevision 统一绑定 Implementation、稳定 Port、配置和 Conformance；Source Revision、Build、SBOM 与 Provenance 摘要不可变 |
| 明确执行拓扑 | WorkOrder、Workflow 和框架 Run 混用会破坏重试与恢复 | 一个 WorkOrder 对应一个 Platform WorkflowRun；每个 AgentRun 对应一个 RunManifest 和 AgentRuntimeRun，Sub-agent 使用显式父子关系 |
| Tenant-qualified 执行与统一 Resolution 引用 | 只靠间接 WorkOrder 关联或复制 Revision 会产生越权和漂移 | WorkflowRun/AgentRun/RunManifest/Runtime Start 显式绑定 Tenant；Runtime 与每个 Sandbox Slot 只引用一个 ProviderResolution |
| 不可变准入与可续期 Runtime 授权分离 | 把短期 ArtifactGrant/Token 写进 RunManifest 会让长任务、Adapter 重启和 Resume 无法恢复，也可能让续期绕过商业期限 | RunManifest 固化输入、ArtifactAccessRequirement、初始授权上限、CommercialAuthorization ID/Digest/到期上限和续期规则；每个 Attempt 使用内部作用域闭合、带前驱摘要的 RuntimeAuthorization 与同窗 ArtifactGrant，等价/缩权续期，扩权新建 WorkOrder |
| Provider Artifact/Usage 所有权收口 | Provider 直接 Finalize ArtifactVersion 或构造 Platform TechnicalUsageEntry 会形成竞争事实源 | Provider 只写 Staging 并返回 UsageObservation；Platform 校验后 Finalize ArtifactVersion、分配 TechnicalUsage identity/idempotency/recorded_at |
| PrincipalContext 与解析依赖显式化 | 只有一个不透明摘要无法审计身份路由，routing_reason 也不能证明是否使用身份 | ExecutionGrant 内嵌有界 PrincipalContextSnapshot；ProviderResolution 用 identity_dependency 明确声明并绑定摘要 |
| 可执行语义追踪 | 文件存在或函数名标签不能证明约束真的被测试 | 每个 contract_gate Check ID 必须注册并在当前 Gate 执行；DDL/网络/Conformance 责任保留为明确的 Phase 0 待实现证据 |
| Fail-closed 限额与请求体上限 | 空 limits 和无界 JSON 会产生跨实现歧义及资源耗尽 | EffectiveExecutionLimits 全字段必填；各写操作声明 encoded-byte 上限并在解析前以 413 拒绝 |
| 最新稳定运行时与可复现构建并存 | 浮动 `latest` 不可复现，Node Current 生命周期又不适合作为生产基线 | Go/Python 固定最新正式稳定补丁，Node 固定最新 Active LTS；精确版本、依赖锁、OCI Digest 和 BuildProvenance 受治理，升级走双版本/Canary/Rollback |
| 来源身份与 Inbox 去重 | Provider 重试和游标重放不能依赖平台 Event ID 偶然去重 | CanonicalEvent 固化 Producer/ProviderRevision/SourceStream/SourceEvent/Cursor 和 Dedupe Key，Metadata 闭合，Inbox 建唯一约束 |
| Service OAuth、Conversation WorkSession、单次 ExecutionGrant | 后端与浏览器信任级别不同，会员授权不能变成长会话权限 | WorkSession 绑定 Conversation、可缩窄到 WorkOrder；每个可执行 Turn 都需要新的 Business Grant 与额度 Reservation |
| Runtime Gateway 与按需 SandboxProvider | 双向连接和 Sandbox 生命周期不能依赖 API Pod 或 DeerFlow 内部实现，轻量 Run 也不应被迫创建 Sandbox | 前端只访问短期 Gateway Session；Scenario Capability 决定是否创建 Sandbox；Provider 私有 Pod/VM/Endpoint 不进入稳定模型 |
| 强制 Model/Tool/Artifact/Egress Gateway | Prompt 约束不能执行预算、审批和网络策略 | 公共 SaaS Runtime 必须通过受治理 Profile；外部副作用进入 Invocation Ledger |
| 类型化 Runtime 事件与 Gateway 帧 | 任意 Payload、隐式重连和无界流无法跨 Adapter 恢复 | 核心 Command/Event、Background Task、Usage 和 `runtime-gateway/v1` 帧均有闭合 Schema；Run 绑定 Event Registry；Gateway 使用多 Channel Cursor、Sequence、Generation、ACK、Control Digest 和回放边界 |
| Policy 严重度与独立 Sandbox | 配置顺序和 Hook 不能构成安全边界 | 所有规则按 `deny > ask > allow` 合并；Approval、OS Sandbox、Gateway 与 Invocation 各自独立执行 |
| 技术 Usage 与商业 Settlement 分离 | Provider 用量、价格和余额具有不同事实源 | Platform 固化 MeterRevision、Evidence、顺序、更正链并在 Settlement Envelope 中嵌入完整 UsageReport；Business 独占价格、余额和结算结论 |
| Conformance 是内容寻址的准入事实 | Suite 名称或 README 声明无法证明不同 Provider 真正可替换 | Suite 自带 Digest；ProviderRevision 结果绑定 Suite ID/Version/Digest/Profile 和不可变 Evidence |
| Runtime 核心与呈现 Adapter 分离 | 同一执行能力需要支持 Workbench、Headless 和未来 IDE | Runtime Session Core 产生统一 Command/Event/Artifact/Usage；REST/SSE、Workbench、Headless 或 ACP 仅是边缘 Adapter |
| 注册制 Ingest/Delivery 与隔离 UI Extension | 任意 URL/JS 会破坏 SSRF 和浏览器信任边界 | 外部 Endpoint 预注册；富 UI 仅允许签名 Bundle、不透明 Origin iframe 和类型化 postMessage |
| 绝对 Schema ID、Strict I-JSON、JCS 和契约清单 | 跨语言摘要与独立发布必须可复现 | 所有实现通过共享正反向向量；兼容性与完整性分别治理 |

Agent Runtime 选型按 Scenario Capability、受治理 Profile、Tenant Binding、成本和运行环境解析，不设平台级全局框架。每个 Run 在准入时锁定一个不可变 ProviderRevision；运行中禁止静默切换框架。标准 Command/Event/Usage/Artifact 可以跨 Provider 归一化，但 Provider 原生 Checkpoint 默认只保证同一兼容性声明范围内恢复。

当前候选版本仍未冻结。以上决策只证明架构边界；生产批准还需要 Phase 0 实现、故障注入、隔离、容量和恢复证据。
