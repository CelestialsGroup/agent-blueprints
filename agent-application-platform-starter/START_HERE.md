# START HERE

这是 Agent Application Platform **v0.9.0 Product Boundary Candidate**。v0.8.6 及更早版本不是实施基线，仓库不再保留其审查快照。

## Current status

- Conversation/Branch/Turn 与 Conversation-owned Workspace 已闭合。
- DeerFlow 通过独立 AgentRuntimeProvider 接入，私有 Thread/Run/Checkpoint 不进入平台模型。
- RuntimeRecording、Experience Catalog、Template/Skill/Renderer Provider 和 Business CommercialAuthorization 已闭合。
- Conversation、AgentRuntimeRun、RuntimeRecording、Invocation、SandboxOperation、WorkOrder 都有权威状态机或持久化状态约束。
- 本地 Contract Gate 已通过；候选版本未冻结，也不代表 Production Ready。

## Authority

按以下顺序阅读：

1. `AGENTS.md`：实施规则和禁止项。
2. `docs/00_ARCHITECTURE_BASELINE.md`：当前架构摘要。
3. `docs/DECISIONS.md`：当前有效的关键决策及理由。
4. `docs/README.md`：按主题进入详细规范。
5. `tasks/PHASE0.md`：唯一实现与验收路线。
6. `prompts/CODEX_PHASE0_BOOTSTRAP.md`：实现代理入口。

Schema、OpenAPI、状态机、数据库不变量和验证 Gate 高于叙述性文档。

## Validation

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

支持 CPython 3.11–3.13、Node 22.16、Go 1.23.2。结果和实际计数见 `CONTRACT_VALIDATION_REPORT.md`。

## Stable boundary

Business Application 拥有 User、Membership、Product、Order、Payment、Entitlement 和 Commercial Quota Reservation/Settlement。Agent Platform 拥有 Conversation、Message、WorkOrder、Workflow、Invocation、Event、Artifact、Technical Usage、Delivery、Provider、Sandbox、RuntimeRecording 与 Experience Catalog。双方只能通过版本化契约集成。

稳定内核不得保存 Pod、Namespace、Container、VM、Node 或原始 Runtime Endpoint；这些字段只属于 Provider Adapter 私有模型。

生产批准仍需要真实 migrations、DeerFlow/Sandbox Adapter、Temporal Replay、故障注入、安全隔离、容量和备份恢复证据。
