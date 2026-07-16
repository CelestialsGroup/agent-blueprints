# DeerFlow 集成与升级

## 1. 定位

DeerFlow 是默认 Agent Runtime Plugin。

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
