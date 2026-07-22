# 契约验证报告

状态：**本地 Contract Gate 已通过；不对 Application 实现、集成、可靠性或生产批准作结论；Blueprint 与 Contract 尚未正式冻结**

验证日期：2026-07-22

本报告由 `contract/validation/generate_validation_evidence.py` 从本次成功 Gate 的 `build/validation/*.json` 生成；`VALIDATION.json` 是同源机器结果，不手工维护计数。

| 检查项 | 本地结果 |
|---|---|
| 纯源码静态审计 | 通过：664 个 JSON、15 个 YAML、9 个 OpenAPI、3 个 Markdown 文件 |
| JSON Schema 与夹具 | 通过：242 个 Schema、293 个有效夹具、80 个 Schema 负例 |
| 语义不变量 | 通过：8 个状态机、236 个语义负例 |
| 语义追踪 | 通过：135 个关键 Schema、496 条约束、294 个 Contract Gate 映射、166 个本次执行 Check ID、286 个 Phase 0 DDL/Conformance 责任 |
| Core Event Registry | 通过：Platform 30 类、Agent Runtime 17 类闭合 Event Type；CanonicalEvent 按 Producer 所有权绑定对应 Registry |
| 契约清单 | 通过：269 项受治理资源；Python/Node 一致 |
| OpenAPI | 通过：9 份文档，0 Error / 0 Warning |
| Bundle | 通过：9 个 Bundle，连续两次逐字节一致 |
| JCS / Strict I-JSON | Python：CPython 3.14.6；Node.js 24.18.0；Go/gofmt 均通过 |
| 兼容性 | 比较器自测通过；尚无冻结基线，显式记为首次冻结前 N/A，不记为兼容性通过 |
| 仓库/供应链/公共 CI | 本轮延后，不计入 Contract Gate 通过条件 |

本次 Gate 的机器可读 `contract_closure` 包含：request-bound ExecutionGrant and RunManifest；single public WorkOrder control authority through WorkOrderControlRequest plus ExecutionGrant；separate Turn and WorkOrder control with split CAS ownership；sender-constrained Business revocation and Platform-only fenced safety cancellation；ArtifactOperation execution scope with Platform-derived admission and one Invocation ledger；durable ArtifactOperation cancellation intent, dispatch and fail-closed reconciliation；ConversationBranch Create/Fork command with source cut, workspace head and CAS；explicit NoUsageAttestation terminal accounting without fabricated usage；complete stable semantic traceability with executed Gate checks or implementation-required evidence；Platform-owned CompatibilityDecision and evidence for Runtime checkpoints and Sandbox snapshots；SecretGrant and single-operation Credential Gateway mediation；RootBinding-derived primary AgentRun without duplicate WorkOrder authority；staged ArtifactIngest Create/Status/Confirm/Scan/Platform Finalize lifecycle；accepted WorkOrder RPO zero only under acknowledged synchronous PostgreSQL replication；caller input separated from Platform-derived ArtifactOperation and ArtifactIngest admission facts；declared Agent Access path and request identity binding with implementation conformance evidence；renewable RuntimeAuthorization and bounded Runtime/Sandbox/Egress tokens；closed purpose-specific JWS Header and Claims profiles；Runtime/Capability/Plugin/Sandbox/Artifact/Egress operation Contract/Profile/Digest binding；immutable owner-scoped EgressDestinationRevision with class authorization；opaque slot-scoped RuntimeSessionRoute and logical content-bound Placement；WorkspaceContentManifest and ownership-bound typed dual Event registries；source Inbox dedupe, bounded metadata and all JSON write encoded-body admission limits；ProviderRevision, BuildProvenance, admission and executable semantic traceability。

该结论仅为“Contract Gate 通过”。Contract 不包含或认证 Agent Platform 产品组件，因而不能据此声称 0B 实现完成、0C-0G 集成完成、0H 可靠性成立、正式冻结或获得生产批准；这些结论必须由锁定 Blueprint 与 Contract Revision/Digest 的 Application 和运行环境分别提供证据。

GitHub CI、仓库供应链准入和受保护冻结基线按当前阶段明确延后。首次正式冻结前，兼容性基线缺失可以显式 N/A；冻结后必须 fail-closed。
