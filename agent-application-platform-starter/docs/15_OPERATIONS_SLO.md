# 运维、SLO 与故障恢复

## SLI

### Access

- WorkOrder accept availability/latency
- Token validation failure
- Grant replay/conflict
- WorkSession exchange/revocation

### Workflow/Invocation

- Temporal schedule-to-start
- Workflow completion/stuck count
- Invocation success/retry/outcome_unknown
- Reconciliation age

### Execution Mediation

- Model Gateway first-token latency
- Token budget enforcement
- Tool approval latency
- Egress deny/error

### Event

- Event append latency
- work_sequence contention
- SSE lag/reconnect/cursor-expired
- Projection lag

### Runtime/Sandbox

- DeerFlow start/recovery
- Sandbox provisioning/cleanup
- Runtime Gateway active connections
- Provider health/draining

### Artifact/Delivery

- Ingest scan latency
- Preview/edit/convert success
- Artifact commit conflict
- Webhook success/retry/DLQ age

## 初始 SLO

- Agent Access API 月可用性：99.9%
- 已接受 WorkOrder 持久化丢失：0
- P95 WorkOrder Accept：< 500ms
- P95 Durable Event Lag：< 3s
- P95 WorkSession Exchange：< 500ms
- Provider outcome_unknown 24 小时内完成对账：99%
- Delivery Webhook 24 小时最终送达：99.9%

这些是初始目标，需在容量测试后按部署等级修订。

## 恢复演练

- PostgreSQL PITR
- Temporal Persistence/Replay
- Object Storage
- Signing/Verification Keys
- Worker 全量重启
- DeerFlow Runtime 滚动升级
- Model/Tool Gateway 故障
- Provider Drain
- Callback DLQ
- Event Projection 重建
- WorkSession 全量撤销

## 故障关联字段

- tenant_id
- client_app_id
- work_order_id
- workflow_run_id
- invocation_id/attempt_id
- agent_run_id
- provider_revision_id
- cluster_id/cell_id

## 6. Sandbox SLI

- Sandbox create success rate
- Provisioning latency P50/P95/P99
- Ready-to-first-exec latency
- Exec success/cancel/outcome-unknown rate
- Lease expiration cleanup latency
- Orphan Sandbox count
- RuntimeSession connect success/latency
- Snapshot success/throughput
- Provider event lag
- Fencing rejection count
- Cross-tenant security violation count
- Sandbox cost/WorkOrder

初始目标建议：

- Create API 可用性：99.9%
- 已接受 Create 最终可确认：99.99%
- Standard Sandbox P95 provisioning：< 30 秒
- Lease 到期 P95 清理：< 5 分钟
- Orphan Sandbox：0 长期未处理
- RuntimeSession P95 connect：< 3 秒
