# Agent Runtime 与 DeerFlow 参考 Adapter

## 平台定位

Agent Platform 拥有 `agent-runtime-provider-v1.yaml` 定义的稳定 Port，不拥有也不依赖任何单一 Agent 框架。DeerFlow 是 Phase 0 的主参考 Adapter 候选，不是默认事实源、编译时依赖或唯一实现。

Runtime Provider 不拥有 User、Membership、WorkOrder、Artifact Metadata、TechnicalUsage、Delivery 或 Business Workflow。框架原生 Agent、Thread、Run、Checkpoint、Event 和 Trace 只存在于 Adapter 私有模型。

## Runtime 与平台边界

| Agent Platform | Agent Runtime Provider |
|---|---|
| WorkOrder、Workflow、授权、预算、Provider 准入 | 单次 Agent Run 内的规划、推理和上下文 |
| Invocation/Sandbox Ledger、CanonicalEvent | 框架原生 Agent、Thread、Run 和 Checkpoint |
| Artifact Metadata、TechnicalUsage、Delivery | Tool 选择、Sub-agent 和私有执行状态 |
| 运行终态和审计 | Event、Usage 和 Artifact 的标准化输出 |

SaaS Runtime 必须通过受治理 Profile，支持预算注入、Model Gateway、Tool/MCP Gateway、Sandbox Egress Gateway、Approval、Cancel、Usage、Event normalization 和 Artifact Staging。Runtime 不得持有平台长期模型凭据或绕过网络策略。

## AgentRuntimeProvider Port

稳定操作包括：

- Capability 协商；
- Start 和兼容范围内的 Restore；
- 仅追加 Command；
- Status 查询；
- Cursor Event；
- Checkpoint Manifest；
- Artifact Staging 和 Usage。

每次调用使用短期 RuntimeInvocation Token，并绑定 Tenant、ProviderRevision、WorkflowRun/AgentRun/RuntimeRun、RunManifest、InvocationAttempt、幂等请求摘要、Fencing、Policy、Budget 和 Permissions。取消意图不等于取消证明；`outcome_unknown` 必须通过 Invocation Ledger 查询或对账后才能进入终态。

## 与 Temporal 的职责分离

Temporal 管理 WorkOrder 编排、审批等待、重试、交付、结算和跨进程恢复。Agent Runtime Provider 管理单次 Agent Run 的内部循环和框架状态。

框架自带 Workflow、Graph 或 Session 不能取代平台 WorkOrder Workflow、Invocation Ledger、CanonicalEvent、Artifact、TechnicalUsage 或 Delivery。框架状态丢失后，平台只能依据兼容 Checkpoint、Event Cursor 或对账证据恢复或失败，不得伪造成功。

## Provider 解析与运行锁定

ProviderResolution 综合以下输入选择已认证 Revision，并固化 Resolver Revision、输入摘要、逐候选结论、Evidence 与 Decision Digest：

- Scenario 所需 Capability 和 Profile；
- Tenant 与 ClientApplication Binding；
- 数据驻留、模型、工具和部署环境；
- 受治理能力、成本、容量和健康状态；
- 显式且安全的 Fallback Policy。

RunManifest 在准入时通过唯一 ProviderResolution 锁定 Agent Runtime ProviderRevision、配置摘要和一致性证据，不复制第二份 Runtime 快照。Sandbox Slot 同样只引用 Resolution。运行中禁止静默切换框架；Fallback 只适用于未开始的新 Run。Provider 原生 Checkpoint 默认只在同一 Revision 或明确声明并验证的兼容范围内恢复。

## 一致性 Profile

| Profile | 最低要求 |
|---|---|
| `runtime-core-v1` | Capability、Start、Status、Cancel、Cursor Event、Artifact、Usage、幂等和错误标准化 |
| `runtime-general-v1` | Core + Append-input/Interrupt、Pause/Resume、Approval、Plan、Background Task、Sub-agent、Checkpoint Export/Restore |
| `governed-v1` | 强制 Model/Tool/Artifact/Egress Gateway、预算执行和敏感凭据隔离 |

承担 Manus-like 主链路的 Provider 必须通过 `runtime-general-v1 + governed-v1`。冻结 AgentRuntimeProvider v1 前，至少两个 Adapter 必须通过 `runtime-core-v1`，并证明相同 Workbench、Timeline、Artifact、Usage 和 Recording 路径不依赖某个框架。

不支持的 Capability 必须在准入阶段明确拒绝，不得静默降级。Provider 原生 Checkpoint 不得被宣称为跨框架可移植。

## DeerFlow 参考 Adapter

DeerFlow Adapter 可以借鉴通用 Agent、研究、编码、Sub-agent、Skill、Sandbox 和前端交互，但所有 Platform 交互仍经过 AgentRuntimeProvider、SandboxProvider 和强制 Gateway。

对 DeerFlow 的修改按以下优先级处理：Configuration、Skill、受治理 MCP、External Adapter、Plugin Service、Gateway Extension、Core Patch。Core Patch 必须记录上游 Commit、Patch Ledger 和 Rebase Test。

首个 Sandbox 实现可以是：

```text
SandboxProvider -> DeerFlowSandboxAdapter
```

后续可以替换为：

```text
SandboxProvider -> sandbox-runtime
```

替换只影响新 Run 的 ProviderResolution；稳定 Schema、WorkOrder、Artifact、Event、Usage、Recording 和前端不随之变化。

## 升级规则

每次上游升级创建新的不可变 ProviderRevision，并固化框架 Tag/Commit、Image Digest、Adapter Version、Config Digest 和一致性报告。旧 Run 不迁移到新 Revision；Canary 和 Draining 必须保留旧 Checkpoint 与 Event 回放能力。

## Runtime Session Core

同一 Runtime Adapter 内部应拆分为 Session Core 与 Presentation Adapter：

```text
Session Core
 -> typed Command / Event / Artifact / Usage
 -> Workbench REST/SSE Adapter
 -> Headless streaming Adapter
 -> optional IDE/ACP Adapter
```

Session Core 可以私有实现 Prompt Queue、Interjection、Compaction、Background Task、worktree 和本地 Journal，但平台只接收连续 Runtime Command、注册 Event、Artifact/Checkpoint Reference 和 TechnicalUsage。Resume 复用同一 AgentRuntimeRun；Fork/Rewind/调试重跑映射为新的 ConversationBranch、WorkOrder 和 AgentRun。

## 参考项目

以下项目只用于边界、产品和实现方式调研，不构成准入或依赖。结论基于 2026-07-17 的公开仓库状态；实际引入必须锁定 Commit，并重新进行许可证、来源和安全审查。

| 项目 | 主要参考方向 | 平台定位 |
|---|---|---|
| [DeerFlow](https://github.com/bytedance/deer-flow) | 通用 Agent、Sub-agent、Skill、Sandbox、Workbench | Phase 0 主参考 Adapter |
| [OpenHands](https://github.com/OpenHands/OpenHands) | Agent Server、多 Backend、远程 Workspace、Agent Canvas | 编码 Agent 与产品边界参考 |
| [Magentic-UI / MagenticLite](https://github.com/microsoft/magentic-ui) | Steering、Approval、Takeover、Browser/Desktop | Workbench 和 Human-in-the-loop 参考 |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | Supervisor/Researcher、并行研究和评测 | Research Scenario 参考 |
| [OpenManus](https://github.com/FoundationAgents/OpenManus) | 简洁 Plan/Tool/Browser/Flow | 行为原型，不作为生产内核 |
| [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) | Block/Workflow Builder、Preset、Marketplace | Experience Catalog 概念参考；复用前需许可证审查 |
| [AgenticSeek](https://github.com/Fosowl/agenticSeek) | 本地模型、Browser/Coding Agent | Local/Offline Profile 调研，不并入核心 |
| [LangGraph / Deep Agents](https://github.com/langchain-ai/langgraph) | 状态循环、Checkpoint、人工介入 | 通用 Runtime 候选 |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | Agent Loop、Handoff、Guardrail、MCP | 第二个最小 Adapter 优先候选 |
| [Grok Build](https://github.com/xai-org/grok-build) | Session Core、多 Presentation、Prompt Queue/Interjection、Background Task、Workspace Adapter、权限分层、Telemetry Redaction | Runtime Harness 与 Engineering UX 参考；ACP、JSONL/SQLite、宿主机 Bash、Hook 和私有 Checkpoint 不作为平台事实源 |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) / [Google ADK](https://github.com/google/adk-python) / [Mastra](https://github.com/mastra-ai/mastra) / [LlamaIndex](https://github.com/run-llama/llama_index) / [CrewAI](https://github.com/crewAIInc/crewAI) | 多 Agent、Graph、文档和云场景 | 场景或企业 Runtime 候选 |
| [browser-use](https://github.com/browser-use/browser-use) | Browser 状态、动作模型和评测 | Browser Capability Provider 参考 |
| [Letta Code](https://github.com/letta-ai/letta-code) | Memory Block、长期上下文和 Skill 学习 | 版本化 Memory 策略参考 |
| [Quicksand](https://github.com/microsoft/quicksand) | VM、网络隔离、Snapshot、Desktop | 自研 sandbox-runtime 参考 |
| [E2B](https://github.com/e2b-dev/infra) / [Daytona](https://github.com/daytonaio/daytona) | Sandbox 控制面、Workspace、Terminal/VNC | SandboxProvider 和容量模型参考 |
| [LLM Space](https://github.com/deer-flow/llm-space) | Run Snapshot、Trace 调试、Run 对比、Evaluation UX | Agent Engineering Workbench 参考，不是 Runtime 或事实源 |

推荐采用顺序：DeerFlow 主 Adapter；OpenAI Agents SDK 或 Native Minimal 第二 Adapter；Magentic-UI 验证 Steering/Takeover；Open Deep Research 验证 Research Scenario；LLM Space 验证只读证据到调试副本的体验；Quicksand、E2B 和 Daytona 验证后续 Sandbox 方向。

第三方 Trace、本地 JSON、宿主机 Bash、明文凭据和无 Cursor 桌面 RPC 只能用于隔离实验，不得复制到 SaaS 生产链路。

引入 Grok Build 源码前必须锁定公开 Commit 并逐项检查 `THIRD-PARTY-NOTICES`；仓库根许可证不能替代 Codex/OpenCode ports 和 Vendored Source 的许可证审查。Hook 明确是 fail-open 扩展点，不得用于实现 Platform Policy 或 Sandbox 安全边界。
