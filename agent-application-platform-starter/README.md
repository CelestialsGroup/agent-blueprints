# Agent Application Platform v0.9.0

面向多个 Business Application 的 Manus-like 多轮 Agent Conversation、Workflow、Sandbox、Artifact、录制与交付平台。

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

当前是已完成本地 Architecture Contract Gate 的产品边界候选版本，覆盖精确 ExecutionGrant 请求绑定、Branch WorkspaceRevision、可失败的 WorkflowRun/RootBinding、多 Agent Admission 与共享预算、框架中立 Agent Runtime、按需 Sandbox、可审计 ProviderResolution、Runtime Gateway/Recording、Experience Catalog，以及 TechnicalUsage/Business Settlement 交接。最新计数和工具链证据见 `CONTRACT_VALIDATION_REPORT.md`；正式冻结前仍需独立 CI/兼容性准入，也不代表产品实现完成、集成链路完成或生产就绪。详情从 `START_HERE.md` 开始。
