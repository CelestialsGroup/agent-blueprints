# 技术栈与 Kubernetes 部署

## 技术基线

### Agent Platform 技术栈

- Go
- PostgreSQL
- Temporal
- 兼容 S3 的 Object Storage
- Redis：缓存、在线状态、限流、Event 唤醒
- OpenAPI 3.1.1 + JSON Schema 2020-12

### Web 技术栈

- React / Next.js
- 独立部署的 Agent Workbench
- Cookie 认证的 SSE
- Runtime Gateway WebSocket

### Runtime 与治理组件

- 一个或多个独立 Agent Runtime Provider 服务
- DeerFlow Runtime 服务（可选参考 Adapter）
- 第二个最小 Runtime 服务（冻结前可替换性验证）
- Model Gateway
- Tool/MCP Gateway
- Sandbox 出站 Gateway
- Artifact Gateway
- Plugin 服务 / Job / Sandbox CLI / MCP / 远程服务

## Kubernetes 工作负载

```text
agent-api Deployment
agent-workbench Deployment
runtime-gateway Deployment
model-gateway Deployment
tool-gateway Deployment
egress-gateway Deployment

agent-worker-orchestration Deployment
agent-worker-runtime Deployment
agent-worker-sandbox-provision Deployment
agent-worker-preview Deployment
agent-worker-conversion Deployment
agent-worker-delivery Deployment
agent-worker-maintenance Deployment

agent-runtime-provider-* Deployment
deerflow-runtime Deployment（可选参考实现）
agent-runtime-secondary Deployment（冻结前一致性验证）
html-anything Deployment
html-to-pptx Job
sandbox Pod / Job
migration Job
```

Agent API 和普通 Worker 不保存权威 WorkOrder、Event 序列、Session、Provider 健康状态或 Sandbox 路由；这些状态位于 PostgreSQL、Temporal 和 Object Storage。Redis 只用于缓存、限流、在线状态和持久化后的 Event 唤醒，丢失 Redis 不影响正确性。

Runtime Gateway 通过不透明 Provider 路由代理 Terminal/Browser/Desktop，禁止向前端返回 Pod/VM/原始 Endpoint，也不依赖粘性 Session。只有独立 Sandbox Provisioner/Controller 拥有最小范围 Kubernetes API 权限。

## 数据服务

Business 与 Agent 使用独立 PostgreSQL。

生产使用高可用：

- PostgreSQL
- Temporal Persistence
- Object Storage
- Redis

## 模块化单体

Agent API 内先按模块拆分：

```text
access
tenant
workorder
workflow
invocation
scenario
capability
plugin
runtime
event
artifact
usage
delivery
audit
```

代码边界不要求第一阶段立即拆成微服务。

## 网络通信

- Business -> Agent：Service OAuth HTTP
- Browser -> Workbench：WorkSession Cookie + HTTP/SSE/WebSocket
- Agent -> Business：签名 Webhook + Outbox
- Agent -> Plugin 服务：mTLS + Invocation Token
- Worker -> Plugin Job：Kubernetes Adapter + Manifest 协议
- Agent Runtime -> Model/Tool/Egress：强制 Gateway
- Workflow：Temporal

不同语言的 Runtime Provider 作为独立 Workload 部署；Go Agent Platform 不直接链接其 Python/TypeScript 框架依赖。每个 ProviderRevision 独立发布、扩缩容、Canary 和 Draining。

## 发布

数据库：

```text
扩展 Migration
 -> 部署向后兼容代码
 -> 数据回填
 -> 验证
 -> 在后续版本清理契约
```

Workflow 发布：

- Worker Deployment/Build ID
- Pinned 或 Auto-Upgrade 策略
- Replay Test
- Canary/Drain

应用 Pod 禁止自动执行 Migration。

生产工作负载必须定义 Startup/Readiness/Liveness Probe、资源 Request/Limit、PDB、Topology Spread、Anti-affinity、RollingUpdate、优雅终止、ServiceAccount、RBAC、NetworkPolicy 和 HPA/KEDA。Temporal Worker Deployment/Build ID 独立于 Kubernetes 发布；Worker 升级必须通过回放测试。

## sandbox-runtime 部署

后期新增：

```text
sandbox-runtime-api Deployment
sandbox-runtime-controller Deployment
sandbox-runtime-node-agent / backend adapter
sandbox-runtime-migration Job
sandbox runtime namespaces
```

只有 Sandbox Provisioner/Controller 获得最小 Kubernetes RBAC。

`sandbox-runtime` 可以调度 Kubernetes Pod、gVisor、Kata、MicroVM、Apple Container 或远程 VM，但这些是 Provider 内部实现。
