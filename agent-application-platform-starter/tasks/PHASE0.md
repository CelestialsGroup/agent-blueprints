# Phase 0 — v0.9.0 产品纵向链路

Phase 0 实现一条真实的 Manus-like Conversation 链路。只有目录骨架或契约代码不算完成。只有本验收计划通过后才能开始 Phase 1。

## 0A：Business 授权与 Conversation

实现参考 Business User/Organization/Free-Pro Membership、不可变 EntitlementRevision、幂等 QuotaReservation 和 CommercialAuthorizationSnapshot。创建 Conversation/Workspace，签发 Conversation WorkSession，然后提交使用新 Grant 的 Turn，并原子追加 Message、创建 WorkOrder 和 Workflow Start Outbox。

证明重复 Conversation/Turn 请求不会创建第二个 Message、WorkOrder、Reservation 或消费记录。

## 0B：执行链路

实现 PostgreSQL/Outbox -> Temporal WorkOrder Workflow -> ProviderResolution/RunManifest -> 一个已认证 AgentRuntimeProvider -> 一个已认证 SandboxProvider `primary-code` -> Invocation/Sandbox Attempt Ledger -> CanonicalEvent -> Artifact Staging/Finalize -> Delivery/TechnicalUsage Settlement。主链路可以使用 DeerFlow 参考 Adapter 和 DeerFlow Built-in Sandbox Adapter，但不得依赖其私有模型。

证明：

- 后续输入、Interrupt、Pause/Resume、Approval 和 Cancel 使用仅追加 Runtime Command 与 Fencing；
- Worker/Adapter 重启后可以从外部状态或 Checkpoint 恢复；
- Provider 响应丢失后进入对账；
- 旧 Attempt/Runtime Command 结果会被拒绝；
- Redis 丢失不会导致事实丢失。

## 0C：Experience 与 nexu 集成

至少将一个 html-anything Template 作为 ExperienceCatalogEntry + 不可变 TemplateRevision 导入。Scenario UI 通过 Catalog 发现它，WorkOrder 选择其精确摘要，RunManifest 绑定已认证的 Template ProviderRevision，所选 Agent Runtime 通过受治理的 Skill/Tool 路径消费它。

将 html-to-pptx 或 html-video 实现为一个生成派生 ArtifactVersion 的 Converter Provider。Scenario 或 Workbench 逻辑中不得硬编码 Plugin ID。

## 0D：实时 Runtime 与回放

通过 Runtime Gateway 打开 Terminal RuntimeSession，并由 Platform 管理录制。Finalize 至少两个不可变 Chunk，以及一个与 `work_sequence` 对齐的回放 Manifest。UI 必须能在没有实时 Sandbox 的情况下回放 Chat、Plan、Timeline、Terminal、Files 和 Artifact。

在 Capture、Consent、Redaction 和容量测试通过前，Browser/Desktop 录制继续由 Capability Gate 控制。

## 0E：安全与故障证据

- ExecutionGrant/CommercialAuthorization 不得超限，也不得跨 Turn 重用。
- 任何 Agent Runtime（包括 DeerFlow 参考 Adapter）都不得绕过 Model/Tool/Egress Gateway。
- Runtime Recording 不得在 Event/Temporal/PostgreSQL 中持久化 Secret、原始 Token 或未加密字节。
- Template 选择不得引用隐藏、已撤销或未准入的 Revision。
- Conversation/Message/Command/Recording/Catalog 数据库约束通过并发测试。
- Temporal Replay、重复/丢失响应、NetworkPolicy/RBAC/Pod Security 和最小备份恢复演练通过。

## 0F：Agent Runtime 可替换性证明

除主链路 Runtime 外，实现第二个最小 AgentRuntimeProvider Adapter。推荐使用 OpenAI Agents SDK 或 Native Minimal Runtime，但选择不构成平台依赖。

两个 Adapter 必须通过 `runtime-core-v1`，主链路 Runtime 还必须通过 `runtime-general-v1 + governed-v1`，并证明：

- ProviderResolution 可以为新 Run 选择不同 Runtime ProviderRevision；
- Start、Command、Status、Cursor Event、Artifact Staging 和 Usage 使用相同公共契约；
- 同一 Workbench、Timeline 和 RuntimeRecording 可以消费两个 Provider 的标准 Event；
- 稳定 Schema、数据库和 API 不出现任一框架的私有 Agent/Thread/Run/Checkpoint 字段；
- 运行中不会自动切换 Provider，Provider 原生 Checkpoint 不会被宣称为跨框架可移植；
- 不支持的 Capability 明确拒绝，不静默降级。

完成 Phase 0 仍不代表生产就绪；容量、SLO、全面故障注入和生产恢复需要单独批准。
