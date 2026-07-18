# 数据模型不变量 — v0.9.0

以下约束必须由 PostgreSQL Migration/Constraint 实现，不能只由应用代码约定。

## 身份与工作执行

- `(tenant_id, external_subject)` 唯一；所有业务表显式 tenant_id。
- `work_orders(tenant_id, idempotency_key_digest)` 唯一。
- ExecutionGrant `jti` 单次消费，消费记录唯一；过期时间、Request/Scenario/Idempotency 摘要必须匹配。
- `conversations(conversation_id)` 主键；`(tenant_id, client_app_id, client_conversation_key)` 唯一。
- `conversation_messages(message_id)` 主键；`(conversation_id, message_sequence)` 与 `(conversation_id, client_message_id)` 唯一；Message 仅允许追加。
- `conversation_branches(conversation_id, branch_id)` 主键；Head Message/Sequence 与 Fork Point 必须引用同一 Conversation 的先前 Message；`branch_version` 用于 Compare-and-swap。
- `parent_message_id` 只能引用同一 Conversation 中 Sequence 更小的 Message；每个 Branch 默认最多一个活动 WorkOrder，不能用 Conversation 顶层单值表达并行分支。
- Conversation Turn 事务原子完成 Message Sequence、WorkOrder、GrantConsumption、Workflow Start Outbox 和 CanonicalEvent。
- WorkOrder、ExecutionGrant、RunManifest 和 CanonicalEvent 的 Conversation/Turn/Branch/Input Message 绑定必须一致。
- `workflow_runs(workflow_run_id)` 与 `work_orders(work_order_id)` 一对一；显式 `tenant_id` 必须一致，`root_agent_run_id` 唯一引用同一 WorkflowRun 的 Root；Temporal Continue-as-New 或未来编排器分段不能创建第二个平台 WorkflowRun。
- `agent_runs(agent_run_id)` 显式绑定 Tenant、WorkflowRun、RunManifest 和 `runtime_run_id`；每个 WorkOrder 恰好一个 Root AgentRun，Sub-agent 的 Parent/Root 必须属于同一 Tenant/WorkOrder/WorkflowRun。
- RunManifest 的 `agent_runtime.resolution_id` 必须引用恰好一个 Agent Runtime ProviderResolution，并与 AgentRun 的 `runtime_provider_resolution_id` 相同；禁止复制第二份 Runtime Revision/Conformance 快照。
- Conversation 生命周期必须遵循 `conversation-v1`；`archived`/`deleted` 写入相应审计时间，`deleted` 不可恢复。
- CommercialAuthorizationSnapshot ID/摘要、显式 Entitlement/Capability/Limit 和 Quota Reservation 引用随 WorkOrder 固化；Limit 摘要必须闭合，Platform 无权更新 Business Entitlement/Balance。

## Invocation

- `invocations(invocation_id)` 主键；`logical_invocation_key` 唯一。
- `invocation_attempts(attempt_id)` 主键；`(invocation_id, attempt_number)` 唯一。
- `(invocation_id, fencing_token)` 唯一，且新 Attempt Token 单调递增。
- Attempt 编号必须从 1 连续；`InvocationRecord.attempt_count` 等于已持久化 Attempt 数量，`current_attempt_id` 引用编号最大的 Attempt；所有 Attempt 绑定相同的不可变 `request_digest`。
- 一个 Attempt 只能绑定 Result 或 Error；`succeeded` 必须有 Result，`failed`/`outcome_unknown` 必须有相应 Error。
- Invocation 活动状态必须绑定 `current_attempt_id`；`attempt_count <= max_attempts` 必须有 CHECK/事务约束。
- `outcome_unknown`/`reconciling`/`manual_review` 必须绑定 InvocationReconciliationCase；`abandoned` 与非幂等 `retry_scheduled` 必须同时绑定已解决 Case 和仅追加 InvocationManualReviewDecision。Validator 必须从聚合状态推导唯一 Decision/Outcome 组合，不能由调用方声明期望值；Decision 的 Case ID/版本/摘要、证据与 Outcome 必须匹配；Abandon 还必须满足 `risk_accepted=true`。
- Case/Decision/Aggregate 使用平台持久化时间，允许时钟偏差为 0：`opened_at <= resolved_at <= decision.occurred_at <= updated_at`，终态还必须满足 `decision.occurred_at <= completed_at`。Provider 自报时间只能作为证据，不参与该顺序。
- Invocation 与 Sandbox 的 `cancelled` 只能引用 `not_started` 或 `stopped_before_effect` 证据；已完成副作用不得记为取消成功。

## Sandbox

- `sandboxes(sandbox_id)` 主键；`(workspace_id, sandbox_slot_key)` 对非终态 Sandbox 唯一。
- `primary_sandbox_slot_key` 必须通过延迟约束/事务校验引用恰好一个 Workspace Sandbox。
- `sandbox_operations(operation_id)` 主键；`logical_operation_key` 唯一；只保存当前 Attempt 指针/编号聚合，不复制 Attempt 结果历史。
- `sandbox_operation_attempts(attempt_id)` 主键；`(operation_id, attempt_number)` 和 `(sandbox_id, fencing_token)` 唯一。
- Attempt 仅允许追加；Operation 的 `current_attempt_id` 只能引用自己的 Attempt；`current_attempt_number <= max_attempts` 必须有 CHECK/事务约束。
- `sandbox_reconciliation_cases(case_id)` 主键；每个未关闭 Operation 最多一个打开的 Case。
- `sandbox_manual_review_decisions(decision_id)` 主键、`decision_digest` 唯一且仅允许追加；必须引用 Case 和证据。
- `abandoned` Operation 必须引用已解决 Case 和 ManualReviewDecision；Decision 必须匹配 Case ID/版本/摘要/证据/结果，且 `decision=abandon` 必须同时满足 `risk_accepted=true`；未知副作用不得仅凭取消请求写入 `cancelled`。
- 稳定表禁止 Pod/Namespace/Container/VM/Node/原始 Endpoint 列；Adapter 私有表必须与稳定模型分 Schema/权限。

## Provider

- `provider_revisions(provider_revision_id)` 主键、`provider_revision_digest` 唯一；撤销 Update/Delete 权限，只允许 Insert。
- 每个 ProviderRevision（包括 Model/Tool/Skill/Renderer）都必须有 `conformance_set_digest`；每项结果绑定 Suite ID/Version/Digest/Profile 和 Evidence。CapabilityResolution 的 Definition 摘要、允许的 Provider Kind 和 Conformance 覆盖必须在准入时校验。
- ProviderRevision 的 Implementation、BuildProvenance、Port Binding、配置、权限和凭据均按摘要不可变；`agent_runtime`/`sandbox`/`capability` kind 只能绑定对应稳定 Port。
- BuildProvenance 的 Build Artifact Digest 必须等于 Implementation Distribution Digest；OCI 分发必须绑定 Image Digest。
- `provider_admission_decisions(decision_id)` 主键；`(provider_revision_id, decision_sequence)` 唯一且仅允许追加。
- Sequence 必须从 1 连续递增；`sequence=1` 不得有 Supersedes，`sequence>1` 必须引用同一 Revision 紧邻的上一 Decision；`revoked` 必须有 Reason。
- 新 Run 只能选择最新决策为 `certified` 的 Revision；RunManifest 保留 Revision/Decision 摘要，后续撤销不改写历史 Run。
- Agent Runtime Command `(runtime_run_id, command_sequence)`、`command_id` 唯一；Command 仅允许追加且 Fencing Token 严格递增。
- Agent Runtime Command 的 `command_digest` 必须与短期 RuntimeInvocation Token 的 `request_digest` 相等；Token 还必须匹配 Tenant、ProviderRevision、WorkflowRun/AgentRun/RuntimeRun、RunManifest、Attempt、Policy、Budget 和 Permissions。
- AgentRuntimeRun 生命周期必须遵循 `agent-runtime-run-v1`；`cancel_requested` 不是取消证明，`outcome_unknown` 必须经 Invocation Ledger 对账，终态必须有 `completed_at`。
- TemplateRevision ID/摘要唯一且不可变；SelectedExperience 必须引用已准入 Catalog Revision 和已认证 Template ProviderRevision，并满足 Scenario `required_tags` 与 CommercialAuthorizationSnapshot Entitlement。
- UiExtensionManifest Bundle/摘要/ProviderRevision 不可变；只允许受支持 Slot、不透明 Origin iframe 和已批准权限。

## Workflow、Policy、Event 与 Gateway

- OrchestrationBinding `binding_digest` 唯一且不可变；原生 Engine 执行引用只保存摘要，Endpoint、Namespace 和原生 Run ID 不进入稳定领域表。
- PolicyDecision 按 `(tenant_id, work_order_id, decision_id)` 唯一且仅追加；有效 Outcome 必须从所有匹配规则按 `deny > ask > allow` 推导，`ask` 必须绑定 Approval。
- CanonicalEvent `(aggregate_type, aggregate_id, aggregate_sequence)` 唯一；`event_id` 全局唯一。
- Outbox Row 与业务变更同事务；Inbox `(consumer, message_id)` 唯一。
- Canonical Aggregate 支持 Conversation、ConversationBranch、ConversationMessage、Sandbox、RuntimeSession 和 RuntimeRecording；EventPage 必须 `$ref` CanonicalEvent，禁止复制 Schema。
- CanonicalEvent 的 Work Context 是全有或全无绑定；仅属于 Conversation 的生命周期 Event 不得伪造 `work_order_id`/`work_sequence`。
- EventTypeRegistry 的 ID/Version/Digest 随 RunManifest 固化，`(type, data_version)` 唯一；核心 Projection 只消费 Registry 中 Schema Digest 已准入的 Payload。
- Runtime Gateway `(runtime_session_id, connection_generation, direction, channel, frame_sequence)` 唯一；重连 Cursor 按 Channel 唯一，Control ID + Digest 幂等，Recording Checkpoint 固化 recorded-through Sequence。旧 Generation、Sequence Gap、超出 ACK Window 和 Digest 冲突必须拒绝或显式对账。

## Technical Usage

- `meter_definitions(meter_id, meter_version)` 唯一且不可变，不包含 Price/Currency/Plan。
- `technical_usage(entry_id)` 主键；`(tenant_id, idempotency_key)` 唯一。Entry 必须绑定 WorkOrder、MeterDefinition 摘要/基础单位、Producer、Measurement Status 和 Evidence。
- Final UsageReport 只允许 Confirmed/Corrected Entry；Partial/Estimated 不得静默结算为 Confirmed 或零。
- Correction Entry 仅追加，引用同 Tenant/WorkOrder 的先前 Entry，Correction 链无环且不修改历史数量。
- UsageReport 与 BusinessSettlementEnvelope 在同一 Tenant/WorkOrder/Reservation 内连续编号并引用紧邻前驱。Settlement Envelope 嵌入完整 Final/Correction UsageReport，绑定同一 CommercialAuthorization 和 QuotaReservation；Platform Envelope 不含价格或余额变更。

## Artifact 与 Delivery

- `(artifact_id, version_number)` 唯一；ArtifactVersion 不可变。
- Staging/Finalization 使用预期摘要/大小；未 Finalize 不可交付。
- DeliveryAttempt `(delivery_id, attempt_number)` 唯一；回调只能引用预注册 Target，不接受任意 URL。
- `runtime_recordings(recording_id)` 主键；`(recording_id, channel, chunk_sequence)` 与 chunk_id 唯一。
- Recording Chunk 的不可变 ArtifactVersion 与摘要/大小一致；`chunk_count`、Channel Sequence、`work_sequence`/时间范围和 Manifest 摘要必须闭合。
- RuntimeRecording 生命周期必须遵循 `runtime-recording-v1`；`ready` 只能绑定完整 Manifest，`failed` 必须绑定结构化错误，`deleted` 保留不可逆 Tombstone。

## Redis 禁止事项

Redis 不得承载唯一状态、账本、游标真相或授权结论。清空 Redis 后系统必须能从 PostgreSQL、Temporal 和对象存储恢复正确性。
