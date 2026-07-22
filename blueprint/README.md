# Agent Application Platform Blueprint

本目录是面向多个 Business Application 的 Manus-like Agent Platform Blueprint。它以纯 Markdown 独立定义架构、开发规范和验收标准，不包含机器可执行契约、Agent Platform 产品实现，也不跟踪实现仓库的实时开发进度。

## Blueprint 职责

- `docs/` 定义领域边界、架构决策、技术选型、可靠性与开发规则；
- `tasks/` 定义阶段范围、入口条件、退出条件和证据要求；
- `prompts/` 提供遵守同一架构边界的开发指引；
- 根目录 Markdown 提供阅读顺序和贡献规则。

Schema、OpenAPI、状态机、Event Registry、Semantic Constraints、Fixture 和 Conformance Suite 属于独立 Contract；校验器、生成器、依赖锁和 Gate 报告属于非权威 Contract Scripts；产品源码、Migration、部署制品、组件测试、集成测试和生产证据属于独立 Application。当前目录可以并置开发，未来可以拆成独立仓库；完整规则见 `docs/52_BLUEPRINT_CONTRACT_APPLICATION_BOUNDARY.md`。

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

Blueprint 自身是文档评审对象，不运行 Contract Gate。机器契约应由锁定的 Contract Scripts 对锁定的 Contract Checkout 校验：

```bash
cd <script-root>
export AGENT_PLATFORM_CONTRACT_ROOT=<contract-root>
make validate-contract
```

架构设计已完成 0A 候选收口；对应机器契约曾通过本地 Gate，但目录拆分后的精确结果只以 Contract Scripts 对锁定 Contract Revision 生成的 `evidence/VALIDATION.json` 和验证报告为准。Contract Gate 不对 Application 的组件完成度、集成链路、可靠性或生产批准作出结论。详情从 `START_HERE.md` 开始。
