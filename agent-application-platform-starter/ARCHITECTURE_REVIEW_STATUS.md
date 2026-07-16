# Architecture Review Status

Candidate: **v0.8.5 Contract Closure**

Current package status: **Contract re-hardening complete locally; ready for public CI re-admission after repository-root integration**

Current repository status: **not admitted until the Git-root workflow is committed, protected baseline variables are configured, and public CI passes; not frozen; not production ready**

## 本版已闭合

- OpenAPI URN Registry 投影，4 个文档可 lint/bundle，Gate 强制 0 error/0 warning。
- 可执行 Gate 入口、Python 版本前置检查、monorepo Workflow 安装辅助。
- RunManifest Admission Context：CapabilityDefinition 摘要、允许 Provider Kind、Conformance 覆盖、Scenario 精确能力集合、Revision/Decision 与 Snapshot 绑定。
- Invocation/SandboxOperation v2：Attempt、Retry、Reconciliation、Manual Review、安全取消确认、Risk-accepted Abandon；聚合、Case、Decision 的 ID/version/digest/evidence/outcome 由跨对象 Gate 闭合。
- ProviderRevision 与 append-only Admission/Revocation Decision 分离。
- Node/Go/Python 将 RFC 8785 canonicalization 与 Strict I-JSON Admission 分层，精确拒绝所有超范围数学整数词法，并在任意精度分配前执行 token/exponent 资源上限。
- Schema `$ref` 复用，避免 SandboxSpec 和 ProviderRevisionSnapshot 漂移。
- 扩展 Compatibility Gate；覆盖 reviewed `not`/`dependentRequired`/OpenAPI `$ref` parameter 等收窄案例；CI 基线来自受保护变量，缺失时 fail-closed。
- Python hash lock、npm integrity、Actions full SHA；供应链卫生只检查 Git 跟踪文件并拒绝 `.DS_Store`/bytecode。
- WorkOrder、Invocation、SandboxOperation 的 Schema 状态集合与机器定义由语义 Gate 强制一致，并拒绝重复 `(from,event)` 的非确定迁移。

## Admission 规则

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

monorepo 必须先运行 `scripts/install_github_workflow.sh`，提交 Git 根 Workflow，并设置 `AGENT_PLATFORM_CONTRACT_ROOT` 与受保护的 Compatibility 变量。公共 CI 的 Python 3.11/3.13 Matrix、Node 22.16、Go 1.23.2、Redocly 2.39.0 和 deterministic bundle 全部通过后，才允许提出冻结审批。

## 尚未证明

- Phase 0A 运行实现；
- 多节点并发、故障注入和恢复；
- Kubernetes 网络/沙箱实际隔离；
- 性能、容量、SLO；
- Temporal Replay 与 PostgreSQL/Object Storage/Temporal 恢复演练；
- DeerFlow 和未来 sandbox-runtime 的生产 Conformance。
