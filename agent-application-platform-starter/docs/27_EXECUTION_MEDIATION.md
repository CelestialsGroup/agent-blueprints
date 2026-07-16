# 执行治理与强制中介层

## 1. 问题

ExecutionGrant 中的 Token、Sandbox、网络和外部通信限制必须可被实际执行。

如果 DeerFlow 或其他 Runtime 可以直接调用模型、MCP、HTTP 和外部工具，Grant 只能成为建议，无法成为安全边界。

## 2. 强制中介

平台管理的生产运行必须通过：

```text
Agent Runtime
  ├── Model Gateway
  ├── Tool / MCP Gateway
  ├── Artifact Gateway
  └── Sandbox Egress Gateway
```

## 3. Model Gateway

负责：

- Model Provider 路由
- Token Budget
- Request/Response Usage
- Model Allowlist
- Tenant/WorkOrder Attribution
- Timeout 和取消
- 内容与数据分类策略
- BYOK Secret 临时授权
- Usage Evidence

Runtime 不得直接持有平台长期 Model Key。

## 4. Tool Gateway

具有外部副作用或需要审批的 Tool/MCP 调用必须：

1. 创建 Invocation。
2. 进行 Policy/Approval。
3. 调用 Tool Provider。
4. 记录 Usage、Event 和结果。

只读、无副作用的本地工具也必须产生可审计 Run Event，但可按策略合并，不必为每个内部指令创建重型 Invocation。

## 5. Egress Gateway

Sandbox 默认无任意公网出口。

HTTP/DNS 出站通过受控 Egress Proxy：

- 域名和端口 Allowlist
- 阻止私网、Loopback、Link-local 和云元数据地址
- DNS Rebinding 防护
- 请求大小和响应大小限制
- 审计
- 数据分类策略

Kubernetes NetworkPolicy 不提供通用 FQDN 策略，因此不能单独承担域名 Allowlist。

## 6. Governed Agent Runtime Profile

面向 SaaS 的 AgentRuntimeProvider 必须通过 `governed` Conformance Profile：

- 支持预算注入
- 所有模型请求经过 Model Gateway
- 所有外部 Tool 请求经过 Tool Gateway
- 支持 cancel
- 支持 usage
- 支持 approval signal
- 支持 Event Cursor
- 不绕过 Sandbox 网络策略

未通过该 Profile 的 Runtime 只能用于受信任的私有部署。

## 7. 预算

有效预算：

```text
min(
  ExecutionGrant limit,
  Platform safety ceiling,
  Scenario limit,
  Provider limit
)
```

平台必须在预算接近耗尽时发出事件，并在硬限制到达时停止后续调用。

## 8. Sandbox Provider

ExecutionBudgetEnforcer 在创建 SandboxSpec 前计算：

- Max lease
- CPU/Memory/Storage/GPU
- Network bytes/policy
- Runtime profile
- Required capabilities

Provider 返回的 Usage 进入统一 Technical Usage，但平台仍可基于基础设施指标独立复核。
