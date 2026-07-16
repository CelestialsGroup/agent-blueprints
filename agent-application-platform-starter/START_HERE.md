# START HERE

这是 Agent Application Platform **v0.8.3 Architecture and Contract Hardening Candidate**。

v0.3–v0.8.2 均不得作为当前实施基线；旧版本只保留为历史审查证据。

## 唯一 Admission 入口

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

支持 CPython 3.11–3.13、Node 22.16、Go 1.23.2。Python 和 npm 依赖、GitHub Actions 均锁定完整性；不支持的本机 Python 是环境问题，不是架构失败。

## 必读顺序

1. `AGENTS.md`
2. `ARCHITECTURE_REVIEW_STATUS.md`
3. `V083_CONTRACT_REHARDENING_AUDIT_REPORT.md`
4. `docs/41_V083_REVIEW_RESOLUTION.md`
5. `docs/00_ARCHITECTURE_BASELINE.md`
6. `docs/01_SYSTEM_BOUNDARIES.md`
7. `docs/17_IDENTITY_AND_AUTHORIZATION.md`
8. `docs/18_EXECUTION_GRANT_SECURITY.md`
9. `docs/03_WORK_CONTRACTS.md`
10. `docs/23_STATE_MACHINE_SPEC.md`
11. `docs/05_WORKFLOW_RELIABILITY.md`
12. `docs/19_INVOCATION_CONSISTENCY.md`
13. `docs/20_CAPABILITY_SPI.md`
14. `docs/21_PLUGIN_INVOCATION_PROTOCOL.md`
15. `docs/33_SANDBOX_PROVIDER_CONTRACT.md`
16. `docs/34_SANDBOX_SECURITY_AND_ISOLATION.md`
17. `docs/35_SANDBOX_LIFECYCLE_AND_SNAPSHOT.md`
18. `docs/36_SANDBOX_CONFORMANCE_AND_MIGRATION.md`
19. `docs/26_DATA_MODEL_INVARIANTS.md`
20. `docs/22_CONTRACT_GOVERNANCE.md`
21. `docs/37_JCS_AND_IJSON_PROFILE.md`
22. `docs/38_CONTRACT_CI_AND_PROVENANCE.md`
23. `tasks/PHASE0.md`
24. `prompts/CODEX_PHASE0_BOOTSTRAP.md`

## 稳定边界

Business Application 拥有 User、Membership、Product、Order、Payment 和 Commercial Quota。Agent Platform 拥有 WorkOrder、Workflow、Invocation、Event、Artifact、Technical Usage、Delivery、Provider 与 Sandbox。双方只能通过版本化契约集成。

稳定内核不得保存 Pod、Namespace、Container、VM、Node 或原始 Runtime Endpoint；这些字段只属于 Sandbox Provider Adapter 私有模型。

## 成熟度

当前状态只能表述为：

```text
Ready to enter public CI only after the Git-root workflow is committed and protected baseline variables are configured
Not frozen until public CI passes
Not production ready
```

生产批准还需要实现证据、故障注入、安全隔离、容量、Temporal Replay、备份恢复以及 DeerFlow/sandbox-runtime Conformance。
