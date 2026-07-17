# Agent Runtime 架构与 DeerFlow 参考 Adapter

## 1. 平台定位

Agent Platform 拥有 `agent-runtime-provider-v1.yaml` 定义的稳定 Port，不拥有也不强制依赖任何单一 Agent 框架。DeerFlow 是首个参考 Adapter，不是默认事实源、编译时前置依赖或唯一合法实现。

其他实现可以包括 LangGraph/Deep Agents、OpenAI Agents SDK、Microsoft Agent Framework、Google ADK、Mastra、面向文档场景的 LlamaIndex Workflows，以及未来的 Native Runtime。CrewAI 等框架也可在满足目标 Profile 时接入。

任何 Agent Runtime Provider 都不拥有：

- 用户与会员
- WorkOrder
- Artifact Metadata
- Usage Ledger
- Delivery
- Business Workflow

## 2. 框架无关的受治理 Runtime

SaaS 部署中的 Agent Runtime Adapter 必须实现受治理 Runtime Profile：

- Execution Budget 注入
- Model Gateway
- Tool/MCP Gateway
- Sandbox Egress Gateway
- Approval Signal
- Cancel
- Usage
- Event normalization
- Artifact 暂存/发现

任何 Runtime 都不得直接持有平台长期模型凭据，也不得绕过网络策略调用外部服务。

## 3. Provider Adapter 职责

每个 Provider Adapter 负责：

- Thread/Run 映射
- 启动/取消/恢复
- Event normalization
- Tool interception
- Usage mapping
- Artifact discovery
- Runtime/Sandbox 引用
- Error normalization

所有 Agent Runtime 调用本身经过 Invocation Ledger。

稳定操作包括 Capability 协商、启动/恢复 Run、仅追加 Command、Status、Cursor Event 和 Checkpoint Manifest。框架原生 Agent/Thread/Run/Checkpoint ID 与原始 Event 只存在于 Adapter 私有存储。

`contracts/state-machines/agent-runtime-run-v1.json` 是标准化 Run 状态的权威来源。所有变更操作携带 InvocationAttempt、幂等信息和 Fencing；取消意图不等于取消证明，`outcome_unknown` 必须经 Ledger 对账后才能提交终态。

## 4. 与 Temporal 的职责分离

Temporal 管理 WorkOrder、业务步骤、审批等待、重试、交付、结算和跨进程恢复。Agent Runtime Provider 管理单次 Agent Run 内的规划、推理、工具选择、Context、Sub-agent 和框架原生状态。

Runtime 框架自带的 Workflow、Graph 或 Session 不能取代平台 WorkOrder Workflow、Invocation Ledger、CanonicalEvent、Artifact、TechnicalUsage 或 Delivery。框架内部状态丢失时，Platform 必须能够根据外部 Checkpoint、Event Cursor 或明确的对账状态恢复或失败，不得伪造成功。

## 5. 多副本

长期目标：

- Checkpoint 外置
- Workspace/Sandbox 独立
- Runtime Pod 可替换
- Runtime ID 显式

若当前版本具有实例亲和性，RunManifest 固化 runtime_id，并由 Runtime Gateway 路由。

## 6. Provider 解析与运行锁定

Agent Runtime 不是平台级全局单例。ProviderResolution 按以下输入选择已认证 Revision：

- Scenario 所需 Capability 与 Profile；
- Tenant/ClientApplication Binding；
- 数据驻留、模型、工具和部署环境；
- 受治理能力、成本、容量和健康状态；
- 显式且安全的 Fallback Policy。

RunManifest 在准入时锁定 Agent Runtime ProviderRevision、版本、配置摘要和一致性报告。运行中的 Run 禁止静默切换框架；Fallback 只能用于尚未开始的新 Run。Provider 原生 Checkpoint 默认只保证同一 Provider 或明确声明并通过测试的兼容范围内恢复。

## 7. 参考项目与选型矩阵

以下结论基于 2026-07-17 的公开仓库状态。Star 数不作为选型依据；上游功能、仓库结构和许可证可能变化，实际引入时仍以锁定 Commit 的来源审查为准。

### 7.1 完整 Agent 产品与 Harness

| 项目 | 最值得借鉴 | 推荐定位 | 主要限制 |
|---|---|---|---|
| [DeerFlow](https://github.com/bytedance/deer-flow) | 通用 Agent、Sub-agent、Skill、Memory、Sandbox 和长任务工作台 | Phase 0 主参考 Adapter | 不能让 LangGraph、私有 Thread/Event 或 Built-in Sandbox 泄漏到平台稳定模型 |
| [OpenHands](https://github.com/OpenHands/OpenHands) / [Software Agent SDK](https://github.com/OpenHands/software-agent-sdk) | Agent Canvas、多个 Agent Backend、Agent Server、远程 Workspace、WebSocket 和 ACP 接入 | 第一优先级产品边界与编码 Agent 参考 | 上游正在拆分仓库；ACP 适合客户端会话互操作，不能替代本平台的受治理 Provider 契约；`enterprise/` 有独立许可证 |
| [Magentic-UI / MagenticLite](https://github.com/microsoft/magentic-ui) | 浏览器与文件协同、实时 Steering、关键动作审批、人工接管、VM Sandbox | 第一优先级 Workbench、Browser/Desktop 和 Human-in-the-loop 参考 | 当前主线与旧 0.1 架构差异较大，必须锁定版本；不是平台级可靠性内核 |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | 可配置模型/搜索/MCP、Supervisor-Researcher、并行研究和基准评测 | Research Scenario、Evaluation 与 Sub-agent 策略参考 | 是场景实现，不是通用 SaaS Runtime 或业务编排器 |
| [OpenManus](https://github.com/FoundationAgents/OpenManus) | 简洁的 Plan/Tool/Browser/Flow 实现和 Manus-like 交互基线 | 快速原型与行为对照 | 项目自己定位为简单实现，多 Agent 路径仍标注不稳定，不作为生产内核 |
| [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) | Block/Workflow Builder、预置 Agent、Marketplace、Frontend 与 Agent Protocol | Experience Catalog 和低代码编排的概念参考 | `autogpt_platform/` 使用 PolyForm Shield，不能未经法务审查复用；其 Workflow 不取代 Temporal |
| [AgenticSeek](https://github.com/Fosowl/agenticSeek) | 本地模型、Browser/Coding Agent 路由、离线隐私模式 | Local/Offline Deployment Profile 参考 | README 明确称早期原型，且为 GPL-3.0；只做隔离研究，不能直接并入核心代码 |

### 7.2 Agent Runtime 框架

| 框架 | 主要参考方向 | 推荐定位 |
|---|---|---|
| [LangGraph / Deep Agents](https://github.com/langchain-ai/langgraph) | 有状态循环、Checkpoint、人工介入、长周期任务 | 通用 Runtime 候选，但其 Checkpoint 仍是 Provider 私有状态 |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | 低抽象 Agent Loop、Handoff、Guardrail、Tracing、MCP | 第二个最小 Adapter 优先候选 |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) | Graph、多 Agent、OpenTelemetry、Python/.NET | 企业 Runtime Provider 候选 |
| [Google ADK](https://github.com/google/adk-python) | Agent/Tool/Session、评测和 GCP/Vertex AI 部署 | GCP 场景 Runtime Provider |
| [LlamaIndex Workflows](https://github.com/run-llama/llama_index) | 文档/RAG、事件驱动数据管道 | 场景型 Runtime/Capability Provider |
| [CrewAI](https://github.com/crewAIInc/crewAI) | 角色式多 Agent 与 Flow 快速组合 | 受限场景 Provider，不作为内核 |
| [Mastra](https://github.com/mastra-ai/mastra) | TypeScript、Workflow、Memory、Studio | TypeScript 场景 Provider |
| Native Runtime | 吸收多个实现经过验证的模式 | 后期自有 Runtime，不要求一次性重写全部能力 |

### 7.3 专项能力与基础设施

| 项目 | 最值得借鉴 | 平台映射 |
|---|---|---|
| [browser-use](https://github.com/browser-use/browser-use) | 浏览器状态表达、动作模型、远程浏览器和 Browser Agent 评测 | Browser Tool/Capability Provider；不拥有 WorkOrder 或授权 |
| [LLM Space](https://github.com/deer-flow/llm-space) | Agent 工程工作台、Run Snapshot、原始 Trace/可编辑调试副本分离、人工 Rubric 评测 | Agent Engineering Workbench 与 Evaluation UX 参考；不是 Runtime、最终用户 Workbench 或事实源 |
| [Letta Code](https://github.com/letta-ai/letta-code) | Memory Block、长期上下文、Skill 学习、Sub-agent 和多环境路由 | Memory/Context 策略参考；自修改内容必须经过版本化、审计和权限控制 |
| [Quicksand](https://github.com/microsoft/quicksand) | 跨平台 QEMU VM、网络默认隔离、Snapshot/Revert、桌面与浏览器控制 | 自研 `sandbox-runtime` 的本地 VM、Desktop 和 Checkpoint 参考 |
| [E2B Infrastructure](https://github.com/e2b-dev/infra) | 云端 Sandbox 控制面、自托管、模板与隔离执行 | SandboxProvider 的云端实现和容量模型参考 |
| [Daytona](https://github.com/daytonaio/daytona) | Control/Compute/Interface Plane、Snapshot、持久 Workspace、Terminal/VNC | SandboxProvider 与 Runtime Gateway 参考；复用前单独确认当前源码和许可证覆盖范围 |

Browser/Desktop 的实时画面、Terminal 字节流和历史录制仍由 Runtime Gateway 与 Platform-owned RuntimeRecording 管理。上述项目的 Session、Trace、Snapshot 或视频不能直接替代本平台的授权、脱敏、不可变 Chunk、Manifest 和 `work_sequence` 对齐契约。

### 7.4 Agent Engineering Workbench 参考模式

LLM Space 的主要价值是 Agent 开发、调试和评测体验，不是生产 Runtime。平台可以借鉴以下只读证据到新实验的流转模式：

```text
CanonicalEvent + RuntimeRecording + TechnicalUsage
 -> 只读 Run Evidence Projection
 -> 可编辑 Debug Workbench Copy
 -> 新 ConversationBranch + WorkOrder
 -> 新 Run 与 Evaluation Evidence
```

`Run Evidence Projection` 和 `Debug Workbench Copy` 在本节只是解释性投影，不是 v0.9 稳定领域对象。后续若要持久化 Evaluation/Rubric 等新对象，必须先完成所有权决策、Schema、授权、保留策略和兼容性设计。

- 原始 CanonicalEvent、RuntimeRecording、ArtifactVersion、RunManifest 和 TechnicalUsage 不可被调试操作改写。
- 调试副本必须保留来源 Run、ProviderRevision、Event/Recording/Artifact 摘要和创建者；不得伪装成原始证据。
- 从历史证据重新运行时，必须创建新的 ConversationBranch、WorkOrder、ExecutionGrant、ProviderResolution 和 RunManifest；不得复用旧授权或在原 Run 上继续写入。
- Trace Importer 只能把 Langfuse/OpenTelemetry/其他格式标准化为只读投影；第三方原始载荷进入受隔离的 Artifact Storage，不能成为平台事实源。
- Run 比较必须锁定候选 Run 和评测标准的精确 Revision/Snapshot。人工、规则或模型评测都必须记录评测者类型、输入证据摘要、结果和成本。
- Agent Engineering Workbench 是内部研发/运营界面，与面向用户的 Agent Workbench 分离；它不能绕过 Business Entitlement、ExecutionGrant、Gateway 或 Provider 准入。
- 本地 JSON Thread、宿主机 Bash、明文凭据和无 Cursor 的桌面 RPC 只适合本地实验，不得复制到 SaaS 执行链路。

### 7.5 采用优先级

1. 用 DeerFlow 完成主参考 Adapter，同时深度对照 OpenHands 的 Agent Server/多 Backend 边界，防止公共契约按 DeerFlow 私有模型定制。
2. 用 OpenAI Agents SDK 或 Native Minimal Runtime 完成第二个 `runtime-core-v1` Adapter；此阶段不需要复制另一个完整产品。
3. 用 Magentic-UI/MagenticLite 验证 Steering、Approval、Takeover、Browser/Desktop 和危险动作 UX；用 Open Deep Research 建立 Research Scenario 与可重复评测。
4. 用 LLM Space 验证 Trace 导入、Run 快照对比、不可变 Rubric Snapshot 和“原始证据到调试副本”的工程工作台体验，但不复用其本地持久化或宿主机执行模型。
5. 用 Quicksand 与 E2B 校验自研 `sandbox-runtime` 的本地 VM、云端控制面、Snapshot、网络隔离和多租户容量模型；Daytona 作为补充对照。
6. 用 Letta Code 研究长期记忆，但平台只接收经过策略、版本、来源和审计约束的 Memory Revision，不允许 Agent 直接改写稳定事实。
7. OpenManus、AutoGPT Platform 和 AgenticSeek 只做行为、产品或本地部署参考，不进入稳定内核，也不作为 Phase 0 的强制依赖。

这些矩阵只用于指导调研和 Adapter 优先级，不构成准入。每个具体版本仍必须经过许可证/来源审查、ProviderAdmissionDecision 和目标 Profile 的一致性测试。调研代码不得直接复制到核心；确需复用时必须记录来源 Commit、许可证、修改范围和升级策略。

## 8. 升级

优先级：

1. Configuration
2. Skill
3. 通过受治理 Gateway 接入 MCP
4. External Adapter
5. Plugin Service
6. Gateway Extension
7. Core Patch

每个 Runtime 的 RunManifest 固化：

- 框架 Tag/Commit
- Image Digest
- Adapter Version
- Config Digest
- Provider Revision
- 受治理一致性报告

每次上游升级创建新的不可变 ProviderRevision。旧 Run 不迁移到新 Revision；Canary/Draining 必须保留旧 Checkpoint 和历史 Event 回放。Core Patch 需要 Patch Ledger、上游基础 Commit 和 Rebase 测试。

## 9. 契约测试与可替换性证明

AgentRuntimeProvider 一致性至少分为：

- `runtime-core-v1`：Capability 协商、Start、Status、Cancel、Cursor Event、Artifact Staging、Usage、幂等和错误标准化；
- `runtime-general-v1`：在 Core 之上增加 Append-input、Interrupt、Pause/Resume、Approval、Sub-agent 和 Checkpoint Export/Restore；
- `governed-v1`：在目标 Runtime Profile 之上证明 Model/Tool/Artifact/Egress Gateway 不可绕过、预算可执行、敏感凭据不泄漏。

第二个最小 Adapter 只要求通过 `runtime-core-v1`；承担 Manus-like 主链路的 Provider 必须通过 `runtime-general-v1 + governed-v1`。Provider 不得声明未实现的 Feature；Scenario 缺少所需 Feature 时必须在准入阶段失败。

- Thread/Run
- Stream
- Tool interception
- Model budget
- Sub-agent
- Sandbox
- File/Artifact
- Cancel/Resume
- Approval
- Event idempotency
- Usage
- Historical replay
- Runtime 故障恢复
- 追加输入/Interrupt Command Fencing
- Checkpoint 导出/恢复兼容性
- 旧 ProviderRevision Event Golden File 标准化

冻结 AgentRuntimeProvider v1 前，至少两个实现必须通过 `runtime-core-v1`。Phase 0 可以使用 DeerFlow 快速完成主链路，但还必须增加第二个最小 Adapter，推荐 OpenAI Agents SDK 或 Native Minimal Runtime，并至少证明：

- 同一标准 Start/Command/Status/Event/Artifact/Usage 流程可运行；
- 平台稳定模型不出现两个框架的私有字段；
- 两个 Provider 的标准 Event 可被同一 Workbench 和 RuntimeRecording 消费；
- 切换只发生在新 Run 的 ProviderResolution，不发生在运行中；
- 不支持的 Capability 明确拒绝，不静默降级。

## 10. DeerFlow 参考 Adapter

DeerFlow Adapter 可以借鉴并复用其通用 Agent、研究、编码、Sub-agent、Sandbox 和前端交互实现，但所有 Platform 交互仍经过 AgentRuntimeProvider、SandboxProvider 和强制 Gateway。DeerFlow 私有 Thread/Run/Checkpoint/Event 不得泄漏到公共 API 或稳定数据库。

对 DeerFlow 的修改优先采用配置、Skill、MCP、外部 Adapter、Plugin Service 和 Gateway Extension；Core Patch 只用于无法通过稳定扩展面解决的问题，并必须维护 Patch Ledger 与 Rebase Test。

## 11. Sandbox 解耦

所有 Agent Runtime Adapter 都通过平台 SandboxProvider Port 使用 Sandbox，不依赖某个框架私有 Sandbox API。

首个参考实现可以是：

```text
SandboxProvider -> DeerFlowSandboxAdapter
```

后续也可以是：

```text
SandboxProvider -> sandbox-runtime
```

框架原生 Run 与 Sandbox ID 映射保存在 Adapter，不进入平台 Sandbox 契约。
