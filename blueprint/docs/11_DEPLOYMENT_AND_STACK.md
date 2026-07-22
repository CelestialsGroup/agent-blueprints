# 技术栈与 Kubernetes 部署

Phase 0 的组件矩阵、备选/不选、许可证、语言边界、版本升级和冻结时点以 `51_PHASE0_TECHNOLOGY_SELECTION.md` 为准；本文件只描述部署拓扑和运行责任。

## 技术基线

### 语言运行时基线

截至 2026-07-20，默认开发、构建和生产基线固定为以下官方稳定版本；“最新稳定”是受审查的精确版本，不使用浮动 `latest` 标签：

| 组件边界 | 固定基线 | 选择规则 |
|---|---:|---|
| Go 平台内核、API、Worker、Gateway、Controller | Go 1.26.5 | 最新 Go 正式稳定版 |
| Agent Workbench、Business Reference、契约工具 | Node.js 24.18.0 Active LTS（Krypton）+ pnpm 11.15.1 | 生产采用最新 Active LTS，不采用短生命周期 Current；包管理统一使用 pnpm |
| Native Python Runtime、评测与契约工具 | CPython 3.14.6 | 最新 CPython 正式稳定版；3.13 仅作 CI 回滚兼容通道 |

精确开发版本记录在 `.tool-versions`，`package.json`/`pnpm-lock.yaml` 和 `go.mod`/`toolchain` 分别约束 Node/pnpm 与 Go，Python 依赖继续使用带摘要的锁文件。生产镜像在实现阶段进一步固定 OCI Digest，并将编译器/解释器版本、依赖锁摘要、SBOM 和镜像摘要写入 BuildProvenance。

补丁升级先通过契约 Gate、历史载荷/Temporal Replay、Provider Conformance 和安全扫描，再 Canary；语言大版本或 Node LTS 切换必须双版本并行并保留旧镜像、Worker Build ID 与 ProviderRevision 的回滚窗口。升级只改变实现 Revision，不能原地改写已准入 ProviderRevision、RunManifest 或历史 Workflow。

版本核对来源：[Python 3.14.6](https://www.python.org/downloads/release/python-3146/)、[Node.js 24.18.0](https://nodejs.org/en/blog/release/v24.18.0)、[pnpm 11.15.1](https://github.com/pnpm/pnpm/releases/tag/v11.15.1)、[Go 1.26.5](https://go.dev/dl/#go1.26.5)。

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
- Native Runtime Core（产品主 Runtime，并先以 Core Profile 落地）
- 独立 Reference Runtime Contract Probe（冻结前验证公共 Port 可替换性）
- 独立 Reference Runtime Contract Probe（冻结前可替换性验证，不复用 Native Runtime 内部包）
- Model Gateway
- Tool/MCP Gateway
- Sandbox 出站 Gateway
- Artifact Gateway
- Capability Provider 服务 / Job / Sandbox CLI / MCP / 远程服务；Plugin 仅作兼容打包

Model/Tool Gateway 对 Runtime 暴露 `capability-provider-v1`；Artifact 与 Egress 分别暴露 `artifact-gateway-v1`、`egress-gateway-v1`。所有 Gateway Route 均绑定不可变 Contract Digest 与 audience，不允许实现期再以私有未版本化协议替代。

## Kubernetes 工作负载

```text
agent-api Deployment
agent-workbench Deployment
runtime-gateway Deployment
model-gateway Deployment
tool-gateway Deployment
egress-gateway Deployment

agent-worker Deployment（Phase 0 可承载多个逻辑 Task Queue）

agent-runtime-native Deployment
agent-runtime-reference-probe Deployment（冻结前 Port 可替换性验证）
html-anything Deployment
html-to-pptx Job
sandbox Pod / Job
migration Job
```

Orchestration、Runtime、Sandbox Provision、Preview、Conversion、Delivery 和 Maintenance 是逻辑 Worker/Task Queue 边界，不要求 Phase 0 立即拆成七个 Deployment。只有独立扩缩容、权限、故障域或资源类别出现实际需求时才拆分。Agent API 和普通 Worker 不保存权威 WorkOrder、Event 序列、Session、Provider 健康状态或 Sandbox 路由；这些状态位于 PostgreSQL、Temporal 和 Object Storage。Redis 只用于缓存、限流、在线状态和持久化后的 Event 唤醒，丢失 Redis 不影响正确性。

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
- Agent -> Capability Provider：mTLS + Capability Invocation Token
- Runtime/Provider -> Artifact/Egress Gateway：mTLS + operation-scoped Artifact/Egress Token
- Worker -> 兼容 Plugin/Job：Capability Adapter + Kubernetes/Manifest 私有协议
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
