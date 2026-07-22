# 系统边界与数据所有权

## Business Application 边界

唯一事实源：

- 用户/登录
- 组织成员关系
- 会员/产品
- 订单/支付/退款
- 商业权益/额度
- Entitlement Revision/额度 Reservation/Settlement
- 价格/发票
- Business 通知

## Agent Platform 边界

唯一事实源：

- ClientApplication
- InternalTenant/Principal 映射
- AgentConversation/ConversationBranch/ConversationMessage
- Conversation Workspace/Branch WorkspaceRevision/WorkOrder
- GrantConsumption
- WorkflowRun/AgentRun
- Invocation
- CanonicalEvent
- Artifact/Version/暂存区
- TechnicalUsage
- Delivery
- Provider Revision/Resolution
- RuntimeRecording/回放 Manifest
- Experience Catalog/不可变 Revision

## Plugin 边界

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

- Artifact 导入 Session
- 预注册 Storage Connector
- 已存在 Artifact Reference
- 预注册 Callback/Delivery Target

## 身份映射

```text
client_app_id         <- Service OAuth
外部 tenant/user      <- ExecutionGrant
内部 tenant/user      <- Agent Platform 映射
```

平台内部访问控制只使用内部 ID。

## Sandbox 数据所有权

Agent Platform 是以下对象的事实源：

- Sandbox 身份与 Tenant/Work 映射
- Desired state
- Lease policy
- Provider resolution
- RuntimeSession 用户授权
- Normalized usage
- Audit

Sandbox Provider 是以下数据的事实源：

- 后端观测状态
- 后端 Operation 状态
- 内部 Runtime Endpoint
- 后端指标
- Snapshot Payload

Provider 私有 Pod/VM/Container ID 不进入公共契约。
