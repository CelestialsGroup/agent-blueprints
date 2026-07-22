# Codex Phase 0 启动指引 — v0.9.0

按顺序阅读 `AGENTS.md`、`START_HERE.md`、`docs/00_ARCHITECTURE_BASELINE.md`、`docs/DECISIONS.md`、`docs/README.md` 和 `tasks/PHASE0.md`。

## 准入优先

```bash
./scripts/bootstrap_contracts.sh
make validate-architecture
```

开始实现前修复所有本地架构契约失败。`make validate-all` 的 GitHub CI、仓库供应链和冻结基线准入留到正式冻结准备阶段，不阻止 Phase 0 候选实现。在每个 Phase 0 验收项都取得运行证据前，不得开始 Phase 1。

## 实现顺序

1. 完成 `tasks/PHASE0.md` 的 0A 最小契约闭合，不带着未定义的 Run、Event、Usage 或 Gateway 关系进入实现。
2. 实现 PostgreSQL Migration、Constraint、Outbox/Inbox、Temporal、对象存储基础和无 Sandbox Native Runtime Core；它是产品主 Runtime 的第一阶段，不是一次性 Probe。
3. 实现 CommercialAuthorization、Grant 消费、Reservation/Settlement 和 Conversation Turn 原子链路。
4. 扩展自研 Native Runtime 到 General/Governed Profile，并实现平台自己的 SandboxProvider；第三方 Agent 项目只作参考。
5. 闭合 Invocation/Sandbox Ledger、CanonicalEvent、Artifact Staging/Finalize、TechnicalUsage 和 Delivery。
6. 实现多轮 Workbench、Runtime Gateway、Terminal Recording 和离线历史回放。
7. 导入 html-anything Catalog Experience，并实现一个 Converter Provider。
8. 实现与 Native Runtime 不共享内部执行包的最小 Reference Runtime Provider，并完成双 Provider Port 一致性测试；不以此引入第三方框架适配。
9. 完成重复请求、响应丢失、旧 Fencing、Replay、隔离、容量和备份恢复证据。

## 禁止事项

- 不得把 Business 的 User、Membership、Order、Payment 或 Balance 事实复制到 Agent Platform。
- 不得把 WorkOrder 当作无边界 Conversation，也不得让 Workspace 只属于 WorkOrder。
- 不得在任何 Runtime Adapter 之外暴露框架私有 Agent/Thread/Run/Checkpoint Payload。
- 不得将 DeerFlow、LangGraph、OpenAI Agents SDK 或任何其他框架设为稳定内核的前置依赖或唯一实现。
- 不得把实时 Runtime 字节持久化到 Event、Temporal 或 PostgreSQL。
- 不得只用可变字符串标识 Template，也不得硬编码 nexu Plugin ID。
- 不得加载任意远程 JavaScript，也不得授予 UI Extension 宿主 Cookie、Token 或 DOM 访问权限。
- 不得宣称 Exactly-once 或生产就绪。

每个 Commit 都必须说明边界影响、文档/契约/实现/证据分类、新增的强制措施、已运行的测试和尚未证明的属性。
