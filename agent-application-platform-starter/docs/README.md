# 文档目录

只保留当前 v0.9.0 实施需要的事实源；历史审查与逐版本修复报告已经删除。

## 入口与决策

- `00_ARCHITECTURE_BASELINE.md`：基线摘要与成熟度边界。
- `DECISIONS.md`：当前已接受的架构决策。
- `01_SYSTEM_BOUNDARIES.md`：所有权与依赖方向。
- `02_CORE_DOMAIN.md`：聚合与模块模型。
- `GLOSSARY.md`：规范术语。

## 产品与访问

- `03_WORK_CONTRACTS.md`：Business/Platform 请求、Usage 和 Delivery 契约。
- `46_CONVERSATION_AND_TURNS.md`：多轮 Conversation 与分支模型。
- `50_BUSINESS_ENTITLEMENT_INTEGRATION.md`：会员、Entitlement 和额度交接。
- `17_IDENTITY_AND_AUTHORIZATION.md`：Principal、Scope 和对象授权。
- `18_EXECUTION_GRANT_SECURITY.md`：按 Turn 签名授权。
- `28_BROWSER_SESSION_SECURITY.md`：浏览器 Cookie/SSE/WebSocket 安全。
- `10_FRONTEND_INTEGRATION.md`：Workbench 集成。

## 执行与扩展

- `05_WORKFLOW_RELIABILITY.md`：Temporal、Outbox 和回放规则。
- `19_INVOCATION_CONSISTENCY.md`：副作用账本与对账。
- `27_EXECUTION_MEDIATION.md`：Model/Tool/Artifact/Egress 强制治理。
- `09_DEERFLOW_INTEGRATION.md`：AgentRuntimeProvider Adapter 与升级。
- `20_CAPABILITY_SPI.md`：Capability、Resolution、Revision 和 Conformance。
- `21_PLUGIN_INVOCATION_PROTOCOL.md`：受治理的 Invocation 协议。
- `30_PLUGIN_MODE_BINDINGS.md`：service/job/sandbox_cli/MCP 绑定。
- `49_EXPERIENCE_CATALOG_AND_UI_EXTENSIONS.md`：Template 与隔离的富 UI。

## 状态、数据与 Artifact

- `23_STATE_MACHINE_SPEC.md`：权威生命周期映射。
- `26_DATA_MODEL_INVARIANTS.md`：必需的数据库约束。
- `06_EVENT_MODEL.md` 和 `29_EVENT_TYPE_REGISTRY.md`：Event 排序与 Payload 治理。
- `07_ARTIFACT_WORKSPACE.md` 和 `31_DELIVERY_AND_INGEST.md`：Artifact 生命周期与注册制外部 I/O。
- `48_RUNTIME_RECORDING_AND_PLAYBACK.md`：历史 Runtime 回放。

## Sandbox 与运行治理

- `33_SANDBOX_PROVIDER_CONTRACT.md`：稳定 SandboxProvider Port。
- `34_SANDBOX_SECURITY_AND_ISOLATION.md`：隔离 Profile 与威胁边界。
- `36_SANDBOX_CONFORMANCE_AND_MIGRATION.md`：Provider 替换证据。
- `11_DEPLOYMENT_AND_STACK.md`：部署拓扑与发布规则。
- `24_PRODUCTION_GOVERNANCE.md`：SLO、容量、保留与恢复。

## 治理与交付计划

- `22_CONTRACT_GOVERNANCE.md`：完整性、兼容性与可复现性。
- `37_JCS_AND_IJSON_PROFILE.md`：跨语言摘要 Profile。
- `13_ARCHITECTURE_ACCEPTANCE.md`：验收清单。
- `12_PHASE1_SCOPE.md`：取得 Phase 0 证据后允许开展的工作。
