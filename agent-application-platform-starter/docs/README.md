# Documentation

只保留当前 v0.9.0 实施需要的事实源；历史审查与逐版本修复报告已经删除。

## Start and decisions

- `00_ARCHITECTURE_BASELINE.md`: baseline summary and maturity boundary.
- `DECISIONS.md`: current accepted architecture decisions.
- `01_SYSTEM_BOUNDARIES.md`: ownership and dependency direction.
- `02_CORE_DOMAIN.md`: aggregate and module model.
- `GLOSSARY.md`: canonical terminology.

## Product and access

- `03_WORK_CONTRACTS.md`: Business/Platform request, usage and delivery contracts.
- `46_CONVERSATION_AND_TURNS.md`: multi-turn conversation and branch model.
- `50_BUSINESS_ENTITLEMENT_INTEGRATION.md`: membership, entitlement and quota handoff.
- `17_IDENTITY_AND_AUTHORIZATION.md`: principals, scopes and object authorization.
- `18_EXECUTION_GRANT_SECURITY.md`: signed per-turn authorization.
- `28_BROWSER_SESSION_SECURITY.md`: browser Cookie/SSE/WebSocket security.
- `10_FRONTEND_INTEGRATION.md`: Workbench integration.

## Execution and extension

- `05_WORKFLOW_RELIABILITY.md`: Temporal, Outbox and replay rules.
- `19_INVOCATION_CONSISTENCY.md`: side-effect ledger and reconciliation.
- `27_EXECUTION_MEDIATION.md`: Model/Tool/Artifact/Egress enforcement.
- `09_DEERFLOW_INTEGRATION.md`: AgentRuntimeProvider adapter and upgrades.
- `20_CAPABILITY_SPI.md`: Capability, Resolution, Revision and Conformance.
- `21_PLUGIN_INVOCATION_PROTOCOL.md`: governed invocation protocol.
- `30_PLUGIN_MODE_BINDINGS.md`: service/job/sandbox_cli/MCP bindings.
- `49_EXPERIENCE_CATALOG_AND_UI_EXTENSIONS.md`: templates and isolated rich UI.

## State, data and artifacts

- `23_STATE_MACHINE_SPEC.md`: authoritative lifecycle mapping.
- `26_DATA_MODEL_INVARIANTS.md`: required database constraints.
- `06_EVENT_MODEL.md` and `29_EVENT_TYPE_REGISTRY.md`: event ordering and payload governance.
- `07_ARTIFACT_WORKSPACE.md` and `31_DELIVERY_AND_INGEST.md`: artifact lifecycle and registered external I/O.
- `48_RUNTIME_RECORDING_AND_PLAYBACK.md`: historical runtime playback.

## Sandbox and operations

- `33_SANDBOX_PROVIDER_CONTRACT.md`: stable SandboxProvider port.
- `34_SANDBOX_SECURITY_AND_ISOLATION.md`: isolation profiles and threat boundary.
- `36_SANDBOX_CONFORMANCE_AND_MIGRATION.md`: provider replacement evidence.
- `11_DEPLOYMENT_AND_STACK.md`: deployment topology and release rules.
- `24_PRODUCTION_GOVERNANCE.md`: SLO, capacity, retention and recovery.

## Governance and delivery plan

- `22_CONTRACT_GOVERNANCE.md`: integrity, compatibility and reproducibility.
- `37_JCS_AND_IJSON_PROFILE.md`: cross-language digest profile.
- `13_ARCHITECTURE_ACCEPTANCE.md`: acceptance checklist.
- `12_PHASE1_SCOPE.md`: work allowed after Phase 0 evidence.
