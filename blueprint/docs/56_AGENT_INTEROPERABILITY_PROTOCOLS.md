# Agent 互操作协议与 Skill 包规范

## 目的与边界

本文定义 Agent Platform 如何支持主流 Agent 生态协议和可移植格式，同时保持平台自己的授权、账本、可靠性与事实所有权。互操作能力只存在于受治理的 Adapter、Importer 或 Gateway 边界；MCP Session、A2A Task、ACP Session、AG-UI Event、Skill 本地目录和任一 SDK 对象都不是平台稳定事实。

平台不建立一个把所有外部协议压成同一对象的“万能 Agent Protocol”。各协议解决的问题不同，必须分别映射到已有稳定语义：

```text
MCP Client/Server Adapter  -> Capability / Context / Invocation / Artifact
Skill Package Importer     -> immutable Artifact / Experience / Provider Revision
A2A Adapter                -> remote Provider / Child Spawn Admission / Artifact
ACP Edge Adapter           -> Agent Access / Runtime Session / Workbench Projection
AG-UI Projection Adapter   -> CanonicalEvent / Task / Artifact / Control Request

External protocol state != WorkOrder / AgentRun / RunManifest / Invocation Ledger
```

协议支持不等于依赖某个框架。Adapter 可以使用通过供应链审查的官方 SDK，但 SDK 类型、默认重试、Session 存储和权限模型不得进入公共 Contract 或替代平台控制面。

## 标准来源与版本治理

以下仅是 2026-08-01 的规范来源研究快照，用于确认标准身份，不是项目已经支持的版本基线：

| 标准 | 规范来源 | 研究快照 HEAD | 本文使用的身份 |
|---|---|---|---|
| MCP | [modelcontextprotocol/modelcontextprotocol](https://github.com/modelcontextprotocol/modelcontextprotocol) | `73763114e511106fc07543f6096b3a814b1a3583` | Model Context Protocol |
| Agent Skills | [agentskills/agentskills](https://github.com/agentskills/agentskills) | `38a2ff82958afee88dadf4831509e6f7e9d8ef4e` | Agent Skills / `SKILL.md` package format |
| A2A | [a2aproject/A2A](https://github.com/a2aproject/A2A) | `2cdf197805cf3eb780714f730cdfd24bce1c9998` | Agent2Agent Protocol |
| ACP | [agentclientprotocol/agent-client-protocol](https://github.com/agentclientprotocol/agent-client-protocol) | `6fa3b754bad74e8bc4210a7c53f7d70c10e1b704` | Agent Client Protocol |
| AG-UI | [ag-ui-protocol/ag-ui](https://github.com/ag-ui-protocol/ag-ui) | `bb1c2afddb4880309879b9564cfb3a635a5da4eb` | Agent-User Interaction Protocol |

进入 `contracted` 前必须锁定官方 Release/Tag/Specification Revision、内容摘要和快照日期；若上游只提供可变网页或 Branch，Contract 发布流程保存内容寻址的只读规范快照。协议 Revision、Adapter/SDK Revision 和目标 Server/Client 实现 Revision 分别记录，任何一项都不能代替另外两项。SDK、测试工具或源码成为依赖时，还必须在 `55_REFERENCE_ADOPTION_LEDGER.md` 建立独立 Reference ID 并完成许可证、Notice、供应链和安全审查。

## 支持状态

任何协议、Role、版本和 Transport 都按以下状态独立治理：

1. `tracked`：已识别标准和使用场景，只完成设计跟踪；
2. `contracted`：Binding、映射、错误、安全和 Conformance 已发布为不可变 Contract Revision；
3. `implemented`：Adapter/Importer 已实现，并绑定精确 Blueprint/Contract/Source Revision；
4. `certified`：目标 Conformance Profile 和负向安全测试通过，Evidence 内容寻址；
5. `enabled`：由 Tenant/Client/Scenario Policy 显式启用，并锁定 Role、版本、Transport、Feature Set 和 Destination/Source。

状态不能跳级。“Schema 中有字段”“安装了 SDK”“可以建立连接”或“单次调用成功”都不能宣称协议支持。当前 Blueprint 只形成目标和 Contract 待办；在对应 Contract、实现和 Evidence 完成前，项目不得对外宣称完整 MCP、Agent Skills、A2A、ACP 或 AG-UI 兼容。

## 目标支持矩阵

| 标准或格式 | 平台角色 | 目标阶段 | 最小支持范围 | 平台落点 | 当前结论 |
|---|---|---|---|---|---|
| MCP | Client | Phase 0 必须 | `initialize`/版本与能力协商、Tool 发现与调用；`stdio` 和 `streamable_http` 分 Profile，仅启用已认证 Profile | Tool/MCP Gateway、CapabilityDefinition、ProviderRevision、Invocation Ledger | 既有 Capability Port 和 Manifest 字段可复用；专用 Binding/Conformance 待发布 |
| Agent Skills / `SKILL.md` 包 | Importer/Consumer | Phase 0 必须 | 包校验、来源/许可证/签名/摘要、声明导入、不可变 Revision、按需受控执行 | ArtifactVersion、Experience Catalog、Skill ProviderRevision、Prompt/Context Binding | 既有 `skill`/`skill_pack` 类型可复用；标准 Manifest/Import Evidence 待发布 |
| MCP | Server | Phase 1 可选 | 只暴露已准入 Capability/Resource/Prompt 投影；每个调用重新授权 | MCP Edge Gateway、Capability/Artifact/Context 投影 | 不属于 Phase 0，不因 MCP Client 成立而自动成立 |
| A2A | Client/Server | Phase 1 按场景 | Agent Card/能力发现、Message/Task/Artifact 映射、取消和结果对账 | 远程 Provider、Child Spawn/Admission、Invocation/Artifact | 仅定义边界，待真实跨 Agent 需求后发布 Contract |
| ACP（Agent Client Protocol） | IDE/客户端 Edge | Phase 1 按场景 | Session、Prompt、Tool/Terminal/文件交互的边缘适配 | Agent Access、Runtime Gateway、Workbench Projection | `ACP` 在本文不指 Agent Communication Protocol；不得把客户端 Session 当平台事实 |
| AG-UI | UI Projection Edge | Phase 1 按场景 | 标准事件流投影和显式用户输入/控制回写 | CanonicalEvent、Task/Artifact Projection、Turn/Control API | 不替代 Runtime Event Registry 或 WorkOrder 状态机 |

每一行都必须继续拆分 Role、Feature Profile 和 Transport。例如通过 `mcp-client-tools-v1+stdio` 不能推导已支持 MCP Resources、Prompts、Sampling、Elicitation、远程 Authorization 或 MCP Server。

## MCP Client 边界

Phase 0 的 MCP 目标是受治理的 Tool Client Profile，不是让 Runtime 直接连接任意 Server。

```text
Runtime StepContext
 -> model-visible Tool Spec Snapshot
 -> Tool/MCP Gateway
 -> McpConnectorBindingV1
 -> admitted MCP Server
 -> normalized Capability Result / Event / Artifact Staging
```

`McpConnectorBindingV1` 至少固定：

- 标准标识、协议 Revision、Client Feature Profile、Transport Profile 和允许协商的版本集合；
- ProviderRevision、Connector Revision、SDK/Build Provenance 和 Conformance Set Digest；
- `stdio` 的受控 Sandbox/Command Revision，或 `streamable_http` 的 Owner-scoped DestinationRevision；
- Server identity、TLS/Authorization/Credential Profile、Audience、重定向与 DNS/IP Policy；
- Tool/Resource/Prompt allowlist、Schema Digest、内容分类和最大载荷/并发/超时；
- Session 恢复策略、通知策略和 negotiated capability digest；
- Gateway Route、Binding Digest 和禁用 Feature 集合。

连接建立时只能在 Binding 的允许集合中选择版本和能力；无交集、未知必需能力、Server 身份变化、Schema 漂移或降级到未准入 Transport 时 fail-closed。协商结果形成不可变 Session/Negotiation Evidence，并被创建该连接后续 Step Snapshot 引用。MCP Session ID、进程 ID、原始 URL 和 SDK 对象保持 Gateway 私有。

Phase 0 的两个 Transport 分开认证：

- `stdio` 只在已准入 Sandbox/Provider 中启动签名且内容寻址的 Command，不允许宿主机任意命令、继承平台环境变量或访问平台长期凭据；
- `streamable_http` 只经 Egress/Credential Policy 到预注册 DestinationRevision，不接受 WorkOrder、Skill 或 Server 返回的任意 URL，不绕过 TLS、Redirect、DNS rebinding、SSRF 和数据驻留检查。

### Tool 映射

MCP Tool 只有经过 Catalog/Policy 投影后才成为模型可见 Tool Spec。每个投影必须绑定 Server/Tool identity、input/output Schema Digest、CapabilityDefinition、side-effect class、幂等/取消/进度声明和风险级别。缺失或无法证明的副作用与幂等信息采用最保守值，不能因 Server 自报而自动获得安全属性。

每次 `tools/call` 创建平台 Capability Invocation/Attempt，使用短期单操作 Token、Fencing、预算、Approval、ArtifactGrant/StagingGrant 和结果对账。MCP 错误、进度、结构化内容与 Artifact 先由 Adapter 验证并标准化，再进入 Capability Result、CanonicalEvent 或 Artifact Staging。连接断开或响应丢失不能由 MCP SDK 自动重发未知副作用。

Tool 列表或 Schema 变化只能产生新的 Tool Projection/Step Snapshot；正在执行的 Step 不动态扩展 Tool exposure。Server 通知不是平台准入事实，也不能直接撤销或新增 Capability。

### Context 与反向请求

MCP Resource/Prompt 返回内容始终是不可信 Context 候选，必须经过 Context Builder 的来源、内容分类、预算和 Prompt-injection 边界，不能成为 System 指令或权限。Phase 0 不因支持 Tool Client 自动支持 Resource/Prompt Profile。

Server 发起的 Sampling、Elicitation、Roots 或其他反向请求默认禁用。未来启用时必须拥有独立 Feature Profile、用户交互语义、模型/文件最小授权、预算和 Conformance；不得借用原 Tool Call 的权限。

## MCP Server 边界

MCP Server 是 Phase 1 的外部投影 Adapter，不是 Platform Core 的第二套 API。它只能暴露显式发布且已准入的 Capability、Resource 或 Prompt Projection，并在每次请求时重新执行 Tenant、Client、Principal、Entitlement、Policy、Quota 和对象授权。

外部 MCP Client 不能提交或选择 WorkOrder、AgentRun、ProviderResolution、PolicyDecision、ExecutionBudget、ArtifactGrant、InvocationAttempt 或 Fencing 等平台事实。需要执行 Turn 或控制 WorkOrder 时，Adapter 必须调用正式 Agent Access API；MCP 的 Session/Request/Progress/Cancel 只作为边缘关联和传输证据。

## Skill Package 与 Importer

Skill 是可移植的指令、资源、脚本和元数据包，不是统一的远程调用 Wire Protocol。平台支持的是锁定格式 Revision 的导入与消费，不把某个客户端的本地 Skill 目录、发现顺序或自动执行规则变成公共语义。

导入流程固定为：

```text
registered source / upload
 -> quarantine Artifact
 -> package/path/size/signature/license/security validation
 -> SkillPackageManifestV1 normalization
 -> SkillImportEvidenceV1
 -> immutable ArtifactVersion + Experience Revision
 -> optional admitted Skill ProviderRevision
 -> Tenant/Client/Scenario enablement
```

`SkillPackageManifestV1` 至少固定：

- Format ID/Revision、Package ID/Version/Digest、入口文件和规范化文件清单；
- 名称、描述、发布者、许可证/Notice、Source Revision、签名和 Build Provenance；
- Prompt/Instruction、Reference、Asset、Script 的独立摘要与内容分类；
- 声明的 Capability、模型/Runtime 兼容范围、依赖和参数 Schema；
- 请求的 Tool、Sandbox、Workspace、Artifact、Network、Secret 和副作用权限；
- 安装/激活约束、生命周期、替代版本和兼容性范围。

`SkillImportEvidenceV1` 至少记录 Source、Fetcher/Importer/Scanner Revision、原始包和规范化 Manifest Digest、每项校验结论、拒绝/警告 Reason Code、许可证/签名/恶意内容扫描、输出 Artifact/Experience/Provider Revision 和审批主体。Importer 不得边验证边在控制面执行脚本。

以下规则始终成立：

- `SKILL.md` 正文和附带文件是不可信内容，不因格式合法而获得 Developer/System 优先级；
- 相对路径必须归一化并限制在包根，拒绝路径穿越、危险符号链接、特殊文件、重复规范化路径、解压炸弹和超限文件；
- Script 只能作为内容寻址的受控 Sandbox Command 或已准入 Provider 实现执行，不在 API/Worker/Importer 宿主机执行；
- Manifest 中声明权限只是请求，最终权限由 Business/Platform Policy、Approval、RunManifest、Gateway 和 Sandbox 独立收窄；
- Remote include、安装期下载、动态依赖和任意 URL 默认拒绝；需要网络时必须转成锁定来源、SBOM 和 DestinationRevision；
- Run 只选择不可变 Experience/Skill/Provider Revision；修改包内容创建新 Revision，旧 Run 不漂移；
- StepContext 固定本步骤实际启用的 Skill Revision、注入摘要、公开 Tool 集合和 Dispatch Binding，Skill 不能在步骤中静默自更新。

## A2A、ACP 与 AG-UI 映射

| 外部概念 | 平台映射 | 不允许的解释 |
|---|---|---|
| A2A Agent Card / capability | 已准入远程 ProviderRevision + CapabilityDefinition/Resolution | 远程自报即可通过准入 |
| A2A Task / context | Adapter 私有关联 + Invocation 或已准入 Child AgentRun | 直接成为 WorkOrder/AgentRun/RunManifest |
| A2A Message / Artifact | 有界输入、CanonicalEvent 投影或 Artifact Staging/Version | 远程载荷直接成为正式 Artifact 或平台终态 |
| ACP Session / Prompt | WorkSession/Conversation/Turn API 的边缘关联 | 客户端 Session 成为 Conversation 或授权事实 |
| ACP Tool/Terminal/File | Capability、Runtime Gateway、WorkspaceRevision API | IDE 直接访问 Provider Endpoint、Sandbox 或宿主文件系统 |
| AG-UI Run/Task/Event | CanonicalEvent/Task/Artifact 的版本化 UI 投影 | AG-UI Event 反向成为 Runtime Registry 或账本事实 |
| AG-UI user action | 新 Turn 或显式 WorkOrderControlRequest + ExecutionGrant | UI Event 直接修改 WorkOrder、Approval 或 Runtime 状态 |

A2A 远程委派不能绕过 Child Spawn/Admission。若语义上需要新的 Sub-agent，Platform 先完成 Parent/Root/Depth、共享预算、ProviderResolution、Workspace/Sandbox 和 Policy 准入，再由选定 Provider 使用 A2A；远程 Task ID 只保存在 Adapter/Invocation evidence。A2A 状态需要通过版本化映射和对账证据才能影响平台聚合状态。

ACP 和 AG-UI 都是 Presentation/Client Edge。它们可以改善 IDE、Headless Client 或 Workbench 的互操作体验，但不能替代 Agent Access、Runtime Gateway、CanonicalEvent Registry、Artifact API 或 Business Grant。本文中的 `ACP` 必须写全为 Agent Client Protocol，Contract ID/namespace 不使用含混缩写。

## 安全与多租户

所有互操作 Adapter/Importer 必须满足：

- 使用独立 Workload Identity、最小 RBAC、NetworkPolicy、资源限制、超时、背压和 Draining；
- 外部身份映射到 Tenant/Client/Principal 后再解析 Provider/Capability，不信任外部 Tenant 或对象 ID；
- Credential 只经短期、单目标 Credential Gateway Token 获取，不进入 Prompt、Skill 包、Event、日志或 SDK 持久缓存；
- 输入、通知、Schema、Tool 名称、Metadata 和 Error 均有闭合上限，未知字段按锁定协议的兼容规则处理；
- 动态发现只产生候选，不自动认证、启用、扩权或覆盖已锁定 Revision；
- 所有外部内容经过内容分类、恶意载荷、Prompt injection、Secret/PII 和 Artifact 校验；
- Adapter 崩溃、网络分区、重复/乱序、响应丢失、版本漂移和撤销必须进入幂等/Fencing/对账语义；
- 日志只保存有界标识、Revision 和摘要，不保存明文 Prompt、完整 Context、Credential 或第三方敏感 Payload。

## Contract 与 Conformance 演进

Phase 0 在实现前至少发布：

| 资源 | 最低语义 |
|---|---|
| `McpConnectorBindingV1` | 协议/Feature/Transport、版本集合、Server/Destination/Command、身份/凭据、allowlist、上限、Session/通知策略和 Binding Digest |
| MCP Tool Projection Contract | MCP Tool Schema 到 CapabilityDefinition/side-effect/idempotency/cancel/progress/Artifact 的不可变映射 |
| MCP Negotiation Evidence | 请求/响应版本与能力、Server identity、Schema/Tool Set Digest、降级/拒绝 Reason Code |
| `SkillPackageManifestV1` | 标准格式、内容清单、来源/许可证/签名、Capability/依赖、权限请求和不可变摘要 |
| `SkillImportEvidenceV1` | Fetch/Quarantine/Validation/Normalization/Scan/Admission 的逐项证据和输出 Revision |
| Conformance Suite | `mcp-client-tools-v1` 的 `stdio`/`streamable_http` 分 Profile，以及 `skill-package-import-v1` 的正反向 Fixture 与攻击样例 |

这些资源必须同步 Schema、semantic constraints、Fixture、Example、Manifest、兼容性报告和消费者双版本测试。MCP Profile 至少覆盖版本无交集、能力谎报、Tool Schema 漂移、列表变化、重复/丢失响应、取消、超限、Credential/SSRF、Prompt injection、未知副作用和旧 Fencing；Skill Profile 至少覆盖路径穿越、符号链接、重复路径、超限/解压炸弹、签名/摘要、远程引用、脚本隔离、权限扩张、Revision 漂移和许可证证据。

后续 A2A、ACP、AG-UI 和 MCP Server 必须各自发布专用 Binding/Mapping/Suite。不得为了提前占位而扩展 `McpConnectorBindingV1` 或创建无语义边界的通用 Envelope。

## Phase 0、Phase 1 与停止条件

Phase 0 只要求：

1. 发布并通过 MCP Tool Client 与 Skill Package Import 的机器 Contract/Conformance；
2. 实现并认证至少一个锁定 MCP Transport Profile 的受治理纵向调用，以及一个 Skill 包隔离导入/选择/执行纵向链路；其他 Transport 只保持其实际达到的状态；
3. 证明 Runtime 不能绕过 Gateway、Skill 不能扩权、动态发现不能改变正在执行的 Step Snapshot；
4. 将协议 Evidence 绑定精确 Blueprint/Contract/Provider/Adapter Revision，且不提升为完整生态兼容或生产证明。

Phase 1 才按真实产品场景选择 MCP Server、MCP Context/反向请求、A2A、ACP 或 AG-UI。每项必须有 Owner、Threat Model、目标实现互操作矩阵、版本/Transport 范围、Canary、Rollback 和停用策略；“主流”本身不是启用理由。

如果实现要求 Runtime 直连外部 Server、把本地 Skill 目录作为可变事实源、信任远端权限/状态、绕过 Child Admission/Invocation Ledger、把协议 Session/Task/Event 写成平台权威、静默降级版本、自动执行导入脚本或在未知副作用后重试，必须停止受影响范围并回到 Blueprint/Contract 评审。
