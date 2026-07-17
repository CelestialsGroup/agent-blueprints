# START HERE

这是 Agent Application Platform **v0.9.0 Product Boundary Candidate**。

v0.3–v0.8.6 均不得作为当前实施基线；旧版本只保留为历史审查证据。

## 唯一 Admission 入口

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

支持 CPython 3.11–3.13、Node 22.16、Go 1.23.2。Python 和 npm 依赖、GitHub Actions 均锁定完整性；不支持的本机 Python 是环境问题，不是架构失败。

## 必读顺序

1. `AGENTS.md`
2. `ARCHITECTURE_REVIEW_STATUS.md`
3. `V090_PRODUCT_BOUNDARY_AUDIT_REPORT.md`
4. `docs/45_V090_PRODUCT_BOUNDARY_RESOLUTION.md`
5. `docs/00_ARCHITECTURE_BASELINE.md`
6. `docs/01_SYSTEM_BOUNDARIES.md`
7. `docs/17_IDENTITY_AND_AUTHORIZATION.md`
8. `docs/18_EXECUTION_GRANT_SECURITY.md`
9. `docs/03_WORK_CONTRACTS.md`
10. `docs/46_CONVERSATION_AND_TURNS.md`
11. `docs/47_AGENT_RUNTIME_PROVIDER_CONTRACT.md`
12. `docs/48_RUNTIME_RECORDING_AND_PLAYBACK.md`
13. `docs/49_EXPERIENCE_CATALOG_AND_UI_EXTENSIONS.md`
14. `docs/50_BUSINESS_ENTITLEMENT_INTEGRATION.md`
15. `docs/23_STATE_MACHINE_SPEC.md`
16. `docs/05_WORKFLOW_RELIABILITY.md`
17. `docs/19_INVOCATION_CONSISTENCY.md`
18. `docs/20_CAPABILITY_SPI.md`
19. `docs/21_PLUGIN_INVOCATION_PROTOCOL.md`
20. `docs/33_SANDBOX_PROVIDER_CONTRACT.md`
21. `docs/34_SANDBOX_SECURITY_AND_ISOLATION.md`
22. `docs/35_SANDBOX_LIFECYCLE_AND_SNAPSHOT.md`
23. `docs/36_SANDBOX_CONFORMANCE_AND_MIGRATION.md`
24. `docs/26_DATA_MODEL_INVARIANTS.md`
25. `docs/22_CONTRACT_GOVERNANCE.md`
26. `docs/37_JCS_AND_IJSON_PROFILE.md`
27. `docs/38_CONTRACT_CI_AND_PROVENANCE.md`
28. `tasks/PHASE0.md`
29. `prompts/CODEX_PHASE0_BOOTSTRAP.md`

## 稳定边界

Business Application 拥有 User、Membership、Product、Order、Payment、Entitlement 和 Commercial Quota Reservation/Settlement。Agent Platform 拥有 Conversation、Message、WorkOrder、Workflow、Invocation、Event、Artifact、Technical Usage、Delivery、Provider、Sandbox、RuntimeRecording 与 Experience Catalog。双方只能通过版本化契约集成。

稳定内核不得保存 Pod、Namespace、Container、VM、Node 或原始 Runtime Endpoint；这些字段只属于 Sandbox Provider Adapter 私有模型。

## 成熟度

当前状态只能表述为：

```text
Local architecture and contract closure validated
Ready to enter implementation and repository admission
Not frozen until public CI passes
Not production ready
```

生产批准还需要实现证据、故障注入、安全隔离、容量、Temporal Replay、备份恢复以及 DeerFlow AgentRuntimeProvider/sandbox-runtime Conformance。
