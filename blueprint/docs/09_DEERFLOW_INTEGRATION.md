# 自研 Agent Runtime 与第三方项目参考边界

## 平台定位

Agent Platform 拥有 `agent-runtime-provider-v1.yaml` 定义的稳定 Port，自研 Native Runtime 是 Phase 0 和产品主实现。DeerFlow、Dify、OpenHands 等第三方项目只用于研究架构、能力拆分、交互和运维经验，不是需要整体适配、嵌入或兼容的实施目标。

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

Start、Command、Status 与 Event 分别使用单操作 Runtime Token。Token 固定 Operation Contract、Digest Profile 与 Body/Path/规范化 Cursor 摘要；Runtime Command 显式携带平台逻辑 `invocation_id`，DeerFlow 的 Thread/Checkpoint ID 不能替代 `runtime_run_id + invocation_id + invocation_attempt_id + fencing_token` 绑定。

每次调用使用短期 RuntimeInvocation Token，并绑定已认证 Runtime Controller `sub`、Tenant、ProviderRevision、WorkflowRun/AgentRun/RuntimeRun、RunManifest、RuntimeAuthorization、InvocationAttempt、幂等请求摘要、Fencing、Policy、Budget 和 Permissions。锁定的 Runtime v1 中，`execution` Token 的 `iat/nbf` 不得早于 RuntimeAuthorization 签发，也不得越过 RuntimeAuthorization 或命令期限；执行授权到期后，平台仍可签发最长 300 秒的 `safety_control`，但它只能读取 Status/Event 或发送 Cancel/Pause，不能 Start、Resume、Append、Interrupt、Approval、Checkpoint、调用 Gateway 或产生其他副作用。新 Runtime Revision 按 `54_AGENT_RUNTIME_EXECUTION_ARCHITECTURE.md` 将读取和系统减权拆为 `observation/reduction_control`，不改写旧 Run。取消意图不等于取消证明；`outcome_unknown` 必须通过 Invocation Ledger 查询或对账后才能进入终态。

Start 请求不是只有 Message ID 的通知。Adapter 必须收到实际有界输入或不可变输入引用、ContextPackage、四类带 Contract ID/Digest/Audience 的 Gateway Binding、请求体 Admission Limits，以及本 Attempt 的完整 RuntimeAuthorization/ArtifactGrant。Input/Context/Gateway 必须与 RunManifest 相等；Authorization 必须覆盖 Manifest 的 ArtifactAccessRequirement，闭合同一 Tenant/WorkOrder/CommercialAuthorization 的 Budget/Policy/Permissions 绑定，不超过初始上限或商业授权 `expires_at`，并拒绝早于 Authorization 签发或晚于其到期的 ArtifactGrant。Model/Tool 调用复用 Capability Port，Artifact/Egress 调用使用各自操作 Token；任何缺失、过期、扩权或摘要不匹配都拒绝执行。

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

自研 Native Runtime 必须通过 `runtime-general-v1 + governed-v1`。冻结 AgentRuntimeProvider v1 前，Native Runtime 与一个独立、最小的 Reference Contract Probe 必须通过 `runtime-core-v1`，并证明相同 Workbench、Timeline、Artifact、Usage 和 Recording 路径不依赖主实现内部模型；这不要求适配任一第三方 Agent 项目。

不支持的 Capability 必须在准入阶段明确拒绝，不得静默降级。Provider 原生 Checkpoint 不得被宣称为跨框架可移植。

## DeerFlow 等项目的参考方式

自研 Runtime 可以借鉴 DeerFlow 的通用 Agent、研究、编码、Sub-agent、Skill、Sandbox 和前端交互，也可以借鉴其他项目的 Workflow、RAG、Steering、Evaluation 与 Workbench 设计；被采纳的行为必须重新落入本平台的领域模型、Provider Port、SandboxProvider 和强制 Gateway。

不以修改、Fork 或包装 DeerFlow 作为 Phase 0 路线，也不复制其 Thread、Checkpoint、前端或 Sandbox 实现。若未来出现明确互操作需求，必须作为新的独立项目重新评估 ProviderRevision、许可证、安全、数据迁移和 Conformance，不能由“参考过该项目”推导出适配承诺。

首个 Sandbox 实现是平台自己的 SandboxProvider：

```text
SandboxProvider -> Native Sandbox Controller / isolated execution backend
```

后续可以替换后端实现，但不改变公共 Port：

```text
SandboxProvider -> alternate isolated execution backend
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

Native Runtime 的执行内核进一步按 Prompt、Context、Harness、Loop 和 Runtime-private Graph 分层。该分层不创建新的公共 Port：Platform 继续拥有 WorkOrder、Temporal、AgentRun Graph、Invocation Ledger 和 CanonicalEvent；Runtime Graph 只表达单个 AgentRun 内部的 Plan/Step。每次模型步骤固定同一 Context、Model、Tool exposure/dispatch、Environment 和权限快照，并输出脱敏 ModelStepEvidence。完整要求见 `54_AGENT_RUNTIME_EXECUTION_ARCHITECTURE.md`。

## 参考项目

以下项目只用于边界、产品和实现方式调研，不构成准入或依赖。原始矩阵基于 2026-07-21 的公开仓库状态，OpenAI Codex 补充研究快照为 2026-07-31；逐项目锁定状态以 `55_REFERENCE_ADOPTION_LEDGER.md` 为准。实际引入必须锁定 Commit，并重新进行许可证、来源和安全审查。

| 项目 | 主要参考方向 | 平台定位 |
|---|---|---|
| [DeerFlow](https://github.com/bytedance/deer-flow) | 通用 Agent、Sub-agent、Skill、Sandbox、Workbench | 架构与产品参考，不作适配目标 |
| [Dify 1.16.0](https://github.com/langgenius/dify/tree/1.16.0) | Workflow 草稿/发布/运行、Plugin Catalog、模型/工具、RAG、OpenAPI codegen、SSE | 当期最新稳定代码参考；不作为 Runtime、编排或事实源 |
| [Dify 2.0.0-beta.2](https://github.com/langgenius/dify/tree/2.0.0-beta.2) | Knowledge Pipeline、queue-based Graph 模块拆分和产品 Feature Radar | Beta 概念参考；不以版本号替代发布日期、代码谱系和成熟度证据 |
| [OpenHands](https://github.com/OpenHands/OpenHands) | Agent Server、多 Backend、远程 Workspace、Agent Canvas | 编码 Agent 与产品边界参考 |
| [Magentic-UI / MagenticLite](https://github.com/microsoft/magentic-ui) | Steering、Approval、Takeover、Browser/Desktop | Workbench 和 Human-in-the-loop 参考 |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | Supervisor/Researcher、并行研究和评测 | Research Scenario 参考 |
| [OpenManus](https://github.com/FoundationAgents/OpenManus) | 简洁 Plan/Tool/Browser/Flow | 行为原型，不作为生产内核 |
| [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) | Block/Workflow Builder、Preset、Marketplace | Experience Catalog 概念参考；复用前需许可证审查 |
| [AgenticSeek](https://github.com/Fosowl/agenticSeek) | 本地模型、Browser/Coding Agent | Local/Offline Profile 调研，不并入核心 |
| [LangGraph / Deep Agents](https://github.com/langchain-ai/langgraph) | 状态循环、Checkpoint、人工介入 | Runtime 内部机制参考，不作 Adapter 计划 |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | Agent Loop、Handoff、Guardrail、MCP | Agent Loop 与治理边界参考，不作 Adapter 计划 |
| [OpenAI Codex](https://github.com/openai/codex) | Turn/Step Context、Context 规范化/回滚/Compaction、Tool exposure/dispatch 分离、Agent graph 稳定遍历 | Runtime Harness/Context/Graph 实现参考；Thread、rollout、SQLite、私有审批/沙箱不作平台事实 |
| [Grok Build](https://github.com/xai-org/grok-build) | Session Core、多 Presentation、Prompt Queue/Interjection、Background Task、Workspace Adapter、权限分层、Telemetry Redaction | Runtime Harness 与 Engineering UX 参考；ACP、JSONL/SQLite、宿主机 Bash、Hook 和私有 Checkpoint 不作为平台事实源 |
| [Microsoft Agent Framework](https://github.com/microsoft/agent-framework) / [Google ADK](https://github.com/google/adk-python) / [Mastra](https://github.com/mastra-ai/mastra) / [LlamaIndex](https://github.com/run-llama/llama_index) / [CrewAI](https://github.com/crewAIInc/crewAI) | 多 Agent、Graph、文档和云场景 | 场景与企业能力参考，不作 Adapter 计划 |
| [browser-use](https://github.com/browser-use/browser-use) | Browser 状态、动作模型和评测 | Browser Capability Provider 参考 |
| [Letta Code](https://github.com/letta-ai/letta-code) | Memory Block、长期上下文和 Skill 学习 | 版本化 Memory 策略参考 |
| [Quicksand](https://github.com/microsoft/quicksand) | VM、网络隔离、Snapshot、Desktop | 自研 sandbox-runtime 参考 |
| [E2B](https://github.com/e2b-dev/infra) / [Daytona](https://github.com/daytonaio/daytona) | Sandbox 控制面、Workspace、Terminal/VNC | SandboxProvider 和容量模型参考 |
| [LLM Space](https://github.com/deer-flow/llm-space) | Run Snapshot、Trace 调试、Run 对比、Evaluation UX | Agent Engineering Workbench 参考，不是 Runtime 或事实源 |

推荐参考顺序：先提炼 DeerFlow/OpenHands 的通用 Agent、Sub-agent、Skill 与 Workbench 边界；用 OpenAI Codex 研究 request-scoped Context、Context Manager、Tool Router 和局部 Agent Graph；用 Dify 稳定版研究 Workflow、Catalog、RAG、契约生成和 SSE 产品化方式，Dify 2 Beta 只进入 Feature Radar；用 Magentic-UI 研究 Steering/Takeover、Open Deep Research 研究 Research Scenario、LLM Space 研究只读证据与 Evaluation UX；用 Quicksand、E2B 和 Daytona 研究 Sandbox 控制面。所有采纳项由自研 Runtime/Platform 重新实现，不形成第三方适配义务。

每个采纳项必须登记到 `55_REFERENCE_ADOPTION_LEDGER.md`，记录完整 Tag/Commit、快照日期、许可证/Notice、安全、借鉴点、拒绝点、平台落点、Contract/Conformance 影响和复审触发条件。未锁定 Commit 的项目只能保持 `research_only` 或设计参考，禁止复制源码、引入依赖或声明兼容。

Dify 的参考基线采用双轨策略。2026-07-21 审阅时，稳定基线为 `1.16.0`、Commit `5c6372d2f76d240265b92fd27c16bc772ffcb107`；最新 `2.0.0-beta.2` Tag 对应 Commit `2a84832998b4a005373859a82919a62a1bbbec42`，创建于 2025-09-08，并与后续 `1.16.0` 分叉。稳定 Tag 用于代码和运维方式参考，Beta 只用于发现未来能力；任何参考升级都重新记录 Tag、Commit、发布日期、代码谱系、许可证和安全结论，不追随 `main` 或浮动镜像。`1.16.0` 是稳定发布，但其中 Dify Agent 仍由官方标为 Open Beta，并明确只应提供给可信、非恶意用户；子功能不能继承整个 Release 的成熟度声明。

Dify 使用附加多租户限制的修改版 Apache-2.0 License；未经书面授权不得用其源码运营定义中的多租户环境，前端还受 Logo 条款和交互设计权利声明约束。因此不复制 Dify 前端、资产或整体源码，也不规划 Dify Workflow、Agent、MCP 或 Sandbox Adapter。Dify Agent、Redis Run Store、进程内 Scheduler、queue-based Graph Engine 与 Local Sandbox 均不能替代 AgentRuntimeProvider、Temporal、PostgreSQL 或 SandboxProvider；参考结论只能重新实现到平台自有契约与组件中。

第三方 Trace、本地 JSON、宿主机 Bash、明文凭据和无 Cursor 桌面 RPC 只能用于隔离实验，不得复制到 SaaS 生产链路。

引入 Grok Build 源码前必须锁定公开 Commit 并逐项检查 `THIRD-PARTY-NOTICES`；仓库根许可证不能替代 Codex/OpenCode ports 和 Vendored Source 的许可证审查。Hook 明确是 fail-open 扩展点，不得用于实现 Platform Policy 或 Sandbox 安全边界。
