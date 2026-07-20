# v0.9.0 架构与实施验收层级

本文件定义验收条件，不记录某次运行状态。实际结果只看 `CONTRACT_VALIDATION_REPORT.md`、实现测试和生产证据，四个层级不得互相替代。

## 1. 本地架构候选 Gate

进入 Phase 0 实现前必须满足：

- `./scripts/bootstrap_contracts.sh` 可在支持的 Python/Node/Go 版本完成；
- `make validate-architecture` 通过，6 个 OpenAPI 为 0 错误/0 警告，Bundle 可重复；
- ExecutionGrant 精确绑定 WorkOrderRequest/ConversationTurnRequest/WorkOrderControlRequest Contract ID、Digest Profile 和请求摘要；
- ConversationBranch 绑定不可变 WorkspaceRevision Head，Fork/CAS/并行 Branch 不共享可变文件头；
- Runtime 与 Sandbox Slot 只引用带 Resolver/Input/Candidate/Evidence/Decision 的 ProviderResolution；
- Resolution 显式绑定 Tenant/ClientApplication/WorkOrder，通过 identity_dependency 声明并绑定 PrincipalContextSnapshot；
- RunManifest 携带实际输入、ContextPackage、ArtifactAccessRequirement、初始 Budget/Policy/Permissions 上限、商业授权 ID/Digest/到期上限、续期规则和四类 Gateway Binding；Runtime Start 携带本 Attempt 的等价/缩权 RuntimeAuthorization/ArtifactGrant，并拒绝内部作用域不闭合或越过商业/ArtifactGrant 时间窗的授权；
- Conversation Turn 与 WorkOrder Control 分离，三个 CAS 所有权域分离，WorkOrder 可从 accepted 直接请求取消；
- 通用 Capability Provider Port/Token 不要求 `plugin_id`，调用绑定 Request Digest、Fencing、Policy、Budget、Permissions 和 Staging；
- WorkspaceContentManifest、Sandbox Slot 选择、Event 来源 Inbox 去重、闭合 Metadata 和 HTTP encoded-body 上限均有可执行契约；
- `contracts/semantic-constraints-v1.json` 覆盖全部关键语义；每个 Contract Gate Check ID 在当前运行中真实执行，并与待实现 DDL/Conformance 责任明确分离；
- RunManifest 支持 Capability 驱动的零或多个 Sandbox，主 Slot 条件闭合；
- 状态机、JCS、Schema、语义负例与 Python/Node 契约清单一致。

该 Gate 不包含 GitHub CI、仓库供应链准入或冻结基线；通过只表示候选架构可以进入实施。

## 2. Phase 0 实现验收

- WorkOrder、Tenant-qualified WorkflowRun、Root/Sub-agent AgentRun、RunManifest 和 AgentRuntimeRun 引用闭合；
- Native Minimal Probe 在 DeerFlow 主实现前完整通过 `runtime-core-v1`；主 Runtime 通过 `runtime-general-v1 + governed-v1`；
- PostgreSQL Constraint 实现 Tenant、Branch WorkspaceRevision、Outbox/Inbox、Sequence、Ledger、Fencing 和 CAS 不变量；
- Business → ExecutionGrant → ConversationTurn → Temporal → Runtime/Sandbox → Event/Artifact/Usage 可重复运行和恢复；
- RuntimeRecording 只持久化经过 Emit-time Scrub/Schema Gate 的 Chunk，并绑定 Redaction Evidence；
- Redis 清空、Worker/Adapter 重启、Provider 响应丢失和旧 Fencing Token 有可执行测试。

该层证明真实组件和纵向链存在，不等于生产可靠性。

## 3. 正式冻结 Gate

冻结 `v0.9.0` 前另行完成：

- 消费者契约、历史载荷回放、双版本互操作和人工兼容性审查；
- Git 根 Workflow、供应链 Gate、公共 CI 和受保护冻结基线变量；
- 两个 Runtime Adapter 完整通过要求的 Conformance Profile；
- 破坏性变更已有版本、迁移窗口和 `DECISIONS.md` 记录。

冻结只承诺公共契约兼容边界，不授予生产批准。

## 4. 生产批准

- Temporal Replay、故障注入、多租户隔离、容量/SLO 和备份恢复有可复现运行证据；
- API/Worker 多副本不依赖粘性 Session 或 Pod 本地权威状态；
- Redis 通知丢失、Provider/Controller/Sandbox Node 故障和 Runtime 重路由可恢复或对账；
- 工作负载具备 Probe、资源限制、PDB、Topology、最小 RBAC、NetworkPolicy 和优雅 Draining 证据。

生产批准是独立决策，不能由契约 Gate、实现完成或 CI 结果自动推导。
