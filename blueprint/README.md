# Agent Application Platform Blueprint v0.9.0

本目录是面向多个 Business Application 的 Manus-like Agent Platform Blueprint。它独立定义架构、公共契约、开发规范和验收标准，不包含 Agent Platform 产品实现，也不跟踪某个实现仓库的实时开发进度。

## Blueprint 职责

- `docs/` 定义领域边界、架构决策、技术选型、可靠性与开发规则；
- `contracts/` 定义 Schema、OpenAPI、状态机、Event Registry、Semantic Constraints 和 Conformance Suite；
- `examples/`、`deploy/` 与 `prompts/` 提供 Fixture、可执行架构 Profile 和实施指引，不是可发布产品代码；
- `scripts/` 与 `Makefile` 验证 Blueprint 自身的一致性、确定性和兼容性。

产品源码、Migration、部署制品、组件测试、集成测试和生产证据属于独立实现仓库。当前两个目录可以并置开发，未来可以拆成独立仓库；实现必须以不可变 Blueprint Revision、Contract Manifest Digest 和 Conformance Suite Digest 锁定依赖，完整规则见 `docs/52_BLUEPRINT_IMPLEMENTATION_BOUNDARY.md`。

Business 拥有 User/Membership/Product/Order/Payment/Entitlement/Commercial Quota；Agent Platform 拥有 Conversation/Message/Branch WorkspaceRevision/WorkOrder/Workflow/Invocation/Event/Artifact/Technical Usage/Delivery/Provider/Sandbox/RuntimeRecording/Experience Catalog。双方通过版本化契约解耦。

扩展模型：

```text
Scenario -> CapabilityDefinition -> ProviderResolution + Resolver Evidence
         -> 不可变 ProviderRevision + ProviderAdmissionDecision
         -> 内容寻址 Conformance Suite / Event Registry
         -> Plugin / Runtime / Sandbox Provider
```

自研 Native Runtime 是正式产品主实现，也必须通过框架中立的 AgentRuntimeProvider Port。冻结该 Port 前，另行实现一个不复用 Native Runtime 内部执行包的最小 Reference Contract Probe，并共同通过 `runtime-core-v1`；这证明 Port 可替换，不构成第三方兼容承诺。DeerFlow、Dify、OpenHands、LangGraph、OpenAI Agents SDK 等项目只用于研究架构、能力和 UX，不在当前适配计划内。外层可靠性统一由 Temporal、PostgreSQL、兼容 S3 的 Storage 和平台 Ledger 提供。

Phase 0 使用平台自己的 Native SandboxProvider 与隔离执行后端；后端可通过同一 Port、ProviderRevision 和 Conformance Suite 独立升级替换，第三方 Sandbox 项目只作控制面与隔离模型参考。html-anything、Open Design、motion-anything、html-to-pptx/html-video 通过 Catalog/Template/Skill/Editor/Converter Provider 集成。

一个 WorkOrder 最多拥有一个 WorkflowRun；Root Admission 成功后才以单次 RootBinding 原子绑定 Root AgentRun/RunManifest。Sub-agent 必须经过 ChildAgentRunSpawnRequest/AdmissionDecision，所有 AgentRun 共享 WorkOrder Budget Ledger，并使用独立 Resource Allocation、WorkspaceBinding、Sandbox Slot、Fencing 和仅追加 ControlFanout 版本链。Root 成功不能掩盖活动或失败的 required Child。

校验：

```bash
./scripts/bootstrap_contracts.sh
make validate-architecture
```

当前 Blueprint 已完成本地 Architecture Contract Gate，覆盖精确 ExecutionGrant 请求绑定、Branch Create/Fork 与 WorkspaceRevision CAS、可失败的 WorkflowRun/RootBinding、多 Agent Admission 与共享预算、框架中立 Agent Runtime、按需 Sandbox、可审计 ProviderResolution、ArtifactOperation/分阶段 Ingest、NoUsage、兼容性判定、Secret/Credential mediation、Runtime Gateway/Recording、Experience Catalog，以及 TechnicalUsage/Business Settlement 交接。最新计数和工具链证据见 `CONTRACT_VALIDATION_REPORT.md`；正式冻结前仍需独立 CI/兼容性准入。该结果不对任何实现仓库的组件完成度、集成链路、可靠性或生产批准作出结论。详情从 `START_HERE.md` 开始。
