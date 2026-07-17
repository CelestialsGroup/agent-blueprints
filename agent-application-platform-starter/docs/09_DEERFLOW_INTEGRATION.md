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

## 7. 框架参考矩阵

| 框架 | 主要参考方向 | 推荐定位 |
|---|---|---|
| DeerFlow | 通用 Agent、研究/编码流程、Sandbox 协作 | 首个参考 Adapter |
| LangGraph / Deep Agents | 有状态循环、人工介入、长周期任务 | 通用 Runtime 候选 |
| OpenAI Agents SDK | 低抽象 Agent Loop、Handoff、MCP | 第二个最小 Adapter 候选 |
| Microsoft Agent Framework | Graph、多 Agent、OpenTelemetry、Python/.NET | 企业 Runtime Provider |
| LlamaIndex Workflows | 文档/RAG、事件驱动数据管道 | 场景型 Runtime/Capability Provider |
| Google ADK | GCP/Vertex AI 部署与调试 | GCP 场景 Runtime Provider |
| CrewAI | 角色式多 Agent 快速原型 | 受限场景 Provider，不作为内核 |
| Mastra | TypeScript、Workflow、Memory、Studio | TypeScript 场景 Provider |
| Native Runtime | 吸收多个实现的成熟模式 | 后期自有 Runtime |

该矩阵只用于指导调研和 Adapter 优先级，不构成准入。每个具体版本仍必须经过许可证/来源审查、ProviderAdmissionDecision 和目标 Profile 的一致性测试。

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
