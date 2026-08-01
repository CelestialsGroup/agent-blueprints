# 执行治理与强制中介层

## 问题

ExecutionGrant 中的 Token、Sandbox、网络和外部通信限制必须可被实际执行。

如果任一 Runtime（包括 DeerFlow、LangGraph、OpenAI Agents SDK 或 Native Runtime）可以直接调用模型、MCP、HTTP 和外部工具，Grant 只能成为建议，无法成为安全边界。

## 强制中介

平台管理的生产运行必须通过：

```text
Agent Runtime
  ├── Model Gateway
  ├── Tool / MCP Gateway
  ├── Artifact Gateway
  └── Sandbox Egress Gateway
```

## Policy Decision Pipeline

执行前按以下顺序收集规则，但最终结果与配置加载顺序无关：

```text
CommercialAuthorization hard limits
+ Platform security policy
+ Tenant / ClientApplication policy
+ Scenario and Runtime Profile
-> deny > ask > allow
-> deny | Approval | governed execution
```

PolicyDecision 固化全部匹配规则摘要和 Effective Permissions Digest。`ask` 创建 Approval；任何匹配 Deny 都不能被 Tenant、用户记忆授权、Runtime 自报 Allow 或 Hook 覆盖。Policy Allow 之后仍必须通过 Invocation、Gateway、OS Sandbox、NetworkPolicy 和 Artifact Staging。

AgentRuntimeProvider 的每次调用还必须使用短期 RuntimeInvocation Token。Token 将 Tenant、ProviderRevision、WorkflowRun/AgentRun/RuntimeRun、RunManifest、RuntimeAuthorization、InvocationAttempt、Fencing、PolicyDecision、ExecutionBudget、Effective Permissions 和请求摘要绑定为一个不可混用的授权上下文；mTLS 只证明工作负载身份，不能替代对象级绑定。锁定的 Runtime v1 Contract 以 `safety_control` 共同表达短期读取和 Cancel/Pause，这是旧 Revision 的兼容事实；它不能恢复执行或产生新副作用。自动 Cancel/Pause 还必须绑定先于 Token 生效、由唯一 Platform Safety Controller workload 签发的不可变 SystemSafetyControl ID/Digest；该事实以闭合原因和触发证据证明平台为何拥有此次减权权限，不替代 Business ExecutionGrant，也不能授权任何扩权操作。

真实 Agent Loop 和生产 Runtime caller 接线前必须发布新的 Runtime Token Revision，将权限拆为：`execution` 承载当前 Business 授权下的 Start/推进命令，以及绑定新 WorkOrderControlRequest/ExecutionGrant 的用户 Pause/Cancel；`observation` 只读取 Status/Event，执行期绑定当前 RuntimeAuthorization，过期对账绑定 InvocationReconciliationCase，安全确认绑定 SystemSafetyControl；`reduction_control` 只允许唯一 Safety Controller 绑定 SystemSafetyControl 发送系统 Pause/Cancel。任何读取都绑定正式规范化读描述符和目标 RuntimeRun，三类 Token 不可跨操作或跨模式复用。完整迁移要求见 `54_AGENT_RUNTIME_EXECUTION_ARCHITECTURE.md`。

RunManifest 固化初始 Budget/Policy/Permissions 上限、ArtifactAccessRequirement、CommercialAuthorizationBinding（ID/Digest/`expires_at`）和授权续期规则。Runtime Start 携带本 Attempt 的完整 RuntimeAuthorization 与类型化 Model/Tool/Artifact/Egress Gateway Binding；每个 Binding 固化可执行 Contract ID/Digest、Route、Audience 和 Binding Digest。Authorization 内部作用域与摘要必须闭合，不能越过商业授权期限，ArtifactGrant 必须落在 Authorization 时间窗内。Token 过期、Adapter 重启或 Resume 通过前驱摘要链刷新 Authorization/ArtifactGrant，只能等价或缩权。

通用 Capability Provider 请求携带完整执行授权值并绑定 ProviderResolution/Instance/Audience。Invoke、Status、Cancel、Event Token 以 `operation_contract_id + operation_digest_profile + operation_request_digest` 绑定正式请求或操作描述符，不可跨操作复用；Invoke 的 `execution` 不越过原 deadline/CommercialAuthorization，后续连续 sequence/前驱 `jti` 的 `safety_control` 只用于 Status/Cancel/Event，不携带 Artifact 或新副作用权限。Model/Tool Gateway 复用该 Port；Artifact Read/Stage/Commit 同样绑定正式 Contract/Profile/Digest，Artifact/Egress 使用独立 OpenAPI 和最长 300 秒的操作 Token。ArtifactStagingGrant 只允许受限 Quarantine 上传/Commit，不能 Finalize；`plugin_id` 不属于稳定授权边界。

所有执行操作 Token 还校验生效下界：Runtime/Egress 不早于 RuntimeAuthorization，Capability/Sandbox 不早于其 Policy/Budget/Grant 准入，Artifact 不早于对应 ArtifactGrant/StagingGrant。只校验 `exp` 会留下授权尚未生效却可提前使用的窗口。

## 模型 Gateway

负责：

- Model Provider 路由
- Token 预算
- Request/Response Usage
- Model Allowlist
- Tenant、ClientApplication、Principal 与 WorkOrder/ArtifactOperation ExecutionScope 归属
- 超时和取消
- 内容与数据分类策略
- BYOK Secret 临时授权
- Usage 证据

Runtime 不得直接持有平台长期 Model Key。

## 工具 Gateway

具有外部副作用或需要审批的 Tool/MCP 调用必须：

1. 创建 Invocation。
2. 进行策略判断/审批。
3. 调用 Tool Provider。
4. 记录 Usage、Event 和结果。

只读、无副作用的本地工具也必须产生可审计 Run Event，但可按策略合并，不必为每个内部指令创建重型 Invocation。

## 出站 Gateway

Sandbox 默认无任意公网出口。

HTTP/DNS 出站通过受控 Egress Proxy：

- 域名和端口 Allowlist
- 阻止私网、Loopback、Link-local 和云元数据地址
- DNS Rebinding 防护
- 请求大小和响应大小限制
- 审计
- 数据分类策略

稳定请求只携带预注册 `destination_id + destination_revision_id + destination_revision_digest + destination_class + relative path`，禁止由 Runtime 提供原始 Origin。EgressDestinationRevision 固化 Platform/Tenant/ClientApplication Owner、HTTPS Origin、方法/路径/头、Redirect 和 DNS Policy；EffectivePermissions 按 `destination_class` 授权，不能把 `destination_id` 当成类别。权威传输契约为 `egress-gateway-v1`；Token 绑定 `http_exchange` Operation、Egress Request Contract ID、Digest Profile、Tenant/ClientApplication、RuntimeRun、InvocationAttempt、Fencing、DestinationRevision、Gateway Binding、RuntimeAuthorization、Request Digest、Policy、Budget 和 Permissions。

Kubernetes NetworkPolicy 不提供通用 FQDN 策略，因此不能单独承担域名 Allowlist。

## 受治理 Agent Runtime Profile

面向 SaaS 的 AgentRuntimeProvider 必须通过 `governed-v1` Conformance Profile：

- 支持预算注入
- 所有模型请求经过 Model Gateway
- 所有外部 Tool 请求经过 Tool Gateway
- 支持取消
- 支持 Usage
- 支持审批 Signal
- 支持 Event Cursor
- 不绕过 Sandbox 网络策略

未通过该 Profile 的 Runtime 只能用于受信任的私有部署。

## 预算

有效预算：

```text
min(
  ExecutionGrant 限制,
  Platform 安全上限,
  Scenario 限制,
  Provider 限制
)
```

平台必须在预算接近耗尽时发出事件，并在硬限制到达时停止后续调用。

ExecutionBudget 以 WorkOrder 为唯一共享硬上限，不能为每个 AgentRun 复制一份独立可消费额度。每个 AgentRun 另有不可变 AgentRunBudgetAllocation，但它只包含八类资源上限；所有 Gateway、Sandbox Lease、Child Admission 和 Usage 导入对同一个 PostgreSQL Budget Ledger 原子预留或扣减。`max_agent_runs`、`max_agent_depth` 与 `max_parallel_agent_runs` 只属于 WorkOrder ExecutionBudget，任一上限到达即拒绝 Child Admission，并在硬预算耗尽时对全部活动 Run 发起 Cancel fan-out。

模型预算还必须区分单次请求上下文窗口/输入/输出、AgentRun 累计模型调用与资源、WorkOrder 共享累计上限。每项定义单位、`0` 的含义、计数时点、Reservation/Observation/Release/Correction 和并发扣减规则；相同字段不得由不同 Runtime 分别解释为单次或累计。该语义通过新的 Execution Limits/Budget Contract Revision 引入，旧 Revision 不原地改义。

## Sandbox Provider

ExecutionBudgetEnforcer 在创建 SandboxSpec 前计算：

- 最大 Lease
- CPU/Memory/Storage/GPU
- 网络字节/策略
- Runtime Profile
- 必需 Capability

Provider 返回的 Usage 进入统一 Technical Usage，但平台仍可基于基础设施指标独立复核。

Sandbox Capability 发现只使用已准入控制面 mTLS；创建、恢复、状态读取、期望状态、Lease、Exec/Cancel/Result、Runtime Session、Snapshot/Manifest、终止、Operation 查询和 Event Stream 共 14 个操作分别绑定单操作 Token。写操作摘要覆盖去除 `request_digest` 的请求体；读操作摘要覆盖正式描述符，描述符包含规范化路径、Attempt/Fencing 和查询游标。
