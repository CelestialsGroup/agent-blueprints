# Agent Application Platform v0.9.0

面向多个 Business Application 的 Manus-like 多轮 Agent Conversation、Workflow、Sandbox、Artifact、录制与交付平台。

Business 拥有 User/Membership/Product/Order/Payment/Entitlement/Commercial Quota；Agent Platform 拥有 Conversation/Message/WorkOrder/Workflow/Invocation/Event/Artifact/Technical Usage/Delivery/Provider/Sandbox/RuntimeRecording/Experience Catalog。双方通过版本化契约解耦。

扩展模型：

```text
Scenario -> CapabilityDefinition -> ProviderResolution
         -> 不可变 ProviderRevision + ProviderAdmissionDecision
         -> 内容寻址 Conformance Suite / Event Registry
         -> Plugin / Runtime / Sandbox Provider
```

平台不强制依赖任何单一 Agent 框架。DeerFlow 可作为首个参考 AgentRuntimeProvider Adapter，并可借鉴 LangGraph/Deep Agents、OpenAI Agents SDK、Microsoft Agent Framework、LlamaIndex Workflows、Google ADK、CrewAI 和 Mastra；未来也可以实现自有 Native Runtime。外层可靠性统一由 Temporal、PostgreSQL、兼容 S3 的 Storage 和平台 Ledger 提供。

DeerFlow Built-in Sandbox 可作为首个参考 SandboxProvider，但不是平台前置依赖；未来 `sandbox-runtime` 实现同一 Sandbox Provider 契约。html-anything、Open Design、motion-anything、html-to-pptx/html-video 通过 Catalog/Template/Skill/Editor/Converter Provider 集成。

校验：

```bash
./scripts/bootstrap_contracts.sh
make validate-architecture
```

当前是已完成本地契约验证的产品边界候选版本，覆盖 Tenant-qualified WorkflowRun/AgentRun、Conversation/Branch、框架中立 Agent Runtime、Runtime Gateway/Recording、Experience Catalog，以及可执行 TechnicalUsage/Business Settlement 交接；公共准入前不冻结，也不代表产品实现完成或生产就绪。详情从 `START_HERE.md` 开始。
