# v0.8.1 Contract Hardening Audit Report

## 1. 审查结论

Codex 对 v0.8 的主要批评成立。

v0.8.1 已经修复已发现的核心契约缺口，但本版本的准确状态是：

```text
Architecture / Contract Candidate
Ready for Public CI Admission
Not Frozen Until Public CI Passes
Not Production Ready
```

这比继续宣称“已完全冻结”更符合成熟项目治理。

## 2. 保留的正确架构

以下主干没有推翻：

- Business 与 Agent Platform 事实源分离
- Temporal + PostgreSQL 当前状态
- Invocation Ledger
- WorkOrder 级 Event Sequence
- Artifact Staging / Immutable Version
- Callback Registration
- Browser WorkSession Cookie
- Capability / ProviderRevision
- Sandbox Provider Contract
- Desired / Observed State
- Canary / Draining

## 3. 本次核心修复

### RFC 8785 / I-JSON

- 移除 `json.dumps(sort_keys=True)` 安全摘要。
- 使用 RFC 8785 canonical bytes。
- Strict Parser 拒绝重复 Key、NaN、Infinity、Lone Surrogate 和不安全整数。
- Python、Node、Go 共享 Test Vector。
- WorkOrder、RunManifest、Sandbox Mutation 和 SchemaReference 使用统一 Digest Profile。

### Run Reproducibility

ProviderRevision 现在必须：

- certified
- non-empty conformance
- immutable package/runtime/configuration/permission/credential digest
- kind-specific conformance

RunManifest 必须：

- 有 AgentRuntime exact Revision
- 有至少一个 CapabilityResolution
- 有 Temporal Identity / Build / Versioning
- 有至少一个 Sandbox Slot
- 锁定所有 Sandbox Revision / Spec / Conformance
- RFC 8785 self-digest

### Sandbox Mutation

所有 Mutation 继承统一：

```text
operation_id
attempt_id
fencing_token
idempotency_key
request_digest
deadline_at
```

已有 Sandbox 的操作同时要求 expected_generation。

### Invocation State Machine

新增：

- retry_scheduled
- manual_review
- abandoned
- InvocationAttempt 独立状态机

Retryable Failure 创建新 Attempt；Outcome Unknown 不直接重试；对账超时进入人工处理。

### Status Schema

PluginInvocationStatus 合法组合被 Schema 强制：

- succeeded -> result only
- failed -> known_failed error only
- outcome_unknown -> outcome_unknown error only
- accepted/running/cancelled -> no result/error

### Multi-Sandbox

```text
Workspace
 -> sandboxes[]
 -> sandbox_slot_key
```

支持代码、浏览器、桌面、Sub-Agent 和高隔离 Tool 使用不同 Sandbox。

稳定内核不再保存 Pod、Namespace、VM、Container 或 Raw Endpoint。

### Kubernetes

Base 现在具有：

- control/runtime 双 Namespace
- Restricted Pod Security Labels
- Default Deny
- DNS Egress
- Dependency Namespace Policy
- Public Gateway Namespace Policy
- Egress Gateway Boundary
- Runtime Gateway Restricted SecurityContext
- Runtime Namespace Provisioner RBAC

它仍是 Architecture Base，不伪装成生产 Overlay。

### Phase 0

Phase 0 先实现完整故障注入链路：

```text
WorkOrder
 -> Temporal
 -> Invocation
 -> Reference Plugin
 -> Artifact
 -> Event
 -> Delivery
```

链路通过后再创建其余 Gateway、Editor 和 Sandbox 骨架。

## 4. 本地实际验证

已实际运行：

- Supply-chain URL/Version scan
- JSON/YAML parse
- Schema meta-validation
- Portable Schema Registry
- 27 positive fixtures
- 11 Schema-negative fixtures
- 3 semantic-negative fixtures
- 4 strict I-JSON raw-negative fixtures
- Node JCS vectors
- Go JCS vectors
- 111-resource Contract Manifest
- OpenAPI structural audit
- Kubernetes structure/policy audit
- Markdown link audit
- Python script compilation

## 5. 尚未证明

当前执行环境无公共网络安装能力，因此以下必须由公共 CI 完成：

- public PyPI Bootstrap
- official Python rfc8785 vectors
- public npm ci
- Redocly lint
- Redocly deterministic bundle
- GitHub Actions Matrix

在它们通过前，不能将状态写成 Frozen。

## 6. 成熟度判断

| 维度 | v0.8.1 候选基线 |
|---|---:|
| 领域边界 | 9/10 |
| 契约严格度 | 8.5/10 |
| 扩展边界 | 9/10 |
| 一致性模型 | 8.5/10 |
| Sandbox 可替换性 | 9/10 |
| 安全架构 | 8.5/10 |
| 多节点设计 | 8.5/10 |
| 工具链可复现性 | 7.5/10，待公共 CI |
| Phase 0 可实施性 | 8.5/10 |
| 生产运行证据 | 1/10，尚未实现 |

评分只代表设计成熟度，不代表生产可用性。

## 7. 最终判定

```text
v0.8:
Do not use

v0.8.1:
Use as Contract Hardening Candidate
Freeze only after public CI passes
Then allow Codex Phase 0A
```
