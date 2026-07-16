# v0.4 到 v0.5 的调整

## Kubernetes 成为正式架构基线

- Agent API 强制无状态。
- 增加 Runtime Gateway。
- 增加 Per-Run/Workspace Sandbox Pod 模型。
- 增加多 Task Queue Worker 部署。
- 增加数据库原子 Event Sequence。
- Redis 仅作为事件唤醒，不是事实源。
- 增加分布式 EditSession。
- 增加 Provider Health Aggregator 与 draining。
- 增加 Migration Job 和 Expand/Migrate/Contract。
- 增加 Probe、PDB、NetworkPolicy、Resource 和优雅退出。
- 增加 Cell/Cluster/Region 字段预留。
- 增加多节点架构验收与初始 SLO。
- Plugin Runtime Mode 从 sidecar 收敛为：
  service、job、sandbox_cli、mcp、remote_service。
- html-anything 改为 Service Plugin。
- html-to-pptx 改为 Job Plugin。
