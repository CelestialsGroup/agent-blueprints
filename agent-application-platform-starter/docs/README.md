# 文档目录

本目录只描述当前 v0.9.0 候选架构。历史审查过程、临时修复记录和重复的字段说明不属于实施事实源。

## 事实源层级

1. `contracts/` 下的 Schema、OpenAPI、状态机、一致性套件和测试夹具。
2. 数据库 Migration、Constraint 和运行时验证证据；实现后必须满足上层契约。
3. `DECISIONS.md` 中的架构边界与决策。
4. 本目录中的领域规范。
5. 路线图、参考项目和验证报告。

叙述文档不复制完整字段或状态迁移；需要精确实现时直接引用对应可执行契约。

## 入口与领域规范

| 主题 | 主文档 | 补充文档 |
|---|---|---|
| 架构入口 | `00_ARCHITECTURE_BASELINE.md`、`DECISIONS.md` | `01_SYSTEM_BOUNDARIES.md`、`02_CORE_DOMAIN.md`、`GLOSSARY.md` |
| Conversation 与 Business | `46_CONVERSATION_AND_TURNS.md`、`50_BUSINESS_ENTITLEMENT_INTEGRATION.md` | `03_WORK_CONTRACTS.md`、`17_IDENTITY_AND_AUTHORIZATION.md`、`18_EXECUTION_GRANT_SECURITY.md`、`28_BROWSER_SESSION_SECURITY.md` |
| Runtime 与扩展 | `09_DEERFLOW_INTEGRATION.md`、`20_CAPABILITY_SPI.md` | `21_PLUGIN_INVOCATION_PROTOCOL.md`、`27_EXECUTION_MEDIATION.md`、`30_PLUGIN_MODE_BINDINGS.md`、`49_EXPERIENCE_CATALOG_AND_UI_EXTENSIONS.md` |
| Workflow 与可靠性 | `05_WORKFLOW_RELIABILITY.md`、`19_INVOCATION_CONSISTENCY.md` | `23_STATE_MACHINE_SPEC.md`、`26_DATA_MODEL_INVARIANTS.md` |
| Event 与 Workbench | `06_EVENT_MODEL.md`、`10_FRONTEND_INTEGRATION.md` | `29_EVENT_TYPE_REGISTRY.md`、`48_RUNTIME_RECORDING_AND_PLAYBACK.md` |
| Artifact 与 Delivery | `07_ARTIFACT_WORKSPACE.md`、`31_DELIVERY_AND_INGEST.md` | - |
| Sandbox | `33_SANDBOX_PROVIDER_CONTRACT.md`、`34_SANDBOX_SECURITY_AND_ISOLATION.md` | `36_SANDBOX_CONFORMANCE_AND_MIGRATION.md` |
| 部署与生产 | `11_DEPLOYMENT_AND_STACK.md`、`51_PHASE0_TECHNOLOGY_SELECTION.md`、`24_PRODUCTION_GOVERNANCE.md` | `13_ARCHITECTURE_ACCEPTANCE.md` |
| 契约治理 | `22_CONTRACT_GOVERNANCE.md`、`37_JCS_AND_IJSON_PROFILE.md` | - |
| 路线图 | `../tasks/PHASE0.md`、`12_PHASE1_SCOPE.md` | `../prompts/CODEX_PHASE0_BOOTSTRAP.md` |

## 使用原则

- 查边界先读架构入口，查字段和迁移直接读 `contracts/`。
- `09_DEERFLOW_INTEGRATION.md` 中的参考项目只用于选型，不构成平台依赖或准入结论。
- `13_ARCHITECTURE_ACCEPTANCE.md` 将本地架构候选、Phase 0 实现、正式冻结和生产批准拆成四个独立层级，验收时不得混用。
- `CONTRACT_VALIDATION_REPORT.md` 和 `VALIDATION.json` 由同一次成功 Gate 的临时机器证据生成，是某次验证结果，不是可替代契约的事实源。
