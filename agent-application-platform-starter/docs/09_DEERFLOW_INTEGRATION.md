# DeerFlow 集成与升级

## 1. 定位

DeerFlow 是默认 Agent Runtime Provider，通过 `agent-runtime-provider-v1.yaml` 的 Anti-Corruption Adapter 接入。

不拥有：

- 用户与会员
- WorkOrder
- Artifact Metadata
- Usage Ledger
- Delivery
- Business Workflow

## 2. Governed Runtime

SaaS 部署中的 DeerFlow Adapter 必须实现 Governed Runtime Profile：

- Execution Budget 注入
- Model Gateway
- Tool/MCP Gateway
- Sandbox Egress Gateway
- Approval Signal
- Cancel
- Usage
- Event normalization
- Artifact staging/discovery

DeerFlow 不得直接持有平台长期模型凭据，也不得绕过网络策略调用外部服务。

## 3. Adapter

负责：

- Thread/Run mapping
- Start/Cancel/Resume
- Event normalization
- Tool interception
- Usage mapping
- Artifact discovery
- Runtime/Sandbox reference
- Error normalization

所有 Agent Runtime 调用本身经过 Invocation Ledger。

稳定操作是 capability negotiation、start/restore run、append-only command、status、cursor event 和 checkpoint manifest。DeerFlow Thread/Run/Checkpoint ID 与原始事件只存在于 Adapter Private Store。

`contracts/state-machines/agent-runtime-run-v1.json` 是 normalized run status 的权威来源。所有 mutation 携带 InvocationAttempt、idempotency 和 fencing；cancel intent 不等于取消证明，`outcome_unknown` 必须经 Ledger 对账后才能提交终态。

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
3. MCP through governed gateway
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
- Governed Conformance Report

每次上游升级创建新的 immutable ProviderRevision。旧 Run 不迁移到新 Revision；canary/draining 必须保留旧 checkpoint 和历史事件 replay。Core Patch 需要 patch ledger、上游 base commit 和 rebase test。

## 6. Contract Test

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
- Runtime failure recovery
- Append-input/interrupt command fencing
- Checkpoint export/restore compatibility
- Old ProviderRevision event golden-file normalization

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

DeerFlow Thread/Run 与 Sandbox ID 映射保存在 Adapter，不进入平台 Sandbox Contract。
