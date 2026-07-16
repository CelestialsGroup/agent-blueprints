# Architecture Review Status

Candidate: **v0.8.2 Architecture and Contract Hardening**

Current status: **Ready for public CI admission; not frozen; not production ready**

## 本版已闭合

- OpenAPI URN Registry 投影，4 个文档可 lint/bundle，Gate 强制 0 error/0 warning。
- 可执行 Gate 入口、Python 版本前置检查、monorepo Workflow 安装辅助。
- RunManifest 摘要、Slot 唯一/主 Slot、Capability 唯一与 Provider 快照一致性反向测试。
- SandboxOperation v2：Attempt、Retry、Reconciliation、Manual Review、Abandon 完整闭环。
- ProviderRevision 与 append-only Admission/Revocation Decision 分离。
- Node/Go/Python Strict I-JSON 共享全部正反向向量。
- Schema `$ref` 复用，避免 SandboxSpec 和 ProviderRevisionSnapshot 漂移。
- 独立 Compatibility Gate；首个冻结基线前诚实报告 N/A。
- Python hash lock、npm integrity、Actions full SHA、bytecode 排除。

## Admission 规则

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

公共 CI 的 Python 3.11/3.13 Matrix、Node 22.16、Go 1.23.2、Redocly 2.39.0 和 deterministic bundle 全部通过后，才允许提出冻结审批。

## 尚未证明

- Phase 0A 运行实现；
- 多节点并发、故障注入和恢复；
- Kubernetes 网络/沙箱实际隔离；
- 性能、容量、SLO；
- Temporal Replay 与 PostgreSQL/Object Storage/Temporal 恢复演练；
- DeerFlow 和未来 sandbox-runtime 的生产 Conformance。
