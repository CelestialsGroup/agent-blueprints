# Agent Application Platform v0.9.0

面向多个 Business Application 的 Manus-like 多轮 Agent Conversation、Workflow、Sandbox、Artifact、录制与交付平台。

Business 拥有 User/Membership/Product/Order/Payment/Entitlement/Commercial Quota；Agent Platform 拥有 Conversation/Message/WorkOrder/Workflow/Invocation/Event/Artifact/Technical Usage/Delivery/Provider/Sandbox/RuntimeRecording/Experience Catalog。双方通过版本化契约解耦。

扩展模型：

```text
Scenario -> CapabilityDefinition -> ProviderResolution
         -> 不可变 ProviderRevision + ProviderAdmissionDecision
         -> Plugin / Runtime / Sandbox Provider
```

默认实现为 DeerFlow AgentRuntimeProvider、Temporal、PostgreSQL、兼容 S3 的 Storage 和 DeerFlow Built-in Sandbox；未来 `sandbox-runtime` 实现同一 Sandbox Provider 契约。html-anything、Open Design、motion-anything、html-to-pptx/html-video 通过 Catalog/Template/Skill/Editor/Converter Provider 集成。

校验：

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

当前是已完成本地契约验证的产品边界候选版本，覆盖 Conversation/Branch、Agent Runtime、RuntimeRecording、Experience Catalog 和 Business Entitlement 交接；公共准入前不冻结，也不代表生产就绪。详情从 `START_HERE.md` 开始。
