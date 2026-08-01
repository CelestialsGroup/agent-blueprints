# Agent 项目总览

> 状态：Blueprint 已形成 Runtime 执行与 Agent 互操作架构候选；对应的新 Contract Revision 待发布，后续实现、集成、可靠性、正式冻结和生产批准独立判定
>
> 更新日期：2026-08-01

## 项目目标

Agent 项目的目标是构建一个类似 Manus 的通用、多租户 Agent 平台，为多个 Business Application 提供可治理、可恢复、可扩展的长任务执行能力。

平台需要支持：

- 研究、编码、浏览器操作、文件处理和内容生成等通用任务
- 多轮 Conversation、分支隔离的 WorkspaceRevision 和长任务恢复
- 平台治理的 Root/Sub-agent 执行树、共享预算、隔离 Workspace 和可恢复控制
- Chat、Plan、Timeline、Terminal、Browser、Desktop、Files 和 Artifact Workbench
- 实时 Sandbox 查看、Runtime Recording 和历史回放
- 可替换的 Agent Runtime、Sandbox、Model、Tool、Template、Renderer、Editor 和 Converter Provider
- 受治理的 MCP、Agent Skills/Skill Package，以及后续按场景启用的 A2A、ACP、AG-UI 互操作边界
- html-anything、Open Design、motion-anything、html-to-pptx 和 html-video 等 nexu-io 能力
- Business 自有的 User、Organization、Membership、Product、Order、Payment、Entitlement 和 Quota 系统
- 多租户安全、可观测性、可靠恢复、容量治理和长期升级能力

平台可以借鉴 DeerFlow、Dify、OpenHands、LangGraph、OpenAI Agents SDK、OpenAI Codex、Magentic-UI、Open Deep Research、OpenManus、AutoGPT、Grok Build、browser-use、E2B、Daytona、Quicksand、Letta Code 和 LLM Space，但这些项目只用于研究架构、能力和 UX，不在当前适配计划内，也不能成为平台依赖或稳定事实源。采纳、拒绝、锁定基线、许可证和复审状态统一记录在 `blueprint/docs/55_REFERENCE_ADOPTION_LEDGER.md`。生态协议/格式是另一条治理轴：支持 MCP 或 Skill Package 不表示适配上述项目，具体 Role、Feature、Transport、版本和 Conformance 见 `blueprint/docs/56_AGENT_INTEROPERABILITY_PROTOCOLS.md`。

LLM Space 只用于 Agent Engineering Workbench、Trace 调试、Run 对比和 Evaluation UX 参考，不作为生产 Runtime、最终用户 Workbench 或权威数据源。

## 工作区布局

| 目录 | 职责 | 治理边界 |
|---|---|---|
| `blueprint/` | 纯 Markdown 架构设计、领域边界、开发规范和验收标准 | 独立演进；不包含机器契约、产品源码或运行证据 |
| `contract/` | 只包含 Schema、OpenAPI、状态机、Event Registry、语义约束、Fixture、Conformance Suite 和示例 | 独立演进；只使用 Markdown、JSON、YAML，发布不可变 Contract Revision、Manifest Digest 和 Suite Digest |
| `script/` | Contract 校验器、生成器、依赖锁、临时构建物和 Gate 报告 | 非权威辅助工具；通过显式 Contract/Blueprint 根工作，不属于 Contract 内容 |
| `application/` | 产品源码、Migration、部署物、组件/集成测试和运行证据 | 分别锁定 Blueprint Revision 与 Contract Revision/Digest；未来可独立成库 |

当前同一 Git 根下的兄弟目录只用于开发便利。Blueprint、Contract 与 Application 三类产品不得依赖共同目录名或共同 Git History；Contract Scripts 通过 `AGENT_CONTRACT_ROOT` 和 `AGENT_BLUEPRINT_ROOT` 选择输入。完整规则见 `blueprint/docs/52_BLUEPRINT_CONTRACT_APPLICATION_BOUNDARY.md`。

## 当前状态

| 层级 | 状态 | 说明 |
|---|---|---|
| 产品边界 | 候选演进中 | 稳定平台主干保持不变；Runtime 五层执行架构和协议互操作边界已进入 Blueprint，尚未形成对应新 Contract Gate 结论 |
| 声明式契约 | 既有 Revision Gate 通过；新 Revision 待发布 | 精确 Manifest/Suite Digest 以绑定对应 Contract Checkout 的 Gate 报告为准；旧 Gate 不能证明新 Runtime 执行或 Agent 互操作契约 |
| 产品实现 | 分阶段推进 | 实时切片、命令、证据和未证明边界只以 `application/doc/plan/README.md` 及绑定源码的 evidence 为准；根 README 不复制易漂移的阶段号 |
| Phase 0 | 未完成 | 组件通过不等于 0B、0C-0G 集成、0H 可靠性或完整 Agent Loop 完成 |
| 生产可靠性 | 未证明 | 故障注入、隔离、容量、SLO、备份恢复和生产运行证据尚未完成 |

“契约验证通过”只表示对应不可变 Contract Revision 内部可接纳，不等于新 Blueprint 要求已进入 Contract，也不等于实现完成或生产就绪。

## 系统架构

```text
┌─────────────────────────────────────────────────────────────────────┐
│ Business Application                                                │
│ User / Organization / Membership / Product / Order / Payment        │
│ EntitlementRevision / QuotaReservation / Settlement                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ CommercialAuthorization
                               │ ExecutionGrant / WorkSession
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Agent Access 与稳定内核                                             │
│                                                                     │
│ Access / Tenant / Conversation / Message / Branch / WorkspaceRevision│
│ WorkOrder / WorkflowRun / AgentRun / Invocation / Event / Artifact  │
│ Budget / Policy / Provider Resolution / Usage / Audit               │
│ Sandbox Registry / Runtime Recording / Delivery                     │
└──────────────┬─────────────────────┬───────────────────┬────────────┘
               │                     │                   │
               ▼                     ▼                   ▼
       ┌──────────────┐      ┌──────────────┐    ┌──────────────────┐
       │ Temporal     │      │ PostgreSQL   │    │ Object Storage   │
       │ Workflow     │      │ State/Ledger │    │ Artifact/Record  │
       │ History      │      │ Outbox/Inbox │    │ Immutable Blob   │
       └──────────────┘      └──────────────┘    └──────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│ Provider 与执行平面                                                 │
│ AgentRuntimeProvider / SandboxProvider / Capability Provider        │
│ MCP / Skill Import / A2A / ACP / AG-UI Edge Adapter                 │
│ Model Gateway / Tool-MCP Gateway / Artifact Gateway / Egress Gateway│
│ Runtime Gateway                                                     │
└──────────────┬─────────────────────┬───────────────────┬────────────┘
               │                     │                   │
               ▼                     ▼                   ▼
       Native Runtime         Native Sandbox       nexu Catalog/
       Reference Probe        Isolation Backends   Editor/Converter
```

Redis 只用于 Cache、Presence 和持久化后的 Event Wakeup，不保存授权、账本、游标或运行终态。

## 数据所有权

| 所有者 | 权威数据 | 不得拥有 |
|---|---|---|
| Business Application | User、Organization、Membership、Product、Order、Payment、Refund、Invoice、Entitlement、商业余额与额度 | WorkOrder、Run、Event、Artifact、TechnicalUsage |
| Agent Platform | Conversation、Message、Branch、WorkspaceRevision、WorkOrder、Workflow、Invocation、Event、Artifact、TechnicalUsage、Delivery、Provider、Sandbox、Recording、Audit | 价格、支付、会员和商业余额 |
| Runtime Provider | 私有 Agent、Thread、Run、Checkpoint、Context 和原始 Event | Business 授权、Platform 终态和正式 ArtifactVersion |
| Sandbox Provider | Pod/VM/Container、内部 Endpoint、后端状态、Snapshot Payload 和底层指标 | 用户授权、WorkOrder 终态和 Artifact Metadata |
| Workbench | 用户交互和短期客户端状态 | 任何服务端权威事实 |

Business 与 Agent Platform 使用独立数据库，只通过版本化契约交换 CommercialAuthorization、ExecutionGrant、BusinessSettlementEnvelope 和 Delivery 结果；TechnicalUsage 原始事实仍由 Platform 拥有。

## 稳定内核

稳定内核负责不可被 Provider 替换的治理和技术事实：

- ClientApplication、ServicePrincipal、Tenant 和 Principal 映射
- AgentConversation、ConversationMessage、ConversationBranch、Workspace 和不可变 WorkspaceRevision
- WorkOrder、ExecutionGrant 消费、WorkflowRunRootBinding、Root/Child AgentRun、Child Spawn/Admission、共享 ExecutionBudget、AgentRun Resource Allocation、WorkspaceBinding、ControlFanout、Policy 和 Approval
- Invocation/SandboxOperation Ledger、Attempt、Fencing 和 Reconciliation
- CanonicalEvent、ArtifactVersion、TechnicalUsage 和 Delivery
- CapabilityDefinition、ProviderRevision、ProviderAdmissionDecision、带 Resolver/Input/Candidate/Evidence 的 ProviderResolution、Event Registry 和 Conformance Suite
- RuntimeSession 授权、RuntimeRecording Metadata、Chunk Manifest 和 Audit

稳定内核禁止保存 Kubernetes Pod、Namespace、Container、VM、Node、原始 Runtime Endpoint、框架私有 Thread/Checkpoint 或第三方 Trace 作为领域事实。

## Provider 扩展模型

```text
Scenario
 -> CapabilityDefinition
 -> ProviderResolution
 -> immutable ProviderRevision
 -> append-only ProviderAdmissionDecision
 -> Runtime / Sandbox / Model / Tool / Skill / Template / Converter Provider
```

每次 Run 在准入时锁定精确的 Tenant、Branch WorkspaceRevision、AgentRunWorkspaceBinding、ProviderResolution、ProviderRevision、AdmissionDecision、Scenario、Event Registry、Experience Revision、按需 Sandbox Slot、共享 WorkOrder Budget、单 Run Resource Allocation、授权/策略摘要和 RunManifest。Runtime 与 Sandbox Slot 只引用统一 ProviderResolution，不复制第二份 Revision/Conformance 快照。运行中的 Run 不允许因成本、健康状态或偏好变化静默切换 Provider。

Provider 原生 Checkpoint 默认只在同一 Revision 或明确声明并通过测试的兼容范围内恢复，不承诺跨框架可移植。

Native Runtime 内部采用 Prompt、Context、Harness、Loop 和 Runtime-private Graph 五层执行架构；平台 WorkOrder、Temporal、AgentRun Graph、Invocation Ledger 和 CanonicalEvent 不随内部框架变化。每个模型步骤固定同一 Context/Model/Tool/Environment/权限快照，并通过脱敏 ModelStepEvidence 绑定实际可见输入。完整设计及契约版本顺序见 `blueprint/docs/54_AGENT_RUNTIME_EXECUTION_ARCHITECTURE.md`。

外部协议只通过受治理 Adapter/Importer 接入。Phase 0 目标是 MCP Tool Client 和 Agent Skills/`SKILL.md` 包的最小、可验证支持；MCP Server、A2A、ACP（Agent Client Protocol）和 AG-UI 按 Phase 1 真实场景启用。任何协议都必须锁定 Role、Feature、Transport、版本、来源/目标和 Conformance，不能让外部 Session、Task、Event 或本地 Skill 目录成为平台事实。完整矩阵见 `blueprint/docs/56_AGENT_INTEROPERABILITY_PROTOCOLS.md`。

## Conversation 与执行链

Conversation 是多轮交互的长期聚合，拥有一个持久 Workspace、Branch WorkspaceRevision Head 和仅追加 Message 序列。每个可执行 Turn 创建一个 WorkOrder；并行 Branch 不共享可变文件头。

```text
Business 评估 Entitlement 并预留 Quota
 -> 签发 CommercialAuthorizationSnapshot + ExecutionGrant
 -> 创建或恢复 Conversation / Workspace
 -> 原子追加 Message、消费 Grant、创建 WorkOrder 和 Outbox
 -> Temporal 启动 WorkOrder Workflow
 -> 创建不含 Root 指针的 WorkflowRun
 -> ProviderResolution + Resolution Evidence
 -> 按 Capability 可选创建 SandboxProvider/Sandbox
 -> Root Admission 原子创建 RootBinding + AgentRun + RunManifest
 -> Native Runtime 经 AgentRuntimeProvider Port 启动
 -> Model/Tool/Artifact/Egress Gateway
 -> 按需 Child SpawnRequest -> Platform Admission -> Child AgentRun
 -> CanonicalEvent + Artifact Staging + TechnicalUsage
 -> Artifact Finalize + RuntimeRecording + Delivery
 -> Business Settlement / Release / Reconciliation
```

新 Turn 总是创建新的 WorkOrder；Append、Interrupt、Pause/Resume、Approval 和 Cancel 使用新的 ExecutionGrant 控制现有 WorkOrder，`interrupt_and_enqueue` 则明确记录取消意图并创建后继 WorkOrder。Parent Runtime 只能提出 ChildAgentRunSpawnRequest，Child 身份、Provider、预算、Workspace/Sandbox 和准入结论由 Platform 决定。每次 Runtime 调用使用短期 Token 绑定 Tenant、ProviderRevision、Run、InvocationAttempt、Fencing、Policy、Budget 和 Permissions。取消请求只表示意图，不等于 Provider 已停止执行。

Grok Build 的 Session Core/Presentation Adapter、Prompt Queue/Interjection、Background Task、Workspace Adapter、权限分层和 Telemetry Redaction 可用于 Runtime Harness。ACP、本地 JSONL/SQLite、宿主机 Bash、Hook 和私有 Checkpoint 仍是边缘或 Provider 私有实现，不进入平台事实源。

## Workbench

### Agent Workbench

面向最终用户，权限来自 Business WorkSession、ExecutionGrant 和 Entitlement。

| 视图 | 权威来源 |
|---|---|
| Chat | ConversationMessage、CanonicalEvent |
| Plan | 标准 Runtime/Canonical Event |
| Timeline | CanonicalEvent `work_sequence` |
| Terminal/Browser/Desktop | RuntimeSession、Runtime Gateway、RuntimeRecording |
| Files | Workspace、Artifact 和文件增量 Recording |
| Artifact | ArtifactVersion、Preview/Edit/Conversion Session |

### Agent Engineering Workbench

面向内部研发和运营，只消费 CanonicalEvent、RuntimeRecording、ArtifactVersion、RunManifest 和 TechnicalUsage 的只读投影。

原始证据不可编辑。修改 Prompt、Tool、Model 或消息只作用于调试副本；重新运行必须创建新的 ConversationBranch、WorkOrder、ExecutionGrant、ProviderResolution 和 RunManifest。

## Artifact 与 Runtime Recording

ArtifactVersion 内容不可变。Provider 只能写入 Artifact Staging，平台完成摘要、类型、大小、恶意内容、Tenant 和 Capability 校验后才能创建正式 ArtifactVersion。

RuntimeSession 是短期实时连接；RuntimeRecording 是 Platform 拥有的不可变历史资源；Sandbox Snapshot 捕获状态，不等于录制。

Runtime Gateway 使用按 Channel Cursor/Sequence、Connection Generation、ACK Window 和 Control ID + Digest；Port Forward 仅实时使用。窗口过期必须显式切换到只读 Recording，不能伪造无缝连续流。

```text
RuntimeRecording
 -> channel-local RuntimeRecordingChunk[]
 -> immutable ArtifactVersion[]
 -> RuntimeRecordingManifest
 -> work_sequence 对齐的历史回放
```

Terminal、Browser、Desktop 和文件增量的大块字节只有在 Emit-time Scrub/Schema Gate 通过后才能进入加密对象存储；未脱敏 Frame 只存在于有界内存，不进入 PostgreSQL、持久队列、Temporal History 或对象存储。

## 可靠性与安全

平台只承诺：

- 至少一次投递
- 幂等请求和幂等消费
- 严格递增 Fencing Token
- 事务 Outbox/Inbox
- 未知结果对账和人工复核
- 不可变 Revision、Event、Artifact 和 Recording
- PostgreSQL 当前状态与 Temporal History 对账

平台不宣称全局 Exactly-once。

公共 SaaS Runtime 必须经过 Model、Tool/MCP、Artifact 和 Egress Gateway。Sandbox 默认无公网出口、无平台长期密钥、无 Kubernetes API 权限，并通过 RLS、Object Storage Prefix、NetworkPolicy、Runtime Isolation 和对象级 Grant 实现多租户纵深防御。

## Phase 0 路线

```text
0A.2 架构与契约收口
 -> 0B 持久化脊柱与 Native Runtime Core
 -> 0C Business 到 Conversation
 -> 0D Native Runtime General/Governed 与 Native SandboxProvider
 -> 0E Workbench 与 Recording
 -> 0F nexu Experience
 -> 0G 独立 Reference Runtime Contract Probe
 -> 0H 故障、安全与恢复证据
```

Phase 0 的关键验收包括：

- Business 授权到 Conversation Turn 的真实纵向链路
- PostgreSQL Migration、Temporal Replay 和 Outbox/Inbox
- Native Runtime Core 先通过 `runtime-core-v1`，再扩展到 `runtime-general-v1 + governed-v1`
- 平台自有 Native AgentRuntimeProvider、SandboxProvider 与强制 Gateway 链路
- RootBinding、Child Spawn/Admission、共享预算、Workspace 隔离、子树控制、终态汇总和孤儿对账
- 独立 Reference Runtime Probe 不复用 Native Runtime 内部执行包，并通过 `runtime-core-v1` 证明 Port 可替换
- 同一 Workbench 消费 Native Runtime 与 Reference Probe 的标准 Event、Artifact 和 Usage
- html-anything Template 和至少一个 Converter Provider
- 完整 TechnicalUsage -> UsageReport -> 签名 Business Settlement Callback 链路，价格与余额仍只在 Business
- Terminal RuntimeSession、两个不可变 Recording Chunk 和离线回放
- 重复请求、响应丢失、旧 Fencing、Redis 丢失和 Adapter 重启测试
- NetworkPolicy、RBAC、Pod Security、容量和最小备份恢复证据

完成 Phase 0 只表示纵向实现和最小可靠性证据成立，不自动获得生产批准。

## 暂不实施

- 用户上传的任意 Plugin、完整 Marketplace 和收入分成
- 任意远程 JavaScript 或未隔离 UI Extension
- 完整 Office 编辑套件
- 持久 Evaluation/Rubric 生产领域模型
- 独立高密度 sandbox-runtime 后端和跨 Provider Process/Checkpoint 恢复
- 智能成本路由、多区域双活和大规模 Provider 管理界面

## 权威文档与实现

- [Blueprint 入口](blueprint/START_HERE.md)
- [架构基线](blueprint/docs/00_ARCHITECTURE_BASELINE.md)
- [架构决策](blueprint/docs/DECISIONS.md)
- [详细文档索引](blueprint/docs/README.md)
- [Phase 0 实施与验收](blueprint/tasks/PHASE0.md)
- [三类产品与辅助工具边界](blueprint/docs/52_BLUEPRINT_CONTRACT_APPLICATION_BOUNDARY.md)
- [声明式契约](contract/README.md)
- [契约校验脚本](script/README.md)
- [产品实现](application/README.md)

发生冲突时，以 Schema、OpenAPI、状态机、数据库约束和验证 Gate 为准。本文件是项目总览，不替代内部权威规范。
