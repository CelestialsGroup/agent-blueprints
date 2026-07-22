# Conversation 与 Turn 模型

## 所有权

Agent Platform 拥有 AgentConversation、ConversationMessage、分支身份、Conversation 内部序列、Conversation Workspace，以及为各 Turn 创建的 WorkOrder。Business 拥有 User、Organization、Membership，以及签发每个 ExecutionGrant 的权限。

```text
Business 用户
 -> AgentConversation
    -> 不可变 ConversationMessage[]
    -> 持久 Workspace
       -> ConversationBranch[]（Message Head、WorkspaceRevision Head、活动 WorkOrder、CAS 版本）
    -> WorkOrder[]（每个对应一个可执行 Turn）
       -> AgentRun / Invocation / Artifact / Recording
```

一次性 Scenario 调用在同一个准入事务中创建隐式 Conversation，因此批处理客户端不需要另一套交互模型。

Conversation 生命周期由 Contract 资源 `contracts/state-machines/conversation-v1.json` 治理：归档可恢复，删除是经过确认且不可逆的 Tombstone，生命周期时间戳必须可审计。

## Turn 事务

`POST /v1/conversations/{id}/turns` 原子执行：

1. 锁定 Conversation，并验证 WorkSession、新签发的 ExecutionGrant 和 CommercialAuthorizationSnapshot；
2. 验证 `request_contract_id`/请求摘要、`client_message_id`、父消息、分支 WorkspaceRevision Head 和 Experience 选择；
3. 追加不可变的用户 Message，并分配 `message_sequence`；
4. 创建一个引用同一 Conversation/Turn/Message 的 WorkOrder；
5. 写入 Workflow Start Outbox 和 CanonicalEvent；
6. 提交事务后才返回 202。

相同幂等键、Message ID 和请求摘要返回原 Turn；任一内容不匹配则返回 409。

`POST /v1/work-orders/{id}/control` 是另一条事务边界：它使用 `WorkOrderControlRequest` 和新的 ExecutionGrant 控制现有 WorkOrder，不创建 Turn。客户端只提交 `client_control_input_id + content`；平台验证 Grant 后原子分配 `input_id + input_message_id` 并追加不可变 Control Input，再由 Outbox 发送引用 `control_request_id + input_id + content_digest` 的 Runtime Command。Append/Interrupt 比较 `message_head_version + active_work_version`，Pause/Resume/Cancel/Approval 只比较 `active_work_version`，避免无关 Message 产生假冲突。只有内部 Checkpoint Command 不需要用户控制请求。

## 分支与并发

- `parent_message_id` 始终引用先前的不可变 Message。
- 分支从某个 Message 和当时的 WorkspaceRevision 派生，无需复制消息或文件内容。
- `ConversationBranch` 是可查询的分支头投影；Conversation 聚合不保存单一的全局活动 WorkOrder。
- 默认每个 Conversation 分支最多只有一个执行变更的活动 WorkOrder。
- `interrupt_and_enqueue` 记录活动 WorkOrder 的取消意图；不得把意图视为取消证明。
- `interrupt_and_enqueue` 同时创建独立后继 Turn/WorkOrder；Append/Interrupt 现有 Runtime 必须走 WorkOrder Control，二者不能共用含混命令。
- 并行分支使用独立的 WorkOrder、WorkspaceRevision Head 和 Sandbox Slot；只共享不可变的 Conversation/Artifact 历史。
- Message、Workspace 与 Active Work 分别使用独立 CAS；Sandbox 完成后只能以创建 Run 时的 Workspace Head/`workspace_head_version` 提交新 Revision，Steering 不得使文件提交产生假冲突。

## 上下文与记忆

Conversation 历史不等同于模型 Prompt。版本化 Context Builder Capability 在预算和策略约束下选择 Message、Artifact 和摘要。长期记忆、检索或摘要均由 Provider 实现，其精确 Revision 固化在 RunManifest 中。

## Session 授权

WorkSession 绑定 Conversation，并可选缩窄到一个 WorkOrder。每次可执行的后续输入仍需要 Business 新签发的 ExecutionGrant；浏览器 Session 永远不能变成无限制的商业授权。
