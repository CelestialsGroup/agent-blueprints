# 架构决策

本文件只记录当前有效的架构决策。历史审查过程不属于实施事实源；变更以下决策时必须同时更新契约、迁移策略和验证证据。

| 决策 | 理由 | 结果 |
|---|---|---|
| Business 与 Agent Platform 分离事实源 | User、Membership、Payment、Entitlement 与执行状态生命周期不同 | Business 签发 CommercialAuthorization/ExecutionGrant；Platform 只拥有技术执行与 Usage |
| 稳定内核加受控 Provider | 核心账本和授权不能被插件替换 | Conversation、WorkOrder、Ledger、Event、Artifact、Usage、Delivery 属于内核；Runtime、Sandbox、Tool、Skill、Renderer、Editor、Converter 可替换 |
| Temporal 编排，PostgreSQL 记账 | 长任务需要恢复，外部副作用需要可对账 | Temporal 管理持久 History；Invocation/Sandbox Ledger、Outbox 和当前状态由 PostgreSQL 管理，不宣称全局 Exactly-once |
| 关系当前态加 CanonicalEvent | 当前查询和审计/Timeline 都必须稳定 | 不采用全量 Event Sourcing；Work Event 使用 `work_sequence`，仅属于 Conversation 的 Event 使用 `aggregate_sequence` |
| Conversation 拥有 Workspace | 多轮 Agent 需要跨 Turn 保留产物和上下文 | WorkOrder 只表示一个可执行 Turn；ConversationBranch 维护分支头与分支内活动 WorkOrder |
| 平台拥有 AgentRuntimeProvider，不依赖单一 Agent 框架 | DeerFlow 或其他框架的内部 Agent/Thread/Run/Checkpoint、持久化和升级节奏都不稳定 | DeerFlow 只是首个参考 Adapter；LangGraph/Deep Agents、OpenAI Agents SDK、Microsoft Agent Framework、Google ADK、Mastra 或 Native Runtime 均可实现同一 Port |
| Capability、一致性验证和不可变 Revision | 同名字符串不能证明 Provider 可替换 | Scenario 解析到精确 Capability/Profile；RunManifest 固化 Definition、Revision、Admission 和 Experience 摘要 |
| Provider Envelope 与 Build Provenance | Plugin 打包方式不能污染 Runtime、Sandbox 或远程服务 | ProviderRevision 统一绑定 Implementation、稳定 Port、配置和 Conformance；Source Revision、Build、SBOM 与 Provenance 摘要不可变 |
| 明确执行拓扑 | WorkOrder、Workflow 和框架 Run 混用会破坏重试与恢复 | 一个 WorkOrder 对应一个 Platform WorkflowRun；每个 AgentRun 对应一个 RunManifest 和 AgentRuntimeRun，Sub-agent 使用显式父子关系 |
| Tenant-qualified 执行与单一 Runtime Resolution | 只靠间接 WorkOrder 关联或复制两份 Runtime Revision 会产生越权和漂移 | WorkflowRun/AgentRun/RunManifest/Runtime Start 显式绑定 Tenant；RunManifest Runtime 只引用一个 ProviderResolution |
| Service OAuth、Conversation WorkSession、单次 ExecutionGrant | 后端与浏览器信任级别不同，会员授权不能变成长会话权限 | WorkSession 绑定 Conversation、可缩窄到 WorkOrder；每个可执行 Turn 都需要新的 Business Grant 与额度 Reservation |
| Runtime Gateway 与独立 SandboxProvider | 双向连接和 Sandbox 生命周期不能依赖 API Pod 或 DeerFlow 内部实现 | 前端只访问短期 Gateway Session；Provider 私有 Pod/VM/Endpoint 不进入稳定模型；未来用 sandbox-runtime 替换 Adapter 即可 |
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
