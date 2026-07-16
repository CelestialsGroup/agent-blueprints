# v0.8.1 架构基线

## 1. 总体结构

```text
Business Applications
        │ Sender-constrained Service OAuth + ExecutionGrant
        ▼
Agent Access Gateway
        │
Agent Control Plane
  WorkOrder / Workflow / Invocation / Event / Artifact / Delivery
        │
        ├── Execution Mediation
        │     Model Gateway / Tool Gateway / Egress Gateway
        │
        ├── Execution Plane
        │     DeerFlow / Sandbox / Plugin / Runtime Gateway
        │
        └── Artifact Workspace
              Ingest / Preview / Edit / Version / Convert / Deliver
```

## 2. 稳定内核

- Identity and Object Authorization
- ExecutionGrant Consumption
- Idempotency
- WorkOrder/Workspace
- Workflow State
- Invocation Ledger
- Event Store/Registry
- Artifact Registry/Version/Staging
- Technical Usage
- Delivery/Callback Registry
- Audit

## 3. 可插拔边界

- Agent Runtime
- Sandbox
- Model Provider
- Tool/MCP Provider
- Template
- Renderer
- Editor
- Converter
- Storage Connector
- Channel

## 4. 强制治理

平台管理的 SaaS 运行必须经过：

```text
Model Gateway
Tool Gateway
Sandbox Egress Gateway
Artifact Gateway
```

未通过 Governed Runtime Conformance 的 Agent Runtime 不能用于公共 SaaS。

## 5. 可靠性

```text
Temporal Durable Workflow
+ PostgreSQL Current State
+ Invocation Ledger
+ Outbox / Inbox
+ Append-only Event
+ Artifact Staging
```

不承诺全局 Exactly-once。

## 6. 多节点

- API 无状态
- WorkOrder Event Cursor
- Runtime Gateway
- 独立 Sandbox
- Temporal Worker Versioning
- Provider Revision Lock
- Migration Job
- Cell/Cluster 预留

## 7. 基线边界

v0.8.1 是待公共 CI 准入的 Phase 0 Contract Hardening Candidate，不等同于生产实现已通过验证。

生产可靠性仍必须由：

- 实现测试
- 故障注入
- 性能测试
- 安全测试
- 恢复演练

证明。

## 8. Sandbox 可替换边界

```text
Stable Kernel
  SandboxRegistry / Lease / Operation / RuntimeSession / Usage
        ↓
Sandbox Provider Contract
        ↓
DeerFlow Sandbox Adapter | sandbox-runtime
```

Sandbox 后端可替换，但生命周期、授权、事件、Artifact 和前端协议保持稳定。
