# Agent Runtime 执行架构与契约演进

## 目的与权威边界

本文定义 Native Runtime 在真实 Agent Loop 实现前必须遵守的执行分层、可证明上下文、恢复和授权边界，并规定后续 Contract Revision 的最低语义。它不把任何参考项目的私有 Thread、Session、Graph、Checkpoint、SQLite、JSONL、Hook、审批或 Sandbox 模型提升为平台事实。

稳定平台主干保持不变：Business Authorization、Conversation、WorkOrder、Temporal Workflow、PostgreSQL Ledger、WorkflowRun、AgentRun、RunManifest、ProviderResolution、Invocation、CanonicalEvent、Artifact、TechnicalUsage、Gateway 和 Delivery 继续由既有所有者治理。本文新增的是 Runtime 私有执行内核及其与稳定 Port 之间的可验证交接，不创建第二套控制面。

## 五层执行模型

Native Runtime 内部采用以下逻辑分层：

```text
Prompt Policy / Revision
  -> Context Assembly
     -> Harness Step Snapshot
        -> Agent Loop
           -> Runtime-private Plan/Step Graph
              -> governed Model/Tool/Artifact/Egress/Sandbox Ports

Platform-owned WorkOrder / Temporal / AgentRun Graph / Invocation Ledger
  <- standard Runtime Command / Event / Checkpoint Reference / Usage Observation
```

这五层不是新的公共调用链，也不替代 AgentRuntimeProvider。Runtime 可以更换内部库、算法或语言实现，但必须继续通过版本化 Contract 输出同一类受治理事实。

### Prompt

Prompt 是版本化指令策略的求值结果，不是散落在代码中的字符串。Runtime 私有实现可以组合模型基础指令、Scenario、Experience、Skill 和安全提示，但每次模型请求必须能绑定：

- Prompt Policy/Builder Revision 与内容摘要；
- 模型基础指令 Revision、Scenario/Experience/Skill Revision；
- 与当前 Context、Tool Spec 和权限快照一致的最终请求摘要；
- 明确的敏感内容分类和正文保存策略。

`RunManifestV3` 和对应 Start 必须固化不含正文的 `PromptPolicyBindingV1`，至少绑定 Policy/Builder/Serializer Revision 与摘要、指令来源 Revision、角色优先级和内容保存策略。运行中改变任一绑定必须创建新的相容 Revision/Run，不能只在事后 Evidence 中记录漂移。

平台不要求保存明文 Prompt，也不允许普通日志或 Telemetry 成为 Prompt 事实源。

Prompt、System Message、Guardrail 和 Hook 都不是授权边界。即使模型或上下文指示绕过限制，Runtime 仍只能执行 Step Snapshot 已公开且由 Policy、Approval、Gateway、Invocation Ledger 和 Sandbox 独立允许的操作。

### Context

Conversation 历史、Workspace、Artifact、Memory 和检索结果只是候选来源，不等于模型上下文。Context Builder 在策略、信任和预算约束下生成有序、不可变、可解析的 ContextPackage。

Context 组装必须证明：使用哪个 Builder/Policy Revision、候选来源、选择与遗漏原因、确定性顺序、每项摘要、截断或摘要策略、预算分配、信任等级和最终 Assembly Digest。候选与遗漏证据只保存有界 identity/digest/reason，不复制未选中的敏感正文。`uniqueItems` 不能替代 `(kind, reference_id)` 或正式 item identity 的唯一性约束。

每个 Context Item 必须携带来源、内容分类、信任等级和允许的解释角色。不可信检索、网页、文件和 Tool 输出默认只能作为数据，不能因正文中出现指令文本就提升为 System/Developer 指令、扩大 Tool exposure、跳过 Approval 或获得 Egress/Secret 权限。Context Builder、Prompt Serializer 和 Conformance 必须覆盖该边界；最终安全结论仍由结构化 Policy/Gateway 执行，而不是依赖提示词服从。

引用内容只能采用以下两种方式之一：

1. 受 Start 请求总字节上限约束的闭合 inline content；
2. 通过 RunManifest 固化的 Context Resolver Binding 和短期读取授权解析的内容寻址引用。

裸 `reference_id`、进程本地路径、框架 Thread ID 或未授权的 Provider 私有存储都不能成为可执行解析协议。Context Resolver 可以复用受治理 Artifact/Capability 基础设施，但必须拥有独立的 Contract、Audience、Digest 和授权解释，不能靠实现约定猜测。

### Harness

Runtime 接受 Start 后创建一次 request-scoped `RuntimeTurnContext`，固定该次 AgentRuntimeRun 请求使用的默认 Model、Environment、Workspace、Network、Skill/MCP/Capability 配置、权限上限和 Context history 指针。这个名称借鉴 Codex 的 Turn Context 模式，但特意加上 Runtime 前缀，不能与平台 `ConversationTurn`、WorkOrder 或新的 Business ExecutionGrant 混用，也不进入公共 Contract。

Harness 在每次模型采样前从 `RuntimeTurnContext` 派生不可变 `StepContext`。对外可验证的投影称为 Step Snapshot；私有对象可以随 Runtime 实现变化，Evidence 所绑定的语义不能漂移。该 Snapshot 至少固定：

- AgentRun、RuntimeRun、Loop Step 和当前 Context history revision；
- Model Resolution、模型能力和有效上下文窗口；
- 模型可见 Tool Spec 集合及其 Catalog/Policy Revision；
- 实际可 Dispatch 的 Tool/Capability Registry；
- Environment、WorkspaceRevision、Sandbox Slot、Skill/Experience/Provider Revision，以及 MCP Connector/Tool Projection/Capability Binding；
- 当前 Budget、Policy、Permissions、Approval 和 Cancellation 状态。

模型可见 Tool Spec 与实际 Dispatch Registry 必须分离，但二者在同一 Step Snapshot 中闭合。模型不得看到当前步骤无权执行的工具；Dispatch 也不得执行未在该步骤公开且未通过直接受治理调用授权的工具。

MCP 动态 Tool 发现和 Skill 选择只能在 Step 之间生成新的不可变投影；它们不能在同一步中静默改变曝光或 Dispatch 集合。外部协议和 Skill 包的 Binding、导入、安全与 Conformance 见 `56_AGENT_INTEROPERABILITY_PROTOCOLS.md`。

### Loop

Agent Loop 只负责在一个 AgentRuntimeRun 内推进模型步骤、工具调用、等待、审批、压缩和终止。它不拥有商业授权、WorkOrder 终态、ProviderResolution、跨 Run 重试或平台对账结论。

每一步必须拥有稳定 `step_id`、输入证据摘要、开始/完成状态、预算预留与消费、模型结果、工具 Invocation 引用、等待原因和终止原因。模型请求失败与工具副作用结果未知必须使用不同状态；任何不确定 Mutation 都禁止由 Loop 自行重发，必须交给 Invocation Ledger 对账。

当前只提供 `start/cancel/checkpoint` 的私有接口属于 Runtime lifecycle driver，不应被当作完整 Agent Loop。实现时应将生命周期驱动器与 Agent Loop、Context Manager、Step Snapshot 和 Tool Router 分离。

### Graph

平台 Graph 与 Runtime Graph 必须分开：

- Platform AgentRun Graph 是受治理的单父执行树，拥有 Parent/Root/Depth、Admission、共享预算、控制 fan-out、孤儿对账和 WorkOrder 收敛语义；
- Runtime-private Graph 只表达一个 AgentRun 内的 Plan、Step、依赖或局部并行，可以随 ProviderRevision 改变；
- Runtime Graph 节点不能直接创建 Child AgentRun、宣告 WorkOrder 终态或替代 Temporal History；
- 需要新 AgentRun 时，Runtime 只能发出标准 Child Spawn Request，等待 Platform Admission。

每个 Runtime Graph revision 必须拥有内容摘要、稳定节点 identity、显式依赖和有界节点/边/就绪集/局部并行上限。Graph 更新产生新 revision，Checkpoint 绑定精确 revision 与已完成/运行中/未开始节点水位；声明为 DAG 的依赖发现环时 fail-closed。相同 revision 与 Step/Invocation 结果必须产生确定的 ready-set 顺序，恢复不能因集合遍历或进程重启改变 Dispatch 顺序，也不能重发结果未知的副作用。

## 模型步骤证据

真实 Agent Loop 前必须引入 `ModelStepEvidenceV1` 或等价闭合契约。每个模型请求至少绑定：

- `agent_run_id`、`runtime_run_id`、`step_id` 和父步骤；
- Prompt/Context Assembly、Model Resolution、Tool Spec Set、Harness Policy 的 Revision 与摘要；
- 模型请求摘要、响应摘要、Usage Observation 和终止类别；
- 关联的 Invocation、Approval、Artifact、Checkpoint 和 Runtime Event 序列范围；
- 内容分类、Redaction Profile 和加密正文引用。

CanonicalEvent 只保存有界 Evidence 引用和摘要。明文 Prompt、完整 Context、Reasoning、Token、凭据和工具敏感正文不得进入普通 Event、Trace、Metric 或日志。Platform 可以验证证据闭合，但不要求所有 Provider 暴露私有推理过程。

## 预算语义

执行限额必须区分：

- 单次模型请求上下文窗口、最大输入和最大输出；
- 单 AgentRun 累计模型请求、Token、时间、网络、存储和 Artifact；
- WorkOrder 共享累计预算、AgentRun 数、深度、并发和总资源；
- 预留、实际 Observation、释放、更正和超限时的 fail-closed 行为。

字段名称不能依赖实现猜测其作用域。`0` 的含义、单位、计数时点、并发竞争和累计方式必须由 Contract/semantic constraints 明确，不能由不同 Runtime 自行解释。

## Checkpoint 与恢复

Checkpoint 除了内容摘要和 Event Cursor，还必须绑定：

- `last_command_sequence` 和已消费 Command Digest；
- Context history revision、Loop step watermark 和 Graph revision；
- 已完成、未派发和结果未知的 Invocation 集合或其不可变对账摘要；
- in-flight non-idempotent side-effect watermark；
- Budget reservation/usage watermark；
- ProviderRevision、Runtime Revision、Compatibility Profile 和 Evidence。

Restore 必须先验证 CompatibilityDecision，再验证 Command/Event/Step/Invocation 水位。无法证明副作用是否发生时，恢复进入 reconciliation/waiting/failed，不得重新执行原 Mutation。Provider 原生 Checkpoint 仍默认只在同一 Revision 内有效。

## Runtime 调用 Authority

后续 Runtime Invocation Token Contract 必须把三类权限分开：

| Authority | 允许操作 | 必须绑定 | 禁止事项 |
|---|---|---|---|
| `execution` | Start、Append、Interrupt、Resume、Approval、Checkpoint，以及用户发起的 Pause/Cancel | 当前 RuntimeAuthorization、InvocationAttempt、Fencing、Policy、Budget、Permissions 和请求摘要；用户控制另绑定新的 WorkOrderControlRequest/ExecutionGrant | 越过商业期限、扩大权限、复用旧 Control Grant 或重发结果未知 Mutation |
| `observation` | Status、Events 和对账读取 | RuntimeRun、规范化读描述符；执行期读取绑定当前 RuntimeAuthorization，过期读取绑定 ReconciliationCase，安全确认读取绑定 SystemSafetyControl | 产生副作用、恢复执行或读取无关 Run |
| `reduction_control` | Platform Safety Controller 发起的 Pause/Cancel | SystemSafetyControl ID/Digest、目标 Run、Fencing 和闭合触发证据 | Resume、输入、批准、Checkpoint、Gateway 或新副作用 |

用户 Pause/Cancel 使用 `execution`，仍由新的 Business ExecutionGrant 授权；`reduction_control` 只表示 Platform Safety Controller 的系统减权，不能接受用户 ControlRequest，也不替代用户授权。旧 `safety_control` 语义保留在旧 Contract Revision 中，新语义通过版本化 Claims/Operation Profile 引入。

## Contract 演进要求

以下变更必须作为新的不可变 Contract Revision 发布，不能修改历史 Revision 的含义：

| 资源 | 目标变化 | 版本策略 |
|---|---|---|
| AgentRuntimeProvider OpenAPI | 关闭 Status/Event HTTP 400/429 响应 authority gap，并使错误分类、StandardError 和重试规则闭合 | 新的 v1 patch Contract Revision；旧 Revision 继续可解析 |
| Runtime Invocation Token Claims | 引入 `execution/observation/reduction_control` 及对应 authority binding | `AgentRuntimeInvocationTokenClaimsV2` |
| Prompt Policy Binding | 固化 Policy/Builder/Serializer Revision 与摘要、指令来源 Revision、角色优先级和内容保存策略，不保存明文 | `PromptPolicyBindingV1`，由 `RunManifestV3` 和 Start 固化 |
| Context Package | Builder/Policy、顺序、选择证据、预算、信任、解析绑定和 Assembly Digest | `ContextPackageV2` |
| Context Resolution | 将每类内容寻址引用绑定到受治理 Artifact/Capability Port 的 Contract、Audience、Route、Digest Profile 和短期读取授权要求 | `ContextResolverBindingV1`，由 `ContextPackageV2` 和 `RunManifestV3` 固化；不引入裸 Endpoint |
| Execution Limits/Budget | 单请求、AgentRun 累计与 WorkOrder 共享作用域 | `EffectiveExecutionLimitsV2` 及受影响 Budget Contract 新版本 |
| Model Step Evidence | 模型实际可见输入与执行快照的脱敏证据 | `ModelStepEvidenceV1` |
| Checkpoint | Command/Step/Invocation/副作用/预算水位 | `AgentRuntimeCheckpointManifestV2` |
| Run admission | 固化上述 Context、Budget、Evidence Policy 和 Checkpoint 版本 | `RunManifestV3`、`StartAgentRuntimeRunRequestV2` |
| Runtime Event Payload/Registry | 增加有界 Model Step Evidence 引用并保持 Payload 闭合 | `AgentRuntimeEventDataV2` + `agent-runtime-core-v2`，不修改 v1 Schema/Registry |
| Runtime Conformance | 验证 Context trust/确定性、Prompt injection 不扩权、Step、Tool exposure/dispatch、预算、Compaction、Graph revision/确定性恢复和副作用未知结果 | 新 `runtime-agent-loop-v1` Profile/Suite Revision |

Contract 实施必须同步 Schema/OpenAPI、semantic constraints、状态机、Registry、正反向 Fixture、Example、Manifest、Suite 和兼容性报告。只增加 Markdown 说明不能算 Contract 完成。

## 兼容与切换

- 旧 Run 始终使用其 RunManifest 和 ProviderResolution 锁定的旧 Contract/Profile，不原地迁移；
- 新 ProviderRevision 显式声明支持的 Context、Claims、Checkpoint、Event Registry 和 Conformance Revision；
- ProviderResolution 只为新 Run 选择双方共同支持且已准入的 Revision；
- v1/v2 双读只发生在明确兼容窗，写入使用目标 Revision 的唯一表示；
- 不兼容 Checkpoint 只能失败或创建新 AgentRun，不能静默转换；
- Application 更新 Blueprint/Contract lock 后必须重新生成 projection、运行历史载荷兼容测试和完整 Gate。

## 实施顺序与停止条件

固定顺序：

1. Blueprint/ADR 和参考采纳账本评审；
2. Read/Reconciliation authority 与 OpenAPI patch Contract Revision；
3. Prompt Policy Binding、Context/Resolver/Budget/ModelStepEvidence/Checkpoint/RunManifest/Start 的版本化 Contract；
4. Contract Gate、兼容性报告和新 Conformance Suite；
5. Application 重新锁定 Blueprint/Contract Revision；
6. Runtime lifecycle driver 重命名和私有五层接口实现；
7. 真实 Agent Loop、恢复、故障注入和 Conformance evidence；
8. 平台 authority/composition、端到端和生产可靠性分别验收。

若实现需要修改旧 Contract 迁就当前代码、让框架 Graph/Thread 成为平台事实、绕过 Gateway/Invocation Ledger、记录敏感模型正文、猜测引用解析方式或在未知副作用后自动重试，必须停止受影响范围并回到 Blueprint/Contract 评审。
