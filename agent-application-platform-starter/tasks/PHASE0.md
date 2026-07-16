# Phase 0：架构与基础设施骨架

## 前置 Gate

```bash
python3 -m pip install -r requirements-contracts.txt
npm ci
./scripts/lint_contracts.sh
npm run bundle:openapi
```

## 只实现

### Contract Tooling

- OpenAPI / JSON Schema Codegen Pipeline
- Schema Registry 与 Digest 校验
- Contract Compatibility CI
- 正向/反向 Fixture

### Access

- Service Access Token Validator Port
- WorkSession One-time Exchange
- HttpOnly Cookie Session
- Scope/Tenant/Object Authorization
- CSRF 骨架

### Work

- IdempotencyRecord
- GrantConsumption
- WorkOrder / Workspace
- Start Workflow Outbox
- 正式 State Transition Domain Methods

### Workflow

- Temporal Local Environment
- Stable Workflow ID
- Worker Deployment / Build ID 配置
- WorkflowRuntime Port
- PostgreSQL/Temporal Reconciliation Port

### Invocation

- Invocation / Attempt / Fencing 数据模型
- Prepare / Complete 事务
- outcome_unknown / Reconciliation Port
- Plugin Invocation Client Port

### Execution Mediation

只建立 Port 和安全边界，不实现完整 Gateway：

- ModelGateway
- ToolGateway
- EgressPolicy
- ExecutionBudgetEnforcer

### Event

- WorkOrder Event Cursor
- EventTypeRegistry
- Append/Event/Projection/Outbox 事务 Port
- SSE Cookie Session 和 410 Cursor 语义

### Capability / Plugin

- Capability Registry
- ProviderInstance / ProviderRevision
- Deterministic Resolver
- Plugin Manifest Loader
- Provenance/Trust Registry Port
- Runtime Mode Adapter Port

### Artifact / Delivery

- Ingest Session
- Artifact / Version / Staging / Relation
- EditSession / ConversionJob
- CallbackRegistration / DeliveryTarget
- Webhook Publisher Port

### Kubernetes

- Stateless agent-api
- Runtime Gateway shell
- Temporal Workers by Task Queue
- Sandbox Provisioner minimal RBAC
- Migration Job
- NetworkPolicy/Egress Gateway placeholder
- Graceful Shutdown

## 不实现

- 完整业务会员
- 真正 DeerFlow Runtime Adapter
- 真实模型调用
- 真实 html-anything
- 真实 PPTX Converter
- 动态第三方 Plugin Marketplace
- Office 编辑器

## 必须证明

- 同 Client + Idempotency Key + Digest 返回同一 WorkOrder。
- 不同 Digest 返回 409。
- Grant 与 WorkOrder 同事务。
- WorkOrder Sequence 并发唯一。
- Invocation Attempt/Fencing 拒绝过期结果。
- outcome_unknown 不自动重试。
- WorkSession Cookie 不能跨 WorkOrder 访问。
- Plugin Trust 不来自 Manifest。
- ProviderResolution 锁定 Revision。
- Artifact Commit 创建新版本。
- 任意 Callback/Input URL 不进入 WorkOrder Contract。

### Sandbox Provider

- SandboxProvider Port
- SandboxRegistry
- SandboxSpec / Status / Lease / Operation
- Desired/Observed State + Generation
- Capability Negotiation
- Exec / Cancel / RuntimeSession / Snapshot / Restore / Terminate Ports
- DeerFlowSandboxAdapter Stub
- sandbox-runtime Adapter Stub
- Sandbox Conformance test harness skeleton

- Sandbox Provider 重复 Create 返回同一 Sandbox。
- 旧 Fencing Token 不能覆盖新 Sandbox Operation。
- Runtime Endpoint 不直接暴露给用户 API。
- Provider 不支持 Capability 时必须明确失败。
- RunManifest 锁定 Sandbox ProviderRevision。
