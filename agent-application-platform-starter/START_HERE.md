# START HERE

这是 Agent Application Platform **v0.8 Sandbox-ready Architecture Baseline**。

v0.3–v0.7 均已废弃，不得作为实施依据。

## 先安装固定校验工具

```bash
python3 -m pip install -r requirements-contracts.txt
npm ci
./scripts/lint_contracts.sh
npm run bundle:openapi
```

## 阅读顺序

1. `AGENTS.md`
2. `docs/00_ARCHITECTURE_BASELINE.md`
3. `docs/01_SYSTEM_BOUNDARIES.md`
4. `docs/17_IDENTITY_AND_AUTHORIZATION.md`
5. `docs/18_EXECUTION_GRANT_SECURITY.md`
6. `docs/28_BROWSER_SESSION_SECURITY.md`
7. `docs/03_WORK_CONTRACTS.md`
8. `docs/23_STATE_MACHINE_SPEC.md`
9. `docs/05_WORKFLOW_RELIABILITY.md`
10. `docs/19_INVOCATION_CONSISTENCY.md`
11. `docs/27_EXECUTION_MEDIATION.md`
12. `docs/06_EVENT_MODEL.md`
13. `docs/29_EVENT_TYPE_REGISTRY.md`
14. `docs/20_CAPABILITY_SPI.md`
15. `docs/21_PLUGIN_INVOCATION_PROTOCOL.md`
16. `docs/30_PLUGIN_MODE_BINDINGS.md`
17. `docs/07_ARTIFACT_WORKSPACE.md`
18. `docs/31_DELIVERY_AND_INGEST.md`
19. `docs/26_DATA_MODEL_INVARIANTS.md`
20. `docs/14_KUBERNETES_DISTRIBUTED_RUNTIME.md`
21. `docs/24_PRODUCTION_GOVERNANCE.md`
22. `docs/22_CONTRACT_GOVERNANCE.md`
23. `docs/32_V06_AUDIT_AND_V07_RESOLUTION.md`
24. `docs/13_ARCHITECTURE_ACCEPTANCE.md`
25. `prompts/CODEX_PHASE0_BOOTSTRAP.md`

## 冻结边界

```text
Business Application
  User / Membership / Product / Order / Payment

Agent Platform Stable Kernel
  Identity / Grant / Work / Workflow / Invocation / Event
  Artifact / Usage / Delivery / Audit

Governed Execution Plane
  DeerFlow / Model Gateway / Tool Gateway / Sandbox / Plugin
```

## 诚实的成熟度定义

v0.8 可以作为 Codex Phase 0 的架构与契约基线。

它不代表生产可靠性已经得到证明。生产就绪仍需：

- 实现与架构测试
- 故障注入
- 安全测试
- 性能和容量测试
- 数据恢复演练
- DeerFlow Governed Runtime Conformance

## Sandbox Provider 必读

26. `docs/33_SANDBOX_PROVIDER_CONTRACT.md`
27. `docs/34_SANDBOX_SECURITY_AND_ISOLATION.md`
28. `docs/35_SANDBOX_LIFECYCLE_AND_SNAPSHOT.md`
29. `docs/36_SANDBOX_CONFORMANCE_AND_MIGRATION.md`

前期 DeerFlow Built-in Sandbox 与后期 `sandbox-runtime` 必须实现同一 Sandbox Provider Contract。
