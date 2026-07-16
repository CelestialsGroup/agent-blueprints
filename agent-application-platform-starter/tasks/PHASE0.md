# Phase 0：契约验证与最小完整垂直链路

Phase 0 的目标不是一次性创建全部模块空壳，而是证明核心可靠性模型可以工作。

## Gate 0：契约与工具链

先执行：

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

必须通过：

- 公共 Registry 可安装
- Python / Node / Go RFC 8785 Test Vector
- Strict I-JSON 反向测试
- JSON Schema 与语义校验
- 4 份 OpenAPI 0 error / 0 warning
- OpenAPI Bundle
- Supply-chain URL/Integrity 检查

任何失败都阻止业务代码实施。

## Phase 0A：完整垂直链路

只选择一个确定性的参考场景，例如：

```text
reference-text-artifact
```

完整执行：

```text
Service Authentication
 -> ExecutionGrant
 -> Idempotency / WorkOrder Transaction
 -> Temporal WorkOrderWorkflow
 -> Invocation + Attempt
 -> Reference Plugin
 -> Artifact Staging
 -> ArtifactVersion Commit
 -> Technical Usage
 -> Canonical Event
 -> DeliveryPackage
 -> Signed Delivery Webhook Stub
```

### Reference Plugin

参考 Plugin 必须：

- 确定性输入输出
- 支持 Idempotency Key
- 支持 Status Query
- 支持可配置的故障注入
- 输出一个 `text/plain` 或 `text/markdown` StagedArtifact
- 返回整数基础单位 Usage
- 不访问公网
- 不访问平台数据库

它是可靠性测试工具，不是产品功能。

### Phase 0A 必须证明

#### Admission

- 相同 Client + Idempotency Key + Digest 返回同一 WorkOrder。
- 同 Key 不同 Digest 返回 409。
- 同 Grant 重放不创建第二个 WorkOrder。
- GrantConsumption、IdempotencyRecord、WorkOrder、Workspace 和 Start Outbox 同事务。
- Python / Node / Go 对同一 WorkOrder 产生相同 JCS bytes 和 digest。

#### Workflow

- 重复 Outbox Dispatch 不创建重复 Temporal Workflow。
- Worker 重启后 Workflow 恢复。
- PostgreSQL 当前状态和 Temporal History 可 Reconcile。
- Worker Build ID 和 Versioning Behavior 被记录。

#### Invocation

- Activity 重放复用同一个 Invocation。
- Retryable Failure 创建新 Attempt，不修改旧 Attempt。
- Attempt Number 和 Fencing Token 单调递增。
- 旧 Fencing Token Result 被拒绝。
- Provider “实际成功但响应超时”进入 outcome_unknown。
- Reconciliation 可以确认 success/failure。
- Reconciliation 超时进入 manual_review。
- Manual Review 可以 resolve 或 abandon，并留下 Audit。

#### Artifact

- Plugin 只能写 Staging。
- Digest/MIME/Tenant 验证后创建 ArtifactVersion。
- 重复 Complete 不创建重复 ArtifactVersion。
- ArtifactVersion 内容不可变。
- Commit 与 Usage/Event/Outbox 同事务。

#### Event

- WorkOrder Sequence 并发唯一。
- SSE 可以从 Last-Event-ID 恢复。
- Redis 通知丢失后仍可从 PostgreSQL 补拉。
- Event Type/Data Version 验证生效。

#### Delivery

- Delivery Webhook 至少一次。
- 重复发送以 webhook_id/delivery_id 幂等。
- “发送成功但确认丢失”不会重复执行业务副作用。
- 多次失败进入 DLQ，并可以安全重放。

## Phase 0A 故障注入矩阵

至少覆盖：

| 注入点 | 预期结果 |
|---|---|
| WorkOrder 事务 Commit 前进程退出 | 不存在半创建 WorkOrder |
| Outbox Publish 后 ACK 丢失 | Workflow 不重复 |
| Activity 调用前 Worker 退出 | 安全重新调度 |
| Plugin 成功后响应丢失 | outcome_unknown + reconcile |
| Plugin 返回旧 fencing token | 结果被拒绝 |
| Artifact 上传后 Commit 前退出 | Staging 可清理或重放 |
| Event 写入后 Redis 通知丢失 | SSE 仍可补拉 |
| Webhook 接收成功后响应丢失 | Receiver 幂等 |
| PostgreSQL 短暂不可用 | Workflow 重试且无重复副作用 |

## Phase 0B：平台骨架

只有 Phase 0A 全部通过后，才建立其余 Port 和骨架。

### Access

- WorkSession One-time Exchange
- HttpOnly Cookie
- Scope/Tenant/Object Authorization
- CSRF

### Execution Mediation

- ModelGateway Port
- ToolGateway Port
- EgressPolicy Port
- ExecutionBudgetEnforcer Port

### Capability / Provider

- Capability Registry
- ProviderInstance / immutable ProviderRevision
- Resolver
- Provenance/Trust Registry
- Runtime Mode Adapter Port

### Artifact Workspace

- Ingest Session
- EditSession
- ConversionJob
- PreviewSession
- DeliveryTarget / CallbackRegistration

### Sandbox Provider

- SandboxProvider Port
- SandboxRegistry
- SandboxSpec / Status / Lease / Operation
- Multiple Sandbox Slots per Workspace
- Desired/Observed State + Generation
- Capability Negotiation
- Exec / Cancel / RuntimeSession / Snapshot / Restore / Terminate Ports
- DeerFlowSandboxAdapter Stub
- sandbox-runtime Adapter Stub
- Sandbox Conformance Harness Skeleton

### Kubernetes

- Stateless Agent API
- Temporal Workers by Task Queue
- Runtime Gateway shell
- Separate control/runtime namespaces
- Sandbox Provisioner minimum RBAC
- Migration Job
- NetworkPolicy/Egress Gateway integration point
- Graceful Shutdown

## Phase 0 不实现

- 业务会员和支付
- 真实 DeerFlow Runtime
- 真实模型调用
- html-anything 产品功能
- PPTX Converter
- Plugin Marketplace
- Office 编辑器
- CRI
- 真实 sandbox-runtime Backend
- 完整生产 Kubernetes Overlay

## Phase 0 Exit Criteria

只有同时满足以下条件才算完成：

1. `make validate-all` 通过。
2. Phase 0A 垂直链路端到端测试通过。
3. 故障注入矩阵通过。
4. 数据库唯一约束和事务测试通过。
5. Temporal Replay Test 通过。
6. 没有绕过 Invocation Ledger、Artifact Staging 或 Tenant Scope。
7. Phase 0B Port 没有引入具体 DeerFlow/Kubernetes Backend 类型。
8. 完成报告附真实命令、日志、测试证据和未解决风险。

不得以“目录已创建”“接口已定义”“Mock 测试通过”代替 Phase 0A 运行证据。
