# Kubernetes 多节点运行规范

## 1. 目标

本规范确保 Agent Platform 在 Kubernetes 多副本、多 Worker、多 Runtime 节点环境中仍然具备：

- 无状态 API
- 持久化 Workflow
- 可恢复 Agent Run
- 不重复执行
- 不丢失事件
- Artifact 一致性
- 安全的 Sandbox 隔离
- 独立扩缩容
- 灰度、Drain 和滚动升级
- 节点故障后恢复

## 2. 逻辑部署

```text
Ingress / API Gateway
        │
        ├── Business API
        └── Agent Workbench
                 │
        agent-api Deployment (N)
                 │
        ┌────────┼───────────┬──────────────┐
        │        │           │              │
 PostgreSQL   Temporal     Object Store    Redis
        │        │                           │
        │   agent-worker Deployments (N)     │
        │        │                           │
        └────────┼───────────────────────────┘
                 │
       Runtime Gateway / Session Router
                 │
       ┌─────────┼─────────────┐
       │         │             │
 DeerFlow     Plugin        Sandbox Pods
 Service      Services/Jobs  per Run/Workspace
```

## 3. Workload 分类

### Stateless Deployment

- agent-api
- agent-workbench
- runtime-gateway
- lightweight renderer service
- plugin registry reader

### Temporal Worker Deployment

按 Task Queue 分开：

- orchestration
- agent-runtime
- sandbox-provision
- artifact-preview
- artifact-conversion
- delivery
- maintenance

### Runtime Service

- DeerFlow Runtime
- html-anything
- 长驻 Renderer
- MCP Gateway

### Kubernetes Job

适合：

- html-to-pptx
- PDF 渲染
- 视频渲染
- 大型一次性转换
- 数据迁移
- 回填

### Per-Run Sandbox Pod

适合：

- Terminal
- Browser
- Coding Agent
- 构建
- 用户工作区

## 4. Agent API 无状态规则

Agent API Pod 内禁止保存权威状态：

- WorkOrder state
- Run state
- Event sequence
- Idempotency record
- EditSession
- Provider health
- WorkSession
- Capability binding

权威状态必须位于：

- PostgreSQL
- Temporal
- Object Storage

Redis 只能保存：

- 缓存
- Presence
- 限流
- 非权威事件唤醒通知

## 5. Event 实时分发

事件先持久化到 PostgreSQL，再发送非权威通知：

```text
Provider Event
 -> Event Ingestor
 -> PostgreSQL transaction
 -> Outbox
 -> Redis Pub/Sub wake-up
 -> SSE Pod catch-up by sequence
```

Redis 通知丢失不影响正确性。

SSE Pod 收到通知后始终从 PostgreSQL 按 sequence 查询。

## 6. Event Sequence

禁止在 Pod 内使用内存计数器。

每个 WorkOrder 在数据库保存：

```text
next_event_sequence
```

Event Ingestor 在事务中原子分配：

```sql
UPDATE work_orders
SET next_event_sequence = next_event_sequence + 1
WHERE id = $1
RETURNING next_event_sequence;
```

同一 Provider 原始事件通过唯一 source cursor 去重；aggregate_sequence 另行按 Aggregate 原子分配。

## 7. Runtime Session Routing

Terminal、Browser、Desktop、Port-forward 等双向连接通过 Runtime Gateway：

```text
runtime_session_id
 -> tenant_id
 -> work_order_id
 -> sandbox_id
 -> sandbox_connection_generation
 -> provider_route_reference
 -> expires_at
```

`provider_route_reference` 是内部不透明引用，不是 Pod IP、Node IP 或 VM 地址。

Runtime Gateway 通过 Sandbox Provider Adapter 解析内部 Endpoint，并且：

- 不依赖 Ingress Sticky Session
- 不把 Backend Endpoint 返回浏览器
- Token 到期、Session 撤销或 Generation 变化时断开
- Sandbox 重建后重新解析 Route

## 8. Sandbox 生命周期与后端隔离

Sandbox 不绑定创建它的 API、Worker 或 Controller Pod。

稳定内核的 SandboxRegistry 只保存：

- sandbox_id
- tenant_id
- work_order_id
- workspace_id
- sandbox_slot_key
- optional agent_run_id
- provider_instance_id
- provider_revision_id
- desired_state
- observed_state
- generation / observed_generation
- runtime_profile
- resource_profile
- region_id / cluster_id / cell_id
- provider_state_reference（不透明）
- lease_expires_at
- snapshot_reference
- created_at / updated_at

以下字段属于 Provider Adapter 私有模型，禁止进入稳定内核和公共 Contract：

- Kubernetes namespace
- pod_name / pod_uid
- container_id
- node_name
- VM ID
- Firecracker ID
- Apple Container ID
- raw runtime endpoint
- backend credentials

一个 WorkOrder/Workspace 可以拥有多个 Sandbox，例如：

```text
primary-code
browser
desktop
subagent/research-01
subagent/research-02
isolated/untrusted-tool
```

要求：

- 独立 ServiceAccount
- CPU/Memory/Ephemeral Storage limit
- Lease/TTL
- NetworkPolicy + Egress Gateway
- 禁止云元数据和 Kubernetes API
- 禁止跨租户访问
- 幂等清理和 Orphan Reconciliation
- 结束前按 Policy 生成 Workspace Snapshot

## 9. DeerFlow 多副本

目标模式：

- Checkpoint 使用共享数据库
- Artifact 与 Workspace 不依赖 DeerFlow Pod 本地持久盘
- Sandbox 生命周期独立
- DeerFlow API 实例可替换

如果某一版本 DeerFlow 仍具有实例亲和性，Adapter 必须保存：

```text
deerflow_runtime_id
deerflow_thread_id
deerflow_run_id
```

并通过 Runtime Gateway 显式路由。

实例亲和性是兼容模式，不是长期目标。

## 10. Provider Health

Provider Health 由统一聚合器维护，不使用单 Pod 本地判断。

状态：

- healthy
- degraded
- unhealthy
- draining
- disabled

进入 `draining` 后：

- 不接收新任务
- 已锁定的 Run 继续执行
- 完成后可安全下线

## 11. 数据库迁移

禁止应用 Pod 启动时自动执行迁移。

使用独立 Migration Job：

```text
migration job
 -> schema expand
 -> deploy compatible application
 -> data backfill
 -> contract cleanup in later release
```

必须采用 Expand / Migrate / Contract。

## 12. 优雅终止

Pod 收到 SIGTERM：

1. Readiness 立即失败。
2. 停止接收新工作。
3. Worker 停止 Poll 新任务。
4. 等待当前短 Activity 完成。
5. 长任务由 Temporal 恢复。
6. 关闭 SSE/WebSocket。
7. Flush Outbox、日志和 Trace。
8. 在 terminationGracePeriodSeconds 内退出。

## 13. Kubernetes 可靠性配置

所有生产 Workload 必须明确：

- startupProbe
- readinessProbe
- livenessProbe
- Resource Request / Limit
- PodDisruptionBudget
- topologySpreadConstraints
- anti-affinity
- RollingUpdate
- terminationGracePeriodSeconds
- ServiceAccount
- RBAC
- NetworkPolicy
- Pod Security Standards
- HPA 或 KEDA

## 14. 扩缩容指标

不能只使用 CPU。

推荐：

- HTTP request rate
- active SSE connections
- Temporal task queue backlog
- schedule-to-start latency
- pending WorkOrder
- pending Sandbox
- artifact conversion backlog
- active Runtime Session

## 15. Cell 预留

数据模型预留：

- region_id
- cluster_id
- cell_id
- runtime_id

第一阶段使用单 Cell，但禁止把这些值写死在业务逻辑中。

未来：

```text
Global Control Plane
  -> Singapore Cell
  -> China Cell
  -> Europe Cell
```

## 16. Sandbox Provisioner RBAC

只有独立 `sandbox-provisioner` Workload 可以访问 Kubernetes API 创建 Sandbox 资源。

Agent API、普通 Worker、DeerFlow 和 Plugin 默认无 Kubernetes API 权限。

Provisioner 权限限定到专用 Runtime Namespace 和指定资源：

- Pods
- Jobs
- Services
- ConfigMaps（非 Secret）
- PVC（如启用）
- 删除自身创建的资源

禁止 ClusterRole 通配符。

## 17. Egress Policy

Kubernetes NetworkPolicy 只能表达 IP/Port 级策略，不能作为通用 FQDN Allowlist。

Sandbox 和 Plugin 出站通过 Egress Gateway/Proxy：

- DNS Rebinding 防护
- 私网与元数据阻断
- 域名 Allowlist
- TLS/SNI 校验
- 请求审计

## 18. PDB 边界

PodDisruptionBudget 只保护自愿性驱逐，不等同于节点故障或可用性保证。

必须同时使用：

- 多副本
- Topology Spread
- Anti-affinity
- 正确 Readiness
- 数据外置
- 故障恢复测试

## 19. Temporal Worker Deployment

Temporal Worker 使用独立 Worker Deployment Name 和 Build ID。

Kubernetes RollingUpdate 不能替代 Temporal Worker Versioning。

Pinned Workflow 使用 Rainbow/Blue-Green Worker Versions；Auto-Upgrade Workflow 必须保持 Replay Safe。

## 20. sandbox-runtime 接入

sandbox-runtime 作为 Sandbox Provider Service/Controller 部署，不要求实现 Kubernetes CRI。

只有当它替代节点级 container runtime 时才实现 CRI。

普通部署通过 Kubernetes API、RuntimeClass 或专用 VM Backend 调度 Sandbox，并保持 Provider API 稳定。
