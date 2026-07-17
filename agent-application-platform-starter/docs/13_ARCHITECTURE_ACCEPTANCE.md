# v0.9.0 Architecture Acceptance

## Contract admission

- [ ] `./scripts/bootstrap_contracts.sh` 在公共 Registry 和 Python 3.11/3.13 成功。
- [ ] `make validate-all` 全绿，包括 Python/Node/Go Strict I-JSON。
- [ ] monorepo 的 Git 根 Workflow 与 `.gitignore` 已提交，根 `.DS_Store` 未被跟踪，`AGENT_PLATFORM_CONTRACT_ROOT` 与受保护 Compatibility 变量已配置。
- [ ] 5 个 OpenAPI 0 error/0 warning 且 Bundle deterministic。
- [ ] Contract Manifest Python/Node 一致。
- [ ] Compatibility 明确为受保护 frozen baseline pass，或由受保护变量显式批准首冻前 N/A；缺失配置时 CI 必须失败。
- [ ] Supply-chain Gate 全绿。

## Boundary acceptance

- [ ] Business/Platform 所有权无交叉事实源。
- [ ] Provider 选择只经 Capability/Resolution/immutable Revision/Admission。
- [ ] Sandbox 多 Slot 唯一且主 Slot 存在。
- [ ] 稳定模型无 Pod/Namespace/Container/VM/Node/raw endpoint。
- [ ] Conversation owns durable Workspace; every executable Turn binds Message/WorkOrder/Grant/RunManifest.
- [ ] DeerFlow implements AgentRuntimeProvider v1 without stable-model Thread/Checkpoint leakage.
- [ ] Experience selections bind immutable Catalog and Provider revisions.
- [ ] RuntimeSession live transport and RuntimeRecording playback are separate authorized resources.
- [ ] CommercialAuthorizationSnapshot is Business-owned and cannot mutate Platform TechnicalUsage.

## Reliability acceptance

- [ ] Invocation 与 SandboxOperation 都有逻辑记录、append-only Attempt、fencing 和 reconciliation。
- [ ] Invocation Attempt 编号从 1 连续、fencing token 唯一且严格递增，current_attempt_id/attempt_count 与完整历史一致。
- [ ] 聚合、ReconciliationCase 和 ManualReviewDecision 的 ID/version/digest/evidence/outcome 形成可执行引用闭环；非幂等 retry/abandon 无绕过路径。
- [ ] unknown outcome 可到达 success/failure/retry/manual review/abandoned，不存在永久悬空状态。
- [ ] Outbox/Inbox、Event sequence、Artifact staging/finalization 和 Delivery Attempt 有数据库约束。
- [ ] Conversation message, Agent Runtime command and RuntimeRecording chunk sequences have database constraints and semantic negative tests.
- [ ] Conversation、AgentRuntimeRun、RuntimeRecording 的状态集合与权威 JSON 状态机一致，终态/取消/未知结果约束由语义 Gate 执行。

## Production acceptance（不属于 Contract Gate）

- [ ] Phase 0A 真实链路、Temporal Replay、故障注入、安全隔离、容量/SLO、备份恢复演练和 Provider Conformance 均有运行证据。
- [ ] API/Worker 多副本不依赖 Sticky Session 或 Pod 本地权威状态；跨 Pod SSE 可从 work_sequence 恢复。
- [ ] Redis 通知丢失、Provider/Controller 重启、Sandbox node failure 和 Runtime reroute 均能恢复或进入可对账状态。
- [ ] 所有生产 Workload 具备 probe、resource limit、PDB、topology、最小 RBAC、NetworkPolicy 和 graceful drain 证据。
