# 参考项目采纳账本

## 目的

本账本记录外部框架和项目对 Agent Platform 的设计影响，使“参考”能够追溯到明确的采纳、拒绝和落点，而不是停留在项目清单。参考项目不自动成为依赖、Adapter、兼容目标、成熟度证据或稳定事实源。

所有源码复用、包依赖、镜像引入或互操作承诺必须另行完成版本、许可证、来源、安全、数据迁移、升级和 Conformance 审查。本账本中的设计采纳只表示平台根据自身 Blueprint 重新实现对应行为。

## 状态与必填信息

采纳状态只有：

- `research_only`：仅用于调研，尚未形成架构决策；
- `design_adopted`：设计原则已进入 Blueprint，由平台重新实现；
- `deferred`：有价值但不在当前阶段；
- `rejected`：明确不采用，并记录原因；
- `source_reuse_review_required`：计划复用源码或依赖，但尚未完成准入。

每个进入实施的采纳项必须补齐：Reference ID、项目、完整 Tag/Commit、快照日期、许可证/Notice、安全结论、采纳点、拒绝点、平台落点、关联决策、Contract/Conformance 影响、Owner、复审触发条件和运行证据。未锁定 Commit 的项目禁止复制源码或声明版本兼容。

当前 `design_adopted` 只授权依据公开行为重新设计本平台能力，不授权复制源码、引入依赖、镜像或服务。表中未给出 Owner、安全准入或运行证据的项目均视为尚未进入实现准入，而不是默认通过；进入实施前应拆分独立采纳记录并补齐上述字段。

## 当前账本

| Reference ID | 项目与锁定基线 | 状态 | 借鉴并重新实现 | 明确不采用 | 平台落点与证据状态 |
|---|---|---|---|---|---|
| `REF-CODEX-001` | [OpenAI Codex](https://github.com/openai/codex) `f0c30e528a54bdf0fa9a4d52ff74b34383434811`，快照 2026-07-31；Apache-2.0 已核对 | `design_adopted` | request-scoped Turn/Step Context、Context 规范化/diff/rollback/compaction、同一步 Tool exposure 与 dispatch snapshot、model-visible specs 与 registry 分离、单父 Agent graph 和稳定遍历 | Codex Thread、rollout JSONL、SQLite、私有审批/沙箱、Hook、Agent graph 作为平台事实或 Temporal/AgentRun 替代品 | `54_AGENT_RUNTIME_EXECUTION_ARCHITECTURE.md`；待 Contract/Conformance 实施 |
| `REF-DEERFLOW-001` | [DeerFlow](https://github.com/bytedance/deer-flow)，Commit 未锁定 | `design_adopted` | 通用 Agent、Research/Coding、Sub-agent、Skill、Sandbox、Workbench 交互 | Fork/包装为主 Runtime，复制 Thread/Checkpoint/前端/Sandbox，推导适配承诺 | Runtime/Experience/Workbench/Sandbox 边界；源码复用仍禁止 |
| `REF-DIFY-STABLE-001` | [Dify 1.16.0](https://github.com/langgenius/dify/tree/1.16.0) `5c6372d2f76d240265b92fd27c16bc772ffcb107` | `design_adopted` | Workflow 草稿/发布/运行、Catalog、RAG、OpenAPI codegen、SSE 产品化 | Dify Agent/Redis Run Store/进程内 Scheduler/Local Sandbox 作为平台内核；复制受限制前端或多租户源码 | Workflow/Catalog/RAG/Workbench；修改版 Apache-2.0 的多租户和前端限制已记录 |
| `REF-DIFY-BETA-001` | [Dify 2.0.0-beta.2](https://github.com/langgenius/dify/tree/2.0.0-beta.2) `2a84832998b4a005373859a82919a62a1bbbec42` | `research_only` | Knowledge Pipeline、queue-based Graph 模块和 Feature Radar | 以 Beta 版本号或单项能力推导稳定性；直接回移分叉代码 | Feature Radar；不进入当前依赖或生产结论 |
| `REF-OPENHANDS-001` | [OpenHands](https://github.com/OpenHands/OpenHands)，Commit 未锁定 | `research_only` | Agent Server、多 Backend、远程 Workspace、Agent Canvas | 私有 Session/Workspace/Runtime 成为平台事实 | Runtime/Workbench 产品边界；采用前需锁定基线 |
| `REF-LANGGRAPH-001` | [LangGraph / Deep Agents](https://github.com/langchain-ai/langgraph)，Commit 未锁定 | `design_adopted` | 状态循环、Checkpoint、人工介入和局部 Graph 机制 | Graph/Checkpoint 替代 WorkOrder、Temporal、Invocation Ledger 或平台 CompatibilityDecision | Runtime-private Loop/Graph；不作 Adapter 计划 |
| `REF-AGENTS-SDK-001` | [OpenAI Agents SDK](https://github.com/openai/openai-agents-python)，Commit 未锁定 | `design_adopted` | Agent Loop、Handoff、Guardrail、MCP 边界 | SDK 对象进入公共 Schema，Handoff 绕过 Child Admission | Runtime-private Loop 与治理边界；不作 Adapter 计划 |
| `REF-MAGENTIC-UI-001` | [Magentic-UI / MagenticLite](https://github.com/microsoft/magentic-ui)，Commit 未锁定 | `research_only` | Steering、Approval、Takeover、Browser/Desktop 交互 | UI 状态或本地控制成为执行事实源 | Workbench/Human-in-the-loop；采用前需锁定基线 |
| `REF-GROK-BUILD-001` | [Grok Build](https://github.com/xai-org/grok-build)，Commit 未锁定 | `design_adopted` | Session Core/Presentation Adapter、Prompt Queue、Interjection、Background Task、Workspace Adapter、权限分层和 Telemetry Redaction | ACP、JSONL/SQLite、宿主机 Bash、fail-open Hook 和私有 Checkpoint 作为平台权威或安全边界 | Runtime Harness/Engineering UX；源码复用需逐项 THIRD-PARTY-NOTICES 审查 |
| `REF-RESEARCH-001` | [Open Deep Research](https://github.com/langchain-ai/open_deep_research)，Commit 未锁定 | `research_only` | Supervisor/Researcher、并行研究和评测 | Research graph 直接成为平台编排事实 | Research Scenario/Evaluation；采用前需锁定基线 |
| `REF-LOCAL-AGENT-001` | [OpenManus](https://github.com/FoundationAgents/OpenManus)、[AgenticSeek](https://github.com/Fosowl/agenticSeek)，Commit 未锁定 | `research_only` | 简洁 Plan/Tool/Browser Flow、本地模型与离线体验 | 作为生产内核或安全/可靠性证据 | 行为原型与 Local/Offline Profile 调研 |
| `REF-AUTOGPT-001` | [AutoGPT](https://github.com/Significant-Gravitas/AutoGPT)，Commit 未锁定 | `research_only` | Block/Workflow Builder、Preset、Marketplace UX | 未经许可证审查复用源码或商业模型 | Experience Catalog/Builder 概念；许可证待复核 |
| `REF-BROWSER-001` | [browser-use](https://github.com/browser-use/browser-use)，Commit 未锁定 | `research_only` | Browser 状态、动作模型和评测 | Browser 状态绕过 Capability/Sandbox/Recording 权限 | Browser Capability Provider；采用前需锁定基线 |
| `REF-MEMORY-001` | [Letta Code](https://github.com/letta-ai/letta-code)，Commit 未锁定 | `research_only` | Memory Block、长期上下文和 Skill 学习 | Provider 私有 Memory 成为跨 Runtime 公共事实 | Context/Memory Policy；待 Context Contract 后评审 |
| `REF-SANDBOX-001` | [Quicksand](https://github.com/microsoft/quicksand)、[E2B](https://github.com/e2b-dev/infra)、[Daytona](https://github.com/daytonaio/daytona)，Commit 未锁定 | `research_only` | VM/网络隔离/Snapshot、Sandbox 控制面、Workspace、Terminal/VNC 和容量模型 | 后端 Endpoint/VM/Pod 身份进入稳定 Schema；第三方 Snapshot 自证可移植 | SandboxProvider/Isolation Backend；采用前需兼容与许可证审查 |
| `REF-ENGINEERING-UX-001` | [LLM Space](https://github.com/deer-flow/llm-space)，Commit 未锁定 | `research_only` | Run Snapshot、Trace 调试、Run 对比和 Evaluation UX | 生产 Runtime、最终用户 Workbench、执行或计费事实源 | Agent Engineering Workbench 只读投影 |
| `REF-ECOSYSTEM-001` | Microsoft Agent Framework、Google ADK、Mastra、LlamaIndex、CrewAI，Commit 未锁定 | `research_only` | 多 Agent、Graph、文档和企业/云场景覆盖 | 为覆盖生态而建立通用框架对象或默认 Adapter | 场景雷达；具体采用项必须拆成独立 Reference ID |

## 与互操作标准的关系

本账本治理“从哪些框架/项目借鉴或复用什么”，不治理协议支持状态。MCP、Agent Skills/Skill Package、A2A、ACP 和 AG-UI 的 Role、Feature、Transport、版本锁定、映射与 Conformance 由 `56_AGENT_INTEROPERABILITY_PROTOCOLS.md` 及后续机器 Contract 单独管理。参考项目实现了某协议，不能证明本平台兼容该协议；本平台支持某协议，也不表示适配、依赖或认可该项目的私有架构。

协议 Adapter 若引入具体 SDK、Server、测试工具或源码，该依赖仍必须在本账本拆出独立 Reference ID，补齐 Commit、许可证、供应链、安全和复审证据。标准规范 Revision 与实现依赖 Revision 必须分别锁定，不能用 SDK 版本替代协议版本。

## OpenAI Codex 采纳说明

Codex 的可借鉴价值主要来自执行快照和私有模块边界，而不是其产品存储：

- Turn Context 固定一轮执行的模型、环境、权限、网络、工具和技能状态；更细的 Step Context 固定一次模型请求实际使用的 MCP/Capability/Tool/Environment 快照；
- Context Manager 对历史进行 copy-on-write snapshot、规范化、版本化、rollback 和 compaction，使“保存的历史”与“送给模型的历史”分离；
- Tool Router 同时持有模型可见 Tool Spec 和真实 Tool Registry，避免模型曝光集合与 Dispatch 能力漂移；
- Agent Graph Store 约束 child 最多一个 parent、列表稳定排序和按深度遍历，适合作为平台 AgentRun 树查询和控制 fan-out 的实现参考。

这些行为只能按本平台的 Tenant、ProviderRevision、RunManifest、Policy、Budget、Gateway、Invocation 和 AgentRun Contract 重新实现。Codex 的本地产品选择不形成平台兼容承诺。

## 复审与升级

出现以下任一条件必须复审对应 Reference ID：

- 准备复制源码、引入 package/image、运行其服务或公开宣称兼容；
- 上游许可证、Notice、安全公告、维护状态或数据模型发生变化；
- 平台准备改变公共 Contract、持久事实、Sandbox/Gateway 安全边界；
- 新版本要替换已采纳算法或改变用户可见行为；
- Conformance、故障注入或生产证据表明现有采纳不成立。

复审产生新的锁定快照和决策记录；不得原地把“未锁定”改写成对历史实施的追溯证明。
