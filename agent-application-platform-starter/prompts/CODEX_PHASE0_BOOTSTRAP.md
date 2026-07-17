# Codex Phase 0 Bootstrap — v0.8.6

你正在实现 Agent Application Platform。先阅读 `START_HERE.md`、`AGENTS.md`、`docs/42_V084_REVIEW_RESOLUTION.md` 和 `tasks/PHASE0.md`。

## Admission 前置

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

任一 Gate 失败就停止实现并修复契约/工具链。Git 根 Workflow 未激活、公共 CI 未通过或未批准冻结时，不得开始 Phase 0；不得开始 Phase 1。

## 实现顺序

1. 数据库 migration 与约束；
2. ExecutionGrant、Idempotency、WorkOrder/Outbox；
3. Temporal 最小 Workflow；
4. ProviderResolution、immutable Revision + Admission Snapshot、RunManifest；
5. Invocation/Sandbox Operation + append-only Attempt + fencing；
6. DeerFlow Runtime 与 Built-in Sandbox Adapter；
7. Event、Artifact Staging/Finalize、Delivery；
8. UI history replay；
9. duplicate/lost-response/replay/security tests。

## 禁止事项

- 不得把 Business 用户、订单、支付、商业配额复制为平台事实源；
- 不得宣称 Exactly-once；
- 不得用 Redis 保存唯一事实；
- 不得将 Pod/Namespace/Container/VM/Node/raw endpoint 写入稳定模型；
- 不得回写 ProviderRevision 认证状态；
- 不得绕过 Capability/ProviderResolution 写死 DeerFlow、html-anything 或 html-to-pptx；
- 不得只用文档实现“必须”。

每个提交都要说明：影响的冻结边界、文档/契约/实现/生产验证分类、增加的强制机制、实际运行的 Gate，以及尚未证明的生产性质。
