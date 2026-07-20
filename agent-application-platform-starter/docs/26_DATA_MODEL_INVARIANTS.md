# 数据模型不变量 — v0.9.0

以下约束必须由 PostgreSQL Migration/Constraint 实现，不能只由应用代码约定。

## 身份与工作执行

- `(tenant_id, external_subject)` 唯一；所有业务表显式 tenant_id。
- `idempotency_records(tenant_id, client_app_id, operation_id, idempotency_key_digest)` 唯一；同范围不同 Request Digest 冲突。WorkOrder 创建不能使用范围更窄的替代索引。
- ExecutionGrant `jti` 单次消费，消费记录唯一；过期时间、Request/Idempotency 和 PrincipalContextSnapshot 摘要必须匹配。Turn Grant 必须绑定 Scenario/Turn/ClientMessage，Control Grant 必须禁止这些字段并绑定 WorkOrder/ControlRequest。
- `conversations(conversation_id)` 主键；`(tenant_id, client_app_id, client_conversation_key)` 唯一。
- `conversation_messages(message_id)` 主键；`(conversation_id, message_sequence)` 与 `(conversation_id, client_message_id)` 唯一；Message 仅允许追加。
- `conversation_branches(conversation_id, branch_id)` 主键；Head Message/Sequence 与 Fork Point 必须引用同一 Conversation 的先前 Message；Workspace Head 必须引用同 Branch 的不可变 WorkspaceRevision ID/Digest。Message、Workspace Head 和 Active Work 分别使用 `message_head_version`、`workspace_head_version`、`active_work_version` CAS；`branch_version` 只作投影 ETag。
- `workspace_revisions(workspace_revision_id)` 主键、`revision_digest` 唯一；`(workspace_id, branch_id, revision_number)` 唯一且从 1 连续；后续 Revision 引用同 Branch 紧邻前驱，Fork Revision 记录来源 Branch Revision，内容 Manifest ArtifactVersion 不可变并在准入时验证独立 WorkspaceContentManifest Schema。
- `parent_message_id` 只能引用同一 Conversation 中 Sequence 更小的 Message；每个 Branch 默认最多一个活动 WorkOrder，不能用 Conversation 顶层单值表达并行分支。
- Conversation Turn 事务原子完成 Message Sequence、WorkOrder、GrantConsumption、Workflow Start Outbox 和 CanonicalEvent。WorkOrderControl 事务验证客户端 `client_control_input_id` 后分配内部 `input_id/input_message_id`，只追加 ControlInput/GrantConsumption/Control Outbox，不创建新 Turn；Append/Interrupt 才比较 Message Head CAS，所有 Control 比较 Active Work CAS；`interrupt_and_enqueue` 通过取消意图与后继 WorkOrder 的明确关联闭合。
- WorkOrder、ExecutionGrant、RunManifest 和 CanonicalEvent 的 Conversation/Turn/Branch/Input Message 绑定必须一致；RunManifest `request_binding` 必须逐字段等于已消费 ExecutionGrant 的 Request Contract ID、Digest Profile 和 Digest。
- `workflow_runs(workflow_run_id)` 与 `work_orders(work_order_id)` 一对一；显式 `tenant_id` 必须一致，`root_agent_run_id` 唯一引用同一 WorkflowRun 的 Root；Temporal Continue-as-New 或未来编排器分段不能创建第二个平台 WorkflowRun。
- `agent_runs(agent_run_id)` 显式绑定 Tenant、WorkflowRun、RunManifest 和 `runtime_run_id`；每个 WorkOrder 恰好一个 Root AgentRun，Sub-agent 的 Parent/Root 必须属于同一 Tenant/WorkOrder/WorkflowRun。
- RunManifest 的 `agent_runtime.resolution_id` 必须引用恰好一个 Agent Runtime ProviderResolution，并与 AgentRun 的 `runtime_provider_resolution_id` 相同；每个 Sandbox Slot 同样只引用一个 Sandbox ProviderResolution；禁止复制第二份 Revision/Conformance 快照。
- RunManifest 固化 Input、ContextPackage、ArtifactAccessRequirement、初始 ExecutionBudget/PolicyDecision/EffectivePermissions 上限、CommercialAuthorizationBinding（ID/Digest/到期上限）、AuthorizationRenewalPolicy、带 Contract ID/Digest/Audience 的 Gateway Binding 和 Admission Limits。Runtime Start 的 Input/Context/Gateway 必须逐值相同；RuntimeAuthorization 按 `(runtime_run_id, authorization_sequence)` 连续仅追加并绑定前驱摘要、当前 Attempt 和 Manifest，只能等价/缩权。其 Budget/Policy/Permissions 必须绑定同一 Tenant/WorkOrder/CommercialAuthorization，Authorization 不得越过商业期限，fresh ArtifactGrant 必须恰好覆盖 Requirement 且 `authorization.issued_at <= grant.issued_at < grant.expires_at <= authorization.expires_at`。
- Conversation 生命周期必须遵循 `conversation-v1`；`archived`/`deleted` 写入相应审计时间，`deleted` 不可恢复。
- CommercialAuthorizationSnapshot ID/摘要/到期上限、显式 Entitlement/Capability/Limit 和 Quota Reservation 引用随 WorkOrder 固化；Limit 摘要必须闭合，Platform 无权更新 Business Entitlement/Balance。

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

- `sandboxes(sandbox_id)` 主键；`(work_order_id, sandbox_slot_key)` 对非终态 Sandbox 唯一，允许不同 Branch/WorkOrder 同时拥有 `primary-code`。
- RunManifest `sandboxes[]` 可为空；为空时 `primary_sandbox_slot_key` 必须不存在，非空时通过延迟约束/事务校验引用恰好一个 Sandbox Slot。
- 每个 Sandbox Spec 固化 Branch WorkspaceRevision ID/Digest；`cas_new_revision` 提交只能创建新 Revision，并以原 Branch Head/Version 为 CAS 前提。
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
- ProviderResolution 的 Decision Digest 必须绑定 Resolver Revision、Resolution Input Digest、逐候选 Audience/结论及 Evidence；恰好一个 Candidate 为 Selected，并与 Snapshot 的 Instance/Revision 及 selected audience 相同。
- ProviderResolution 行必须显式绑定 Tenant、ClientApplication 和 WorkOrder；`identity_dependency` 决定 PrincipalContextSnapshot Digest 是否必填，RLS 不得只依赖经 WorkOrder 间接推导的 Tenant。
- `provider_admission_decisions(decision_id)` 主键；`(provider_revision_id, decision_sequence)` 唯一且仅允许追加。
- Sequence 必须从 1 连续递增；`sequence=1` 不得有 Supersedes，`sequence>1` 必须引用同一 Revision 紧邻的上一 Decision；`revoked` 必须有 Reason。
- 新 Run 只能选择最新决策为 `certified` 的 Revision；RunManifest 保留 Revision/Decision 摘要，后续撤销不改写历史 Run。
- Agent Runtime Command `(runtime_run_id, command_sequence)`、`command_id` 唯一；Command 仅允许追加且 Fencing Token 严格递增。
- Agent Runtime Command 的 `command_digest` 必须与短期 RuntimeInvocation Token 的 `request_digest` 相等；Token 还必须匹配 Tenant、ProviderRevision、WorkflowRun/AgentRun/RuntimeRun、RunManifest、RuntimeAuthorization、Attempt、Policy、Budget 和 Permissions。
- CapabilityInvocationRequest 必须携带完整 ExecutionBudget/PolicyDecision/EffectivePermissions/CommercialAuthorizationBinding，并逐字段匹配 admitted ProviderResolution/Instance/Revision/Audience。Capability Token 按 `(invocation_attempt_id, authorization_sequence)` 连续，引用前驱 `jti`，分别绑定 Invoke/Status/Cancel/Event 操作摘要且不越过原 deadline/CommercialAuthorization；公共表和 Port 不要求 `plugin_id`。
- ArtifactGrant、ArtifactStagingGrant 分别具有内容摘要；Grant 与每个最长 300 秒的 Artifact Gateway Token 必须匹配 Tenant/WorkOrder/InvocationAttempt、Gateway Binding/Audience 和操作摘要。Staging Commit 不能写 ArtifactVersion Finalize 账本。
- Egress Token 必须匹配 RuntimeRun/InvocationAttempt/Fencing、registered destination、Gateway Binding、Request Digest、Policy/Budget/Permissions；请求不得携带原始 Origin，DNS/Redirect/IP 再验证属于 Execution Gateway Conformance 责任。
- AgentRuntimeRun 生命周期必须遵循 `agent-runtime-run-v1`；`cancel_requested` 不是取消证明，`outcome_unknown` 必须经 Invocation Ledger 对账，终态必须有 `completed_at`。
- TemplateRevision ID/摘要唯一且不可变；SelectedExperience 必须引用已准入 Catalog Revision 和已认证 Template ProviderRevision，并满足 Scenario `required_tags` 与 CommercialAuthorizationSnapshot Entitlement。
- UiExtensionManifest Bundle/摘要/ProviderRevision 不可变；只允许受支持 Slot、不透明 Origin iframe 和已批准权限。

## Workflow、Policy、Event 与 Gateway

- OrchestrationBinding `binding_digest` 唯一且不可变；原生 Engine 执行引用只保存摘要，Endpoint、Namespace 和原生 Run ID 不进入稳定领域表。
- PolicyDecision 按 `(tenant_id, work_order_id, decision_id)` 唯一且仅追加；有效 Outcome 必须从所有匹配规则按 `deny > ask > allow` 推导，`ask` 必须绑定 Approval。
- CanonicalEvent `(aggregate_type, aggregate_id, aggregate_sequence)` 唯一；`event_id` 全局唯一。
- Outbox Row 与业务变更同事务；传输 Inbox `(consumer, message_id)` 唯一；Canonical Event 来源 Inbox `(tenant_id, producer_id, source_stream_id, source_event_id)` 唯一并验证 Dedupe Key。
- Canonical Aggregate 支持 Conversation、ConversationBranch、ConversationMessage、WorkspaceRevision、Sandbox、RuntimeSession 和 RuntimeRecording；EventPage 必须 `$ref` CanonicalEvent，禁止复制 Schema。
- CanonicalEvent 的 Work Context 是全有或全无绑定；仅属于 Conversation 的生命周期 Event 不得伪造 `work_order_id`/`work_sequence`。
- CanonicalEvent Metadata 闭合；Provider 来源必须绑定不可变 ProviderRevision，Provider 私有 Trace/Metadata 只保存为 Evidence 引用。
- EventTypeRegistry 的 ID/Version/Digest 随 RunManifest 固化，`(type, data_version)` 唯一；核心 Projection 只消费 Registry 中 Schema Digest 已准入的 Payload。
- Platform Core Registry 必须覆盖 Conversation/Message、WorkOrder/Control、WorkflowRun/AgentRun、Grant、Approval、Invocation、Artifact、Usage、Workspace、RuntimeSession/Recording 和 Delivery；Runtime Provider Event Registry 不得代替平台领域事件。
- Runtime Gateway `(runtime_session_id, connection_generation, direction, channel, frame_sequence)` 唯一；重连 Cursor 按 Channel 唯一，Control ID + Digest 幂等，Recording Checkpoint 固化 recorded-through Sequence。旧 Generation、Sequence Gap、超出 ACK Window 和 Digest 冲突必须拒绝或显式对账。

## Technical Usage

- `meter_definitions(meter_id, meter_version)` 唯一且不可变，不包含 Price/Currency/Plan。
- `technical_usage(entry_id)` 主键；`(tenant_id, idempotency_key)` 唯一。Entry 必须绑定 WorkOrder、MeterDefinition 摘要/基础单位、Producer、Measurement Status 和 Evidence。
- Provider 只提交按 ProviderRevision + InvocationAttempt + observation_id 幂等的 UsageObservation；Platform 验证后分配 TechnicalUsage `entry_id`、归属、Idempotency Key 和 `recorded_at`，ProviderReported Entry 必须引用源 Observation。
- Final UsageReport 只允许 Confirmed/Corrected Entry；Partial/Estimated 不得静默结算为 Confirmed 或零。
- Correction Entry 仅追加，引用同 Tenant/WorkOrder 的先前 Entry，Correction 链无环且不修改历史数量。
- UsageReport 与 BusinessSettlementEnvelope 在同一 Tenant/WorkOrder/Reservation 内连续编号并引用紧邻前驱。Settlement Envelope 嵌入完整 Final/Correction UsageReport，绑定同一 CommercialAuthorization 和 QuotaReservation；Platform Envelope 不含价格或余额变更。

## Artifact 与 Delivery

- `(artifact_id, version_number)` 唯一；ArtifactVersion 不可变。
- Staging/Finalization 使用预期摘要/大小；未 Finalize 不可交付。
- Provider Grant/EffectivePermissions 只允许 `read` 或 `stage_new_version`；Finalize 是 Platform 内部事务，Provider 结果只能引用 StagedArtifact。
- DeliveryAttempt `(delivery_id, attempt_number)` 唯一；回调只能引用预注册 Target，不接受任意 URL。
- `runtime_recordings(recording_id)` 主键；`(recording_id, channel, chunk_sequence)` 与 chunk_id 唯一。
- Recording Chunk 的不可变 ArtifactVersion 与摘要/大小一致；`chunk_count`、Channel Sequence、`work_sequence`/时间范围和 Manifest 摘要必须闭合。
- Recording Chunk 必须绑定 Redaction Profile/Evidence Digest；未脱敏 Frame 不得创建 ArtifactVersion 或进入任何持久介质。
- RuntimeRecording 生命周期必须遵循 `runtime-recording-v1`；`ready` 只能绑定完整 Manifest，`failed` 必须绑定结构化错误，`deleted` 保留不可逆 Tombstone。

## Redis 禁止事项

Redis 不得承载唯一状态、账本、游标真相或授权结论。清空 Redis 后系统必须能从 PostgreSQL、Temporal 和对象存储恢复正确性。
