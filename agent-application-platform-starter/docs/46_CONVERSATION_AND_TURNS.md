# Conversation 与 Turn 模型

## 所有权

Agent Platform 拥有 AgentConversation、ConversationMessage、分支身份、Conversation 内部序列、Conversation Workspace，以及为各 Turn 创建的 WorkOrder。Business 拥有 User、Organization、Membership，以及签发每个 ExecutionGrant 的权限。

```text
Business 用户
 -> AgentConversation
    -> 不可变 ConversationMessage[]
    -> ConversationBranch[]（分支头、派生点、活动 WorkOrder、CAS 版本）
    -> 持久 Workspace
    -> WorkOrder[]（每个对应一个可执行 Turn）
       -> AgentRun / Invocation / Artifact / Recording
```

一次性 Scenario 调用在同一个准入事务中创建隐式 Conversation，因此批处理客户端不需要另一套交互模型。

Conversation 生命周期由 `contracts/state-machines/conversation-v1.json` 治理：归档可恢复，删除是经过确认且不可逆的 Tombstone，生命周期时间戳必须可审计。

## Turn 事务

`POST /v1/conversations/{id}/turns` 原子执行：

1. 锁定 Conversation，并验证 WorkSession、新签发的 ExecutionGrant 和 CommercialAuthorizationSnapshot；
2. 验证 `client_message_id`、父消息、分支和 Experience 选择；
3. 追加不可变的用户 Message，并分配 `message_sequence`；
4. 创建一个引用同一 Conversation/Turn/Message 的 WorkOrder；
5. 写入 Workflow Start Outbox 和 CanonicalEvent；
6. 提交事务后才返回 202。

相同幂等键、Message ID 和请求摘要返回原 Turn；任一内容不匹配则返回 409。

## 分支与并发

- `parent_message_id` 始终引用先前的不可变 Message。
- 分支可以从某个 Message 派生，无需复制之前的消息。
- `ConversationBranch` 是可查询的分支头投影；Conversation 聚合不保存单一的全局活动 WorkOrder。
- 默认每个 Conversation 分支最多只有一个执行变更的活动 WorkOrder。
- `interrupt_and_enqueue` 记录活动 WorkOrder 的取消意图；不得把意图视为取消证明。
- 并行分支使用独立的 WorkOrder 和 Sandbox Slot，但共享不可变的 Conversation 历史。

## 上下文与记忆

Conversation 历史不等同于模型 Prompt。版本化 Context Builder Capability 在预算和策略约束下选择 Message、Artifact 和摘要。长期记忆、检索或摘要均由 Provider 实现，其精确 Revision 固化在 RunManifest 中。

## Session 授权

WorkSession 绑定 Conversation，并可选缩窄到一个 WorkOrder。每次可执行的后续输入仍需要 Business 新签发的 ExecutionGrant；浏览器 Session 永远不能变成无限制的商业授权。
