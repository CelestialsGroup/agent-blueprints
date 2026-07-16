# Phase 0 — Contract-admitted vertical slice

Phase 0 只能在 v0.8.4 Git 根 Workflow 激活、公共 CI Admission 全绿并获批准后开始；Phase 1 在 Phase 0 验收前禁止启动。

## 0A：最小完整链路（优先）

实现一条真实链路：Business 创建 WorkOrder -> 验证/消费 ExecutionGrant -> PostgreSQL/Outbox -> Temporal Workflow -> ProviderResolution/RunManifest -> DeerFlow Runtime -> DeerFlow Built-in Sandbox `primary-code` -> Invocation/Sandbox Attempt Ledger -> Canonical Event -> Artifact Staging/Finalize -> Delivery。

必须证明：

- 重复请求不产生第二个逻辑 WorkOrder/Invocation/Operation；
- Worker 重启可 Replay，PostgreSQL 查询态可重建；
- Provider 响应丢失进入 reconciliation，不会永久卡住；
- fencing 拒绝旧 Attempt；
- Artifact 未 finalize 不可见；
- Redis 清空不损失事实；
- UI 可回放 Chat、Plan、Timeline、Terminal、Files 与 Artifact。

## 0B：稳定内核骨架

实现 Identity/AuthZ、ExecutionGrant、WorkOrder/Workspace、Workflow State、Invocation Ledger、Canonical Event、Artifact、Technical Usage、Delivery、Audit、Provider Registry/Resolution、Sandbox Registry/Lease/Operation/RuntimeSession。

数据库 migration 必须落实 `docs/26_DATA_MODEL_INVARIANTS.md`，包括 append-only ProviderDecision、Sandbox Attempt/Reconciliation/ManualReview 和 Slot 唯一性。

## 0C：Provider Ports

- Agent Runtime Port：首个 Adapter 为 DeerFlow；
- Sandbox Provider Contract：首个 Adapter 为 DeerFlow Built-in，未来 `sandbox-runtime` 无需改变稳定内核；
- Plugin/Converter Port：html-anything、html-to-pptx 作为可独立安装 Provider；
- 所有选择通过 CapabilityDefinition -> ProviderResolution -> immutable Revision/Admission Snapshot。

## 0D：平台安全和部署

Kubernetes 双 Namespace、Default Deny、受控 Egress Gateway、最小 RBAC、non-root/read-only/drop ALL、短期 Runtime Session Gateway Route。稳定内核禁止后端标识字段。

## 0E：验收证据

- 公共 Contract CI；
- migration/constraint tests；
- Temporal replay tests；
- at-least-once duplicate and lost-response tests；
- Sandbox Conformance；
- NetworkPolicy/RBAC/Pod Security 实际测试；
- backup/restore drill 的最小证据。

Phase 0 完成仍不等于 Production Ready；容量、SLO、全面故障注入和生产恢复演练另行审批。
