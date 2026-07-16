# Agent Application Platform v0.8.1

一个可被多个业务产品复用的通用 Agent 工作、Artifact 和交付平台。

## 业务与 Agent 分离

Business Application 负责用户、会员、商品、订单和商业计费。

Agent Platform 负责 WorkOrder、Workflow、Agent Runtime、Sandbox、Plugin、Artifact、Technical Usage 和 Delivery。

## 扩展关系

```text
Scenario
  -> CapabilityDefinition
  -> ProviderResolution
  -> Immutable ProviderRevision
  -> PluginInstallation
```

## 安全执行

公共 SaaS Agent Runtime 必须经过：

- Model Gateway
- Tool/MCP Gateway
- Sandbox Egress Gateway
- Artifact Gateway

## 默认实现

- Agent Runtime：DeerFlow
- Durable Workflow：Temporal
- State：PostgreSQL
- Artifact Blob：S3-compatible Object Storage
- HTML：html-anything Plugin
- PPTX：html-to-pptx Job Plugin
- Sandbox：DeerFlow built-in，后续替换 sandbox-runtime

## 校验

```bash
python3 -m pip install -r requirements-contracts.txt
npm ci
./scripts/lint_contracts.sh
npm run bundle:openapi
```

本版本是 Phase 0 实施基线，不是未经实现验证即可直接上线的产品。


## Sandbox Provider

`DeerFlow Built-in Sandbox` 与未来的 `sandbox-runtime` 通过同一
`Sandbox Provider Contract` 接入。平台核心不依赖 Kubernetes Pod、
CRI、containerd、MicroVM 或 Apple Container 专用字段。
