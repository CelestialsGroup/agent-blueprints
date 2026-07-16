# Agent Application Platform v0.8.4

面向多个 Business Application 的通用 Agent 执行、Workflow、Sandbox、Artifact 与 Delivery 平台。

Business 拥有 User/Membership/Product/Order/Payment/Commercial Quota；Agent Platform 拥有 WorkOrder/Workflow/Invocation/Event/Artifact/Technical Usage/Delivery/Provider/Sandbox。双方通过版本化契约解耦。

扩展模型：

```text
Scenario -> CapabilityDefinition -> ProviderResolution
         -> immutable ProviderRevision + ProviderAdmissionDecision
         -> Plugin / Runtime / Sandbox Provider
```

默认实现为 DeerFlow、Temporal、PostgreSQL、S3-compatible Storage 和 DeerFlow Built-in Sandbox；未来 `sandbox-runtime` 实现同一 Sandbox Provider Contract。html-anything、html-to-pptx 等能力是可独立安装和替换的 Provider/Plugin。

校验：

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

当前是完成本地 re-hardening、等待 Git 根 Workflow 集成和 public CI re-admission 的候选版本；公共 CI 通过前不冻结，也不代表 Production Ready。详情从 `START_HERE.md` 开始。
