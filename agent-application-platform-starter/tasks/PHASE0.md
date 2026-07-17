# Phase 0 — v0.9.0 产品纵向链路

Phase 0 实现一条真实的 Manus-like Conversation 链路。只有目录骨架或契约代码不算完成。只有本验收计划通过后才能开始 Phase 1。

## 0A：Business 授权与 Conversation

实现参考 Business User/Organization/Free-Pro Membership、不可变 EntitlementRevision、幂等 QuotaReservation 和 CommercialAuthorizationSnapshot。创建 Conversation/Workspace，签发 Conversation WorkSession，然后提交使用新 Grant 的 Turn，并原子追加 Message、创建 WorkOrder 和 Workflow Start Outbox。

证明重复 Conversation/Turn 请求不会创建第二个 Message、WorkOrder、Reservation 或消费记录。

## 0B：执行链路

实现 PostgreSQL/Outbox -> Temporal WorkOrder Workflow -> ProviderResolution/RunManifest -> DeerFlow AgentRuntimeProvider -> DeerFlow Built-in Sandbox `primary-code` -> Invocation/Sandbox Attempt Ledger -> CanonicalEvent -> Artifact Staging/Finalize -> Delivery/TechnicalUsage Settlement。

证明：

- 后续输入、Interrupt、Pause/Resume、Approval 和 Cancel 使用仅追加 Runtime Command 与 Fencing；
- Worker/Adapter 重启后可以从外部状态或 Checkpoint 恢复；
- Provider 响应丢失后进入对账；
- 旧 Attempt/Runtime Command 结果会被拒绝；
- Redis 丢失不会导致事实丢失。

## 0C：Experience 与 nexu 集成

至少将一个 html-anything Template 作为 ExperienceCatalogEntry + 不可变 TemplateRevision 导入。Scenario UI 通过 Catalog 发现它，WorkOrder 选择其精确摘要，RunManifest 绑定已认证的 Template ProviderRevision，DeerFlow 通过受治理的 Skill/Tool 路径消费它。

将 html-to-pptx 或 html-video 实现为一个生成派生 ArtifactVersion 的 Converter Provider。Scenario 或 Workbench 逻辑中不得硬编码 Plugin ID。

## 0D：实时 Runtime 与回放

通过 Runtime Gateway 打开 Terminal RuntimeSession，并由 Platform 管理录制。Finalize 至少两个不可变 Chunk，以及一个与 `work_sequence` 对齐的回放 Manifest。UI 必须能在没有实时 Sandbox 的情况下回放 Chat、Plan、Timeline、Terminal、Files 和 Artifact。

在 Capture、Consent、Redaction 和容量测试通过前，Browser/Desktop 录制继续由 Capability Gate 控制。

## 0E：安全与故障证据

- ExecutionGrant/CommercialAuthorization 不得超限，也不得跨 Turn 重用。
- DeerFlow 不得绕过 Model/Tool/Egress Gateway。
- Runtime Recording 不得在 Event/Temporal/PostgreSQL 中持久化 Secret、原始 Token 或未加密字节。
- Template 选择不得引用隐藏、已撤销或未准入的 Revision。
- Conversation/Message/Command/Recording/Catalog 数据库约束通过并发测试。
- Temporal Replay、重复/丢失响应、NetworkPolicy/RBAC/Pod Security 和最小备份恢复演练通过。

完成 Phase 0 仍不代表生产就绪；容量、SLO、全面故障注入和生产恢复需要单独批准。
