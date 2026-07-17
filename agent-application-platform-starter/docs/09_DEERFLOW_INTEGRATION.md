# DeerFlow 集成与升级

## 1. 定位

DeerFlow 是默认 Agent Runtime Provider，通过 `agent-runtime-provider-v1.yaml` 的防腐层 Adapter 接入。

不拥有：

- 用户与会员
- WorkOrder
- Artifact Metadata
- Usage Ledger
- Delivery
- Business Workflow

## 2. 受治理 Runtime

SaaS 部署中的 DeerFlow Adapter 必须实现受治理 Runtime Profile：

- Execution Budget 注入
- Model Gateway
- Tool/MCP Gateway
- Sandbox Egress Gateway
- Approval Signal
- Cancel
- Usage
- Event normalization
- Artifact 暂存/发现

DeerFlow 不得直接持有平台长期模型凭据，也不得绕过网络策略调用外部服务。

## 3. Adapter 职责

负责：

- Thread/Run 映射
- 启动/取消/恢复
- Event normalization
- Tool interception
- Usage mapping
- Artifact discovery
- Runtime/Sandbox 引用
- Error normalization

所有 Agent Runtime 调用本身经过 Invocation Ledger。

稳定操作包括 Capability 协商、启动/恢复 Run、仅追加 Command、Status、Cursor Event 和 Checkpoint Manifest。DeerFlow Thread/Run/Checkpoint ID 与原始 Event 只存在于 Adapter 私有存储。

`contracts/state-machines/agent-runtime-run-v1.json` 是标准化 Run 状态的权威来源。所有变更操作携带 InvocationAttempt、幂等信息和 Fencing；取消意图不等于取消证明，`outcome_unknown` 必须经 Ledger 对账后才能提交终态。

## 4. 多副本

长期目标：

- Checkpoint 外置
- Workspace/Sandbox 独立
- DeerFlow Pod 可替换
- Runtime ID 显式

若当前版本具有实例亲和性，RunManifest 固化 runtime_id，并由 Runtime Gateway 路由。

## 5. 升级

优先级：

1. Configuration
2. Skill
3. 通过受治理 Gateway 接入 MCP
4. External Adapter
5. Plugin Service
6. Gateway Extension
7. Core Patch

RunManifest 固化：

- DeerFlow Tag/Commit
- Image Digest
- Adapter Version
- Config Digest
- Provider Revision
- 受治理一致性报告

每次上游升级创建新的不可变 ProviderRevision。旧 Run 不迁移到新 Revision；Canary/Draining 必须保留旧 Checkpoint 和历史 Event 回放。Core Patch 需要 Patch Ledger、上游基础 Commit 和 Rebase 测试。

## 6. 契约测试

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

## 7. Sandbox 解耦

DeerFlow Adapter 通过平台 SandboxProvider Port 使用 Sandbox。

前期：

```text
SandboxProvider -> DeerFlowSandboxAdapter
```

后期：

```text
SandboxProvider -> sandbox-runtime
```

DeerFlow Thread/Run 与 Sandbox ID 映射保存在 Adapter，不进入平台 Sandbox 契约。
