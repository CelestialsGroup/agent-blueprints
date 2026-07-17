# Architecture Decisions

本文件只记录当前有效的架构决策。历史审查过程不属于实施事实源；变更以下决策时必须同时更新契约、迁移策略和验证证据。

| Decision | Rationale | Consequence |
|---|---|---|
| Business 与 Agent Platform 分离事实源 | User、Membership、Payment、Entitlement 与执行状态生命周期不同 | Business 签发 CommercialAuthorization/ExecutionGrant；Platform 只拥有技术执行与 Usage |
| 稳定内核加受控 Provider | 核心账本和授权不能被插件替换 | Conversation、WorkOrder、Ledger、Event、Artifact、Usage、Delivery 属于内核；Runtime、Sandbox、Tool、Skill、Renderer、Editor、Converter 可替换 |
| Temporal 编排，PostgreSQL 记账 | 长任务需要恢复，外部副作用需要可对账 | Temporal 管 durable history；Invocation/Sandbox Ledger、Outbox 和 current state 由 PostgreSQL 管理，不宣称全局 Exactly-once |
| 关系当前态加 CanonicalEvent | 当前查询和审计/Timeline 都必须稳定 | 不采用全量 Event Sourcing；Work 事件使用 work_sequence，Conversation-only 事件使用 aggregate sequence |
| Conversation 拥有 Workspace | 多轮 Agent 需要跨 Turn 保留产物和上下文 | WorkOrder 只表示一个可执行 Turn；ConversationBranch 维护分支 head 与 branch-local active WorkOrder |
| DeerFlow 实现 AgentRuntimeProvider | 平台不能绑定上游 Thread/Run/Checkpoint 模型 | DeerFlow 只存在于 Adapter 私有模型；升级创建新 ProviderRevision，并通过 command/event/checkpoint conformance |
| Capability、Conformance 和不可变 Revision | 同名字符串不能证明 Provider 可替换 | Scenario 解析到精确 Capability/Profile；RunManifest 固化 Definition、Revision、Admission 和 Experience digest |
| Service OAuth、Conversation WorkSession、单次 ExecutionGrant | 后端与浏览器信任级别不同，会员授权不能变成长会话权限 | WorkSession 绑定 Conversation、可缩窄到 WorkOrder；每个可执行 Turn 都需要新的 Business Grant 与 quota reservation |
| Runtime Gateway 与独立 SandboxProvider | 双向连接和 Sandbox 生命周期不能依赖 API Pod 或 DeerFlow 内部实现 | 前端只访问短期 Gateway Session；Provider 私有 Pod/VM/endpoint 不进入稳定模型；未来 sandbox-runtime 替换 Adapter 即可 |
| 强制 Model/Tool/Artifact/Egress Gateway | Prompt 约束不能执行预算、审批和网络策略 | 公共 SaaS Runtime 必须通过 governed profile；外部副作用进入 Invocation Ledger |
| 注册制 Ingest/Delivery 与隔离 UI Extension | 任意 URL/JS 会破坏 SSRF 和浏览器信任边界 | 外部端点预注册；富 UI 仅允许签名 bundle、opaque-origin iframe 和 typed postMessage |
| 绝对 Schema ID、Strict I-JSON、JCS 和 Contract Manifest | 跨语言摘要与独立发布必须可复现 | 所有实现通过共享正反向向量；兼容性与完整性分别治理 |

当前候选版本仍未冻结。以上决策只证明架构边界；生产批准还需要 Phase 0 实现、故障注入、隔离、容量和恢复证据。
