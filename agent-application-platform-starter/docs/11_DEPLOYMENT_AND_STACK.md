# 技术栈与 Kubernetes 部署

## 技术基线

### Agent Platform

- Go
- PostgreSQL
- Temporal
- S3-compatible Object Storage
- Redis：Cache、Presence、Rate Limit、Event Wakeup
- OpenAPI 3.1.1 + JSON Schema 2020-12

### Web

- React / Next.js
- Standalone Agent Workbench
- Cookie-authenticated SSE
- Runtime Gateway WebSocket

### Runtime 与治理

- DeerFlow Runtime Service
- Model Gateway
- Tool/MCP Gateway
- Sandbox Egress Gateway
- Artifact Gateway
- Plugin Service / Job / Sandbox CLI / MCP / Remote Service

## Kubernetes Workload

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

deerflow-runtime Deployment
html-anything Deployment
html-to-pptx Job
sandbox Pod / Job
migration Job
```

Agent API 和普通 Worker 不保存权威 WorkOrder、Event sequence、Session、Provider health 或 Sandbox route；这些状态位于 PostgreSQL、Temporal 和 Object Storage。Redis 只用于 cache、rate limit、presence 和持久化后事件唤醒，丢失 Redis 不影响正确性。

Runtime Gateway 通过 opaque provider route 代理 Terminal/Browser/Desktop，禁止向前端返回 Pod/VM/raw endpoint，也不依赖 Sticky Session。只有独立 Sandbox Provisioner/Controller 拥有最小范围 Kubernetes API 权限。

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
- Agent -> Business：Signed Webhook + Outbox
- Agent -> Plugin Service：mTLS + Invocation Token
- Worker -> Plugin Job：Kubernetes Adapter + Manifest Protocol
- Agent Runtime -> Model/Tool/Egress：强制 Gateway
- Workflow：Temporal

## 发布

数据库：

```text
Expand Migration
 -> Deploy Backward-compatible Code
 -> Backfill
 -> Verify
 -> Contract Cleanup in Later Release
```

Workflow：

- Worker Deployment/Build ID
- Pinned 或 Auto-Upgrade 策略
- Replay Test
- Canary/Drain

应用 Pod 禁止自动执行 Migration。

生产 Workload 必须定义 startup/readiness/liveness probe、resource request/limit、PDB、topology spread、anti-affinity、RollingUpdate、graceful termination、ServiceAccount、RBAC、NetworkPolicy 和 HPA/KEDA。Temporal Worker Deployment/Build ID 独立于 Kubernetes rollout；Worker 升级必须通过 Replay Test。

## 7. sandbox-runtime 部署

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
