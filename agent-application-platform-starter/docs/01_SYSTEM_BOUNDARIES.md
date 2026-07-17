# 系统边界与数据所有权

## Business Application

唯一事实源：

- User/Login
- Organization Membership
- Membership/Product
- Order/Payment/Refund
- Commercial Entitlement/Quota
- Entitlement Revision/Quota Reservation/Settlement
- Price/Invoice
- Business Notification

## Agent Platform

唯一事实源：

- ClientApplication
- InternalTenant/Principal Mapping
- AgentConversation/ConversationMessage
- WorkOrder/Workspace
- GrantConsumption
- WorkflowRun/AgentRun
- Invocation
- CanonicalEvent
- Artifact/Version/Staging
- TechnicalUsage
- Delivery
- Provider Revision/Resolution
- RuntimeRecording/Playback Manifest
- Experience Catalog/Immutable Revision

## Plugin

Plugin 只负责执行能力。

禁止：

- 查询业务数据库
- 查询平台数据库
- 自行判断会员
- 修改 Run 状态
- 创建正式 ArtifactVersion
- 自行结算 Usage
- 自行决定 Trust

## 外部引用

禁止 WorkOrder 提供任意 URL。

外部内容通过：

- Artifact Ingest Session
- 预注册 Storage Connector
- 已存在 Artifact Reference
- 预注册 Callback/Delivery Target

## 身份映射

```text
client_app_id         <- Service OAuth
external tenant/user  <- ExecutionGrant
internal tenant/user  <- Agent Platform Mapping
```

平台内部访问控制只使用内部 ID。

## Sandbox 数据所有权

Agent Platform 是以下对象的事实源：

- Sandbox identity and tenant/work mapping
- Desired state
- Lease policy
- Provider resolution
- RuntimeSession user authorization
- Normalized usage
- Audit

Sandbox Provider 是以下数据的事实源：

- Observed backend state
- Backend operation status
- Internal runtime endpoint
- Backend metrics
- Snapshot payload

Provider 私有 Pod/VM/Container ID 不进入公共 Contract。
