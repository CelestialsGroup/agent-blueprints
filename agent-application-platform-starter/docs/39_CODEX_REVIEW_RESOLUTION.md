# Codex v0.8 审查问题解决报告

## 结论

Codex 审查总体可信。

七项问题中：

- P1-1、P1-2、P1-3、P1-5、P2-6、P2-7：成立。
- P1-4：部分成立。指定 Python 包版本在公共 PyPI 存在，但 npm Lock 指向内部制品地址，且原 Gate 没有真实公共环境重建证据。

v0.8.1 不推翻 v0.8 的领域边界，而是把说明性承诺转为可执行约束。

## 1. RFC 8785 没有真正实现

### v0.8 问题

- 使用 `json.dumps(sort_keys=True)`。
- 未拒绝重复 Key、NaN、Infinity、不安全整数和 Lone Surrogate。
- 没有三语言 Test Vector。

### v0.8.1

- 安全摘要使用 RFC 8785 JCS。
- 新增 Strict I-JSON Parser。
- 新增 Python、Node、Go 共享 Test Vector。
- WorkOrder、RunManifest、Sandbox Mutation 和 SchemaReference Digest 使用相同 Profile。
- 禁止用普通 Map 排序代替 JCS。

## 2. Run 不可完全复现

### v0.8 问题

以下对象允许缺失关键字段或空集合：

- ProviderRevision Conformance
- ProviderResolution immutable digest
- RunManifest AgentRuntime
- RunManifest CapabilityResolution

### v0.8.1

ProviderRevision 必须：

- certified
- non-empty conformance
- package/runtime/configuration/permission/credential digest
- kind-specific conformance

ProviderResolution 必须保存完整不可变 Revision Snapshot。

RunManifest 必须包含：

- AgentRuntime exact Revision
- 至少一个 CapabilityResolution
- Temporal Workflow Identity/Build/Versioning
- 至少一个 Sandbox Slot
- 所有 Sandbox Revision/Spec/Conformance Digest
- RFC 8785 self-digest

## 3. Sandbox Mutation 不统一

### v0.8 问题

Cancel、Snapshot、Lease、Session 等 Mutation 缺少部分：

- Idempotency Key
- Request Digest
- Deadline
- Generation

### v0.8.1

所有 Sandbox Mutation 继承：

```text
SandboxMutationEnvelope
  operation_id
  attempt_id
  fencing_token
  idempotency_key
  request_digest
  deadline_at
```

已有 Sandbox 的 Mutation 同时要求 `expected_generation`。

Schema 和 Valid/Invalid Fixture 均验证该规则。

## 4. 官方 Gate 不能独立复现

### 核对结果

Python 固定版本存在于公共 PyPI；原 `package-lock.json` 内部 Registry 问题成立。

### v0.8.1

- npm Registry 固定为公共 Registry。
- Lock 中不存在内部 URL。
- Supply-chain 检查阻止内部 Registry 和未固定版本。
- Python/Node/Go 版本进入 CI Matrix。
- Go JCS Harness 无外部依赖，可离线执行。
- Contract Manifest 固化 111 个关键 Contract Resource Digest。
- 验证报告区分本地离线证明和公共 CI 证明。

## 5. Invocation/Attempt 状态机不闭合

### v0.8 问题

- Retryable Failure 没有新 Attempt 转换。
- Outcome Unknown 无对账超时和人工终态。
- Plugin Status 允许 succeeded + error。

### v0.8.1

新增：

```text
retry_scheduled
manual_review
abandoned
```

规则：

- Retry 创建新 Attempt。
- Attempt Number/Fencing Token 递增。
- Outcome Unknown 禁止盲目重试。
- Reconciliation 超时进入 Manual Review。
- 人工可 resolve success/failure 或 abandon。
- Plugin Status 用条件 Schema 绑定 Result/Error。

## 6. Sandbox 实现泄漏和一对一限制

### v0.8 问题

- 稳定内核文档出现 Namespace、Pod Name、Raw Endpoint。
- 数据库约束使一个 Workspace 只能有一个 Sandbox。

### v0.8.1

稳定内核只保存：

- provider_state_reference
- runtime_endpoint_reference

它们是不透明引用。

Pod、VM、Container、Namespace、Node、Endpoint 和 Backend Credential 进入 Adapter Private Store。

模型改为：

```text
Workspace
 -> sandboxes[]
 -> sandbox_slot_key
```

支持：

- primary-code
- browser
- desktop
- subagent/*
- isolated/*

同一 Slot 通过 Partial Unique Index 限制一个 Active Sandbox。

## 7. Kubernetes 只是示意骨架

### v0.8 问题

- Default Deny 后缺少 DNS/依赖 Egress。
- Public Ingress 范围过宽。
- Provisioner RBAC Namespace 不合理。
- Runtime Gateway SecurityContext 不完整。

### v0.8.1

Base 新增：

- control/runtime 双 Namespace
- Restricted Pod Security Labels
- control/runtime Default Deny
- DNS Egress
- dependency namespace policy
- public gateway namespace policy
- Runtime Gateway restricted SecurityContext
- Sandbox Provisioner 对 runtime namespace 的最小 Role
- Sandbox 只到 Egress Gateway

仍明确：

> Base 是 policy-bearing architecture base，不是可直接上线的生产 Overlay。

生产 Overlay 必须通过真实 Cluster Dry-run、CNI Policy Test、连通性测试和故障注入。

## 8. Phase 0 路线调整

Phase 0 不再以批量空壳模块为退出标准。

先完成带故障注入的完整垂直链路：

```text
WorkOrder
 -> Temporal
 -> Invocation/Attempt
 -> Reference Plugin
 -> Artifact
 -> Event
 -> Delivery
```

该链路通过后才建立其他 Gateway、Editor、Sandbox 和 Provider 骨架。

## 最终判断

v0.8.1 达到：

- Contract Hardening Candidate
- Ready for public CI admission
- Public CI 通过后可冻结为 Codex Phase 0 Baseline

它仍不是生产级应用，也不能在没有实现证据的情况下称为“稳定可靠生产平台”。
