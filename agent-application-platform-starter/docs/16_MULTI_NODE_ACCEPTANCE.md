# 多节点架构验收

## API

- [ ] agent-api 至少 3 个副本时，任意 Pod 都能读取同一 WorkOrder。
- [ ] 删除任意 API Pod 不影响 Workflow 执行。
- [ ] SSE 重连到不同 Pod 后可从 after_work_sequence 恢复。
- [ ] 不依赖 Sticky Session。

## Workflow

- [ ] Worker 多副本不会重复执行非幂等 Activity。
- [ ] Worker Pod 被杀死后 Workflow 可恢复。
- [ ] Task Queue 可以独立扩缩容。
- [ ] Cancellation 在 Worker 重启后继续。

## Event

- [ ] 多 Pod 并发写入不会产生重复 sequence。
- [ ] Provider 重复事件被幂等去重。
- [ ] Redis 通知丢失时 SSE 仍可从 PostgreSQL 补拉。
- [ ] Projection 可重建。

## Sandbox

- [ ] Sandbox Pod 与 API/Worker 生命周期独立。
- [ ] Worker 重启后可继续管理已有 Sandbox。
- [ ] Sandbox 有 TTL、Resource Limit 和 NetworkPolicy。
- [ ] 不同 Tenant 不能互访。

## Artifact

- [ ] EditSession 存储在共享状态中。
- [ ] 两个 Pod 同时 Commit 时能检测版本冲突。
- [ ] Draft 不依赖 Web Pod 本地磁盘。
- [ ] Conversion Job 可重试且不重复产生交付记录。

## Plugin

- [ ] Plugin 支持 service/job/sandbox_cli/mcp/remote_service。
- [ ] Provider 可以进入 draining。
- [ ] 禁用 Plugin 不影响已固定版本的 Run。
- [ ] 重型转换不会运行在 agent-api Pod 内。

## 运维

- [ ] Migration 使用独立 Job。
- [ ] 所有 Workload 有 Probe、PDB、资源限制和优雅退出。
- [ ] HPA/KEDA 至少使用一个队列指标。
- [ ] 完成一次节点故障恢复演练。

## Security Mediation

- [ ] Agent Runtime 模型调用不能绕过 Model Gateway。
- [ ] 外部 Tool/MCP 调用进入 Invocation Ledger。
- [ ] Sandbox 任意公网出站默认关闭。
- [ ] Sandbox Provisioner 使用独立最小权限 RBAC。
- [ ] NetworkPolicy 不被误认为 FQDN 策略。
- [ ] PDB 之外完成节点故障测试。

## Sandbox Provider Replacement

- [ ] Provider Controller 重启后可恢复 Reconcile。
- [ ] 多 Controller 不接受旧 Fencing Token。
- [ ] Node 故障后 Sandbox 状态可确认或进入 outcome_unknown。
- [ ] Runtime Gateway 不依赖创建 Sandbox 的 Pod。
- [ ] DeerFlow Provider 与 sandbox-runtime Provider 可同时 Canary。
- [ ] Provider draining 不影响锁定旧 Revision 的 Run。
