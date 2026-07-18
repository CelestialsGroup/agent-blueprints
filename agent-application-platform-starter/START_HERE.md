# 从这里开始

Agent Application Platform v0.9.0 是产品边界候选版本。它定义 Manus-like Agent 平台的领域边界、公共契约和实施约束，但尚未冻结，也不代表产品已经实现或具备生产可靠性。

## 当前成熟度

| 层级 | 当前状态 | 说明 |
|---|---|---|
| 架构设计 | 候选完成 | 核心所有权、Provider 模型、Conversation、Sandbox、Recording 和 Business 交接已有设计 |
| 契约验证 | 本地通过 | Schema、OpenAPI、状态机、正反向夹具、跨语言 JCS 和语义 Gate 已通过本地验证 |
| 产品实现 | 未完成 | 当前仓库主要包含文档、契约和验证工具，没有真实 Agent Platform 纵向链路 |
| 生产证明 | 未开始 | 故障注入、容量、安全隔离、Temporal Replay 和备份恢复仍缺运行证据 |

“契约验证通过”只表示候选契约内部可接纳，不等于实现完成，更不等于生产就绪。

## 阅读顺序

1. `AGENTS.md`：实施规则、所有权和禁止项。
2. `docs/00_ARCHITECTURE_BASELINE.md`：系统分层和当前架构摘要。
3. `docs/DECISIONS.md`：当前有效的关键决策。
4. `docs/README.md`：详细规范索引和事实源层级。
5. `tasks/PHASE0.md`：唯一 Phase 0 实现与验收路线。
6. `prompts/CODEX_PHASE0_BOOTSTRAP.md`：实现代理入口。

Schema、OpenAPI、状态机、数据库不变量和验证 Gate 高于叙述性文档。发生冲突时，应先修复低层事实源，再同步说明文档。当前 0A 契约闭合具备进入实现的候选条件；GitHub CI、仓库准入和冻结基线在后续阶段独立处理。

## 已确定的边界

- Business Application 拥有 User、Organization、Membership、Product、Order、Payment、Entitlement 和商业额度。
- Agent Platform 拥有 Conversation、WorkOrder、Workflow、Event、Artifact、Technical Usage、Provider、Sandbox、RuntimeRecording 和 Experience Catalog。
- Agent Runtime 和 Sandbox 只能通过带解析证据的 Provider Port/Resolution 接入，框架或基础设施私有模型不得进入稳定内核。
- ExecutionGrant 精确绑定请求 Contract/Digest Profile；Conversation Branch 精确绑定 WorkspaceRevision Head。
- Sandbox 由 Capability 按需创建；轻量 Run 可以没有 Sandbox，非空 Slot 只引用统一 ProviderResolution。
- RuntimeRecording 原始证据只读；调试和重跑必须创建新的授权与执行链路。
- 系统只承诺至少一次投递、幂等、Fencing、对账、事务 Outbox 和不可变版本，不承诺全局 Exactly-once。

## 本地验证

```bash
./scripts/bootstrap_contracts.sh
make validate-architecture
```

支持 CPython 3.11-3.13、Node 22.16 和 Go 1.23.2。`make validate-all` 的仓库供应链与 CI 准入留到正式冻结准备阶段；实际结果与计数见 `CONTRACT_VALIDATION_REPORT.md`。

## 下一里程碑

先按 `tasks/PHASE0.md` 实现持久化脊柱和 Native Minimal Runtime Probe，再进入 Business 纵向链、主 Runtime/Sandbox、Runtime Gateway/Recording、nexu Provider、第二可部署 Runtime、故障注入和最小恢复证据。GitHub CI 只在正式冻结前补齐。
