# Architecture Review Status

Candidate: **v0.8.3 Architecture and Contract Hardening**

Current package status: **Contract re-hardening complete locally; ready for public CI re-admission after repository-root integration**

Current repository status: **not admitted until the Git-root workflow is committed, protected baseline variables are configured, and public CI passes; not frozen; not production ready**

## 本版已闭合

- OpenAPI URN Registry 投影，4 个文档可 lint/bundle，Gate 强制 0 error/0 warning。
- 可执行 Gate 入口、Python 版本前置检查、monorepo Workflow 安装辅助。
- RunManifest Admission Context：Scenario 精确能力集合、Revision/Decision 自摘要、最新认证决策、Instance/Snapshot 绑定。
- SandboxOperation v2：Attempt、Retry、Reconciliation、Manual Review、安全取消确认、Risk-accepted Abandon 完整闭环。
- ProviderRevision 与 append-only Admission/Revocation Decision 分离。
- Node/Go/Python Strict I-JSON 共享全部正反向向量，包括小数/指数形式的 unsafe integer。
- Schema `$ref` 复用，避免 SandboxSpec 和 ProviderRevisionSnapshot 漂移。
- 扩展 Compatibility Gate；CI 基线来自受保护变量，缺失时 fail-closed，首个冻结例外也必须显式授权。
- Python hash lock、npm integrity、Actions full SHA；供应链卫生只检查 Git 跟踪文件并拒绝 `.DS_Store`/bytecode。
- WorkOrder、Invocation、SandboxOperation 的 Schema 状态集合与机器定义由语义 Gate 强制一致。

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
