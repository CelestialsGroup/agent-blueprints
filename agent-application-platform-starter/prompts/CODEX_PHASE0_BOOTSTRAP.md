# Codex Phase 0 启动指引 — v0.9.0

阅读 `START_HERE.md`、`AGENTS.md`、`docs/00_ARCHITECTURE_BASELINE.md`、`docs/DECISIONS.md` 和 `tasks/PHASE0.md`。

## 准入优先

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

开始实现前修复所有契约失败。在每个 Phase 0 验收项都取得运行证据前，不得开始 Phase 1。

## 实现顺序

1. Conversation/Message/Turn/Workspace Migration 与约束。
2. CommercialAuthorizationSnapshot、Grant 消费和额度 Reservation/Settlement 参考流程。
3. WorkOrder/Outbox 与 Temporal Workflow。
4. ProviderResolution、不可变 Revision/Admission/Experience 快照和 RunManifest。
5. DeerFlow AgentRuntimeProvider Adapter，以及 Command/Event/Checkpoint 私有映射。
6. DeerFlow Built-in Sandbox Adapter 和 Invocation/Sandbox Ledger。
7. CanonicalEvent、Artifact Staging/Finalize、RuntimeRecording 和 Delivery。
8. html-anything Catalog 导入，以及一个 Converter Provider。
9. 多轮 Workbench 和离线历史回放。
10. 重复请求、响应丢失、回放、安全和备份测试。

## 禁止事项

- 不得把 Business 的 User、Membership、Order、Payment 或 Balance 事实复制到 Agent Platform。
- 不得把 WorkOrder 当作无边界 Conversation，也不得让 Workspace 只属于 WorkOrder。
- 不得在 DeerFlow Adapter 之外暴露 Thread/Run/Checkpoint Payload。
- 不得把实时 Runtime 字节持久化到 Event、Temporal 或 PostgreSQL。
- 不得只用可变字符串标识 Template，也不得硬编码 nexu Plugin ID。
- 不得加载任意远程 JavaScript，也不得授予 UI Extension 宿主 Cookie、Token 或 DOM 访问权限。
- 不得宣称 Exactly-once 或生产就绪。

每个 Commit 都必须说明边界影响、文档/契约/实现/证据分类、新增的强制措施、已运行的测试和尚未证明的属性。
