# v0.9.0 架构验收

## 契约准入

- [ ] `./scripts/bootstrap_contracts.sh` 在公共 Registry 和 Python 3.11/3.13 成功。
- [ ] `make validate-all` 全绿，包括 Python/Node/Go Strict I-JSON。
- [ ] Monorepo 的 Git 根 Workflow 与 `.gitignore` 已提交，根 `.DS_Store` 未被跟踪，`AGENT_PLATFORM_CONTRACT_ROOT` 与受保护兼容性变量已配置。
- [ ] 5 个 OpenAPI 均为 0 个错误、0 个警告，且 Bundle 结果确定。
- [ ] 契约清单的 Python/Node 结果一致。
- [ ] 兼容性检查明确为受保护冻结基线通过，或由受保护变量显式批准首次冻结前使用 N/A；缺失配置时 CI 必须失败。
- [ ] 供应链 Gate 全绿。

## 边界验收

- [ ] Business/Platform 所有权无交叉事实源。
- [ ] Provider 选择只经 Capability/Resolution/不可变 Revision/Admission。
- [ ] ProviderRevision 使用 Implementation/BuildProvenance/Port Binding；Runtime/Sandbox 公共模型不要求 Plugin 字段。
- [ ] WorkOrder、Tenant-qualified WorkflowRun、Root/Sub-agent AgentRun、RunManifest 和 AgentRuntimeRun 的基数与引用闭合，Runtime 只引用一个 ProviderResolution。
- [ ] Sandbox 多 Slot 唯一且主 Slot 存在。
- [ ] 稳定模型不包含 Pod/Namespace/Container/VM/Node/原始 Endpoint。
- [ ] Conversation 拥有持久 Workspace；每个可执行 Turn 都绑定 Message/WorkOrder/Grant/RunManifest。
- [ ] Agent Platform 不依赖任何单一 Agent 框架；所有 Runtime 只通过 AgentRuntimeProvider v1 接入，且框架私有 Agent/Thread/Run/Checkpoint 不泄漏到稳定模型。
- [ ] 至少两个 Runtime Adapter 通过 `runtime-core-v1`；主链路 Runtime 通过 `runtime-general-v1 + governed-v1`。第二个可以是功能最小实现，但必须证明公共 Command/Event/Artifact/Usage 与 Workbench 消费路径不依赖 DeerFlow。
- [ ] 每个 Run 锁定一个 Agent Runtime ProviderRevision；Fallback 只用于未开始的新 Run，原生 Checkpoint 不被错误宣称为跨框架可移植。
- [ ] Experience 选择绑定不可变 Catalog Revision 和 ProviderRevision。
- [ ] RuntimeSession 实时传输与 RuntimeRecording 回放是相互独立的授权资源。
- [ ] Terminal Runtime Gateway 使用类型化 v1 Frame、Generation、按 Channel Cursor/Sequence、ACK/Window、Control ID + Digest、Recording Checkpoint 和显式 Replay Gap。
- [ ] CommercialAuthorizationSnapshot 由 Business 拥有，且无权修改 Platform TechnicalUsage。
- [ ] MeterDefinition、TechnicalUsage、UsageReport 和 BusinessSettlementEnvelope 不包含价格或余额事实；Envelope 嵌入连续编号的完整 Final/Correction UsageReport，Partial/Estimated 不能作为 Confirmed 结算。
- [ ] PolicyDecision 从全部规则按 `deny > ask > allow` 推导，Approval、Sandbox、Gateway 和 Invocation 无绕过路径。

## 可靠性验收

- [ ] Invocation 与 SandboxOperation 都有逻辑记录、仅追加 Attempt、Fencing 和对账机制。
- [ ] Invocation Attempt 编号从 1 连续、Fencing Token 唯一且严格递增，`current_attempt_id`/`attempt_count` 与完整历史一致。
- [ ] 聚合、ReconciliationCase 和 ManualReviewDecision 的 ID/版本/摘要/证据/结果形成可执行引用闭环；非幂等重试/Abandon 无绕过路径。
- [ ] 未知结果可到达成功/失败/重试/人工复核/`abandoned`，不存在永久悬空状态。
- [ ] Outbox/Inbox、Event Sequence、Artifact Staging/Finalization 和 Delivery Attempt 有数据库约束。
- [ ] Conversation Message、Agent Runtime Command 和 RuntimeRecording Chunk 序列具有数据库约束与语义负向测试。
- [ ] 核心 Runtime Event Payload、RunManifest-bound EventTypeRegistry 和 Runtime/Sandbox/Gateway/Capability Conformance Suite 有内容摘要、机器可执行 Schema 与负向测试。
- [ ] Conversation、AgentRuntimeRun、RuntimeRecording 的状态集合与权威 JSON 状态机一致，终态/取消/未知结果约束由语义 Gate 执行。

## 生产验收（不属于契约 Gate）

- [ ] Phase 0 真实纵向链路、Temporal Replay、故障注入、安全隔离、容量/SLO、备份恢复演练和 Provider 一致性均有运行证据。
- [ ] API/Worker 多副本不依赖粘性 Session 或 Pod 本地权威状态；跨 Pod SSE 可从 `work_sequence` 恢复。
- [ ] Redis 通知丢失、Provider/Controller 重启、Sandbox Node 故障和 Runtime 重路由均能恢复或进入可对账状态。
- [ ] 所有生产工作负载具备 Probe、资源限制、PDB、Topology、最小 RBAC、NetworkPolicy 和优雅 Draining 证据。
