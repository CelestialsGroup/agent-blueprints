# 文档目录

本目录只描述当前候选架构、开发规范和验收边界。历史审查过程、临时修复记录、实现进度和重复的字段说明不属于 Blueprint 事实源。

## 事实源层级

1. `DECISIONS.md` 中的架构边界与决策。
2. 本目录中的领域规范、数据不变量和开发规范。
3. 锁定 Contract Revision 中的 Schema、OpenAPI、状态机、Conformance Suite 和 Fixture。
4. Application 的 DDL/代码与运行证据。

Application 的 Migration、Constraint、代码和运行证据用于证明是否符合 Blueprint 与 Contract，不属于 Blueprint 事实源，也不能覆盖上游。叙述文档不复制完整字段；需要精确实现时读取锁定 Contract 中的可执行契约。

## 入口与领域规范

| 主题 | 主文档 | 补充文档 |
|---|---|---|
| 架构入口 | `00_ARCHITECTURE_BASELINE.md`、`DECISIONS.md` | `01_SYSTEM_BOUNDARIES.md`、`02_CORE_DOMAIN.md`、`GLOSSARY.md` |
| Conversation 与 Business | `46_CONVERSATION_AND_TURNS.md`、`50_BUSINESS_ENTITLEMENT_INTEGRATION.md` | `03_WORK_CONTRACTS.md`、`17_IDENTITY_AND_AUTHORIZATION.md`、`18_EXECUTION_GRANT_SECURITY.md`、`28_BROWSER_SESSION_SECURITY.md` |
| Runtime、多 Agent 与扩展 | `09_DEERFLOW_INTEGRATION.md`、`05_WORKFLOW_RELIABILITY.md`、`20_CAPABILITY_SPI.md` | `21_PLUGIN_INVOCATION_PROTOCOL.md`、`26_DATA_MODEL_INVARIANTS.md`、`27_EXECUTION_MEDIATION.md`、`49_EXPERIENCE_CATALOG_AND_UI_EXTENSIONS.md` |
| Workflow 与可靠性 | `05_WORKFLOW_RELIABILITY.md`、`19_INVOCATION_CONSISTENCY.md` | `23_STATE_MACHINE_SPEC.md`、`26_DATA_MODEL_INVARIANTS.md`、`36_SANDBOX_CONFORMANCE_AND_MIGRATION.md` |
| Event 与 Workbench | `06_EVENT_MODEL.md`、`10_FRONTEND_INTEGRATION.md` | `29_EVENT_TYPE_REGISTRY.md`、`48_RUNTIME_RECORDING_AND_PLAYBACK.md` |
| Artifact 与 Delivery | `07_ARTIFACT_WORKSPACE.md`、`31_DELIVERY_AND_INGEST.md` | - |
| Sandbox | `33_SANDBOX_PROVIDER_CONTRACT.md`、`34_SANDBOX_SECURITY_AND_ISOLATION.md` | `36_SANDBOX_CONFORMANCE_AND_MIGRATION.md` |
| 部署与生产 | `11_DEPLOYMENT_AND_STACK.md`、`51_PHASE0_TECHNOLOGY_SELECTION.md`、`24_PRODUCTION_GOVERNANCE.md` | `13_ARCHITECTURE_ACCEPTANCE.md` |
| 三方仓库边界 | `52_BLUEPRINT_CONTRACT_APPLICATION_BOUNDARY.md` | `22_CONTRACT_GOVERNANCE.md` |
| 契约治理 | `22_CONTRACT_GOVERNANCE.md`、`37_JCS_AND_IJSON_PROFILE.md` | - |
| 路线图 | `../tasks/PHASE0.md`、`12_PHASE1_SCOPE.md` | `../prompts/CODEX_PHASE0_BOOTSTRAP.md` |

## 使用原则

- 查边界先读架构入口，查 Wire 字段直接读锁定 Contract，查实现事务直接读 Application。
- 自研 Native Runtime 是产品主实现；独立 Reference Contract Probe 只验证 AgentRuntimeProvider Port 可替换性，不承担产品能力。
- `09_DEERFLOW_INTEGRATION.md` 中的第三方项目只用于研究，不构成平台依赖、适配计划或准入结论。
- `13_ARCHITECTURE_ACCEPTANCE.md` 将契约通过、0B、0C-0G、0H、正式冻结和生产批准拆成独立结论，验收时不得混用。
- Blueprint 只定义上游边界。机器契约由 Contract 拥有；源码、Migration、依赖锁、部署物和运行证据由 Application 拥有。
- Contract 的 `CONTRACT_VALIDATION_REPORT.md` 和 `VALIDATION.json` 由同一次成功 Gate 生成，是某次验证结果，不是可替代契约的事实源。
