# 数据模型不变量

以下约束必须由 PostgreSQL Migration/Constraint 实现，不能只由应用代码约定。

## 身份与工作执行

- `(tenant_id, external_subject)` 唯一；所有业务表显式 tenant_id。
- `idempotency_records(tenant_id, client_app_id, operation_id, idempotency_key_digest)` 唯一；同范围不同 Request Digest 冲突。WorkOrder 创建不能使用范围更窄的替代索引。
- ExecutionGrant `jti` 单次消费，消费记录唯一；过期时间、Request/Idempotency 和 PrincipalContextSnapshot 摘要必须匹配。Turn Grant 必须绑定 Scenario/Turn/ClientMessage，Control Grant 必须禁止这些字段并绑定 WorkOrder/ControlRequest。
- `conversations(conversation_id)` 主键；`(tenant_id, client_app_id, client_conversation_key)` 唯一。
- `conversation_messages(message_id)` 主键；`(conversation_id, message_sequence)` 与 `(conversation_id, client_message_id)` 唯一；Message 仅允许追加。
- `conversation_branches(conversation_id, branch_id)` 主键；Head Message/Sequence 与 Fork Point 必须引用同一 Conversation 的先前 Message；Workspace Head 必须引用同 Branch 的不可变 WorkspaceRevision ID/Digest。Message、Workspace Head 和 Active Work 分别使用 `message_head_version`、`workspace_head_version`、`active_work_version` CAS；`branch_version` 只作投影 ETag。
- ConversationBranch Create/Fork 以 Tenant-derived ClientApplication + Conversation + `branch-create` + Idempotency Key Digest 唯一；相同 Key 不同 Request Digest 返回冲突。Fork 必须同时验证来源 Branch 的 Message Cut、`source_message_head_version`、WorkspaceRevision ID/Digest 与 `source_workspace_head_version`，再原子插入新 Branch、初始 Heads 和 `conversation.branch.created|forked` Outbox Event。
- `workspace_revisions(workspace_revision_id)` 主键、`revision_digest` 唯一；`(workspace_id, branch_id, revision_number)` 唯一且从 1 连续；后续 Revision 引用同 Branch 紧邻前驱，Fork Revision 记录来源 Branch Revision，内容 Manifest ArtifactVersion 不可变并在准入时验证独立 WorkspaceContentManifest Schema。
- `parent_message_id` 只能引用同一 Conversation 中 Sequence 更小的 Message；每个 Branch 默认最多一个活动 WorkOrder，不能用 Conversation 顶层单值表达并行分支。
- Conversation Turn 事务原子完成 Message Sequence、WorkOrder、GrantConsumption、Workflow Start Outbox 和 CanonicalEvent。WorkOrderControl 事务验证客户端 `client_control_input_id` 后分配内部 `input_id/input_message_id`，只追加 ControlInput/GrantConsumption/Control Outbox，不创建新 Turn；Append/Interrupt 才比较 Message Head CAS，所有 Control 比较 Active Work CAS；`interrupt_and_enqueue` 通过取消意图与后继 WorkOrder 的明确关联闭合。
- WorkOrder、ExecutionGrant、RunManifest 和 CanonicalEvent 的 Conversation/Turn/Branch/Input Message 绑定必须一致；RunManifest `request_binding` 必须逐字段等于已消费 ExecutionGrant 的 Request Contract ID、Digest Profile 和 Digest。
- `workflow_runs(workflow_run_id)` 与 `work_orders(work_order_id)` 是唯一可空一对一：只有 Orchestration Start 确认后才创建，启动前取消/失败可以没有；Temporal Continue-as-New 或未来编排器分段不能创建第二个平台 WorkflowRun。
- `workflow_run_root_bindings(workflow_run_id)` 单次赋值且唯一；Root Admission 成功时与 Root AgentRun、RunManifest、AgentRunBudgetAllocation 和 Runtime Start Outbox 同事务创建，循环外键使用 `DEFERRABLE INITIALLY DEFERRED` 并在 Commit 验证。Root Admission 失败的 WorkflowRun 没有 RootBinding，禁止伪造 ProviderResolution、RunManifest、RuntimeRun 或 Sandbox。
- `agent_runs(agent_run_id)` 显式绑定 Tenant、WorkflowRun、RunManifest、`runtime_run_id`、RunKind、Root、Depth 和 required-completion；RootBinding 存在时每个 WorkflowRun 恰好一个 Root。Sub-agent 的 Parent/Root 必须属于同一 Tenant/WorkOrder/WorkflowRun，Depth 等于 Parent + 1，`spawn_request_id` 唯一引用 Accepted Child Admission。
- ChildAgentRunSpawnRequest 按 `(work_order_id, spawn_request_id)` 唯一，ID + Digest 重放幂等、Digest 冲突拒绝。Platform 锁定 WorkOrder 与共享 Budget Ledger 后检查活动状态、授权、深度、总数、并发、Policy、ProviderResolution、Workspace 与 Sandbox；Accepted Decision 与 Child AgentRun/Manifest/Allocation/AgentRunWorkspaceBinding/Outbox/Event 同事务，Rejected Decision 不创建任何执行资源。WorkspaceBinding 必须逐值绑定 Parent Base Revision 与请求模式：只读模式无写权限/Commit，隔离模式产生独立 Revision 后 Merge CAS，共享模式逐 Commit 执行 Branch Workspace Head CAS；模式不能静默降级。
- ExecutionBudget 是 WorkOrder 唯一共享硬上限；`agent_run_budget_allocations` 只包含八类可消耗资源的更窄单 Run 限制，不得复制 `max_agent_runs`、`max_agent_depth` 或 `max_parallel_agent_runs`。所有 Runtime Admission、Model/Tool/Artifact/Egress Gateway、Sandbox Lease 和 Usage 导入以 `budget_id` 原子预留/扣减，不能把相同 Budget 复制成每个 Child 可分别耗尽的额度。三个拓扑上限只从 WorkOrder ExecutionBudget 读取并在 Spawn Admission 中事务执行。
- `agent_run_control_fanouts` 的 Authority ID/Digest/Action/Tenant/WorkOrder 必须外键或事务绑定同一不可变 WorkOrderControlRequest 或系统安全触发事实；用户控制目标禁止出现 SystemSafetyControl，系统 fan-out 的每个 RuntimeRun 必须有独立 SystemSafetyControl。目标集合在禁止新 Child Admission 后事务锁定全部活动 AgentRun，遗漏、重复或跨 WorkOrder 目标均拒绝。进度按 `(fanout_id, fanout_version)` 连续仅追加，前驱摘要、Authority、目标、Fencing 和创建时间不可变，ControlState 只能单调推进且 `updated_at` 严格递增。
- RunManifest 的 `agent_runtime.resolution_id` 必须引用恰好一个 Agent Runtime ProviderResolution，并与 AgentRun 的 `runtime_provider_resolution_id` 相同；每个 Sandbox Slot 同样只引用一个 Sandbox ProviderResolution；禁止复制第二份 Revision/Conformance 快照。
- RunManifest `location` 是内容绑定的逻辑 Placement 决策，只允许 Mode、可空 Region、Policy Reference 和 Decision Digest；Cluster、Cell、Pod、Node、Runtime ID 与 Endpoint 属于 Provider/Orchestration Adapter 私有拓扑。`provider_managed`/`external` 可以没有 Region，不能为满足 Schema 伪造本地位置。
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
- ProviderResolution 行必须显式绑定 Tenant、ClientApplication 和闭合 `execution_scope`；当前允许 WorkOrder 或 ArtifactOperation，且所有外键必须指向该 Scope 的同一所有者。`identity_dependency` 决定 PrincipalContextSnapshot Digest 是否必填，RLS 不得只依赖经上层聚合间接推导的 Tenant。
- `provider_admission_decisions(decision_id)` 主键；`(provider_revision_id, decision_sequence)` 唯一且仅允许追加。
- Sequence 必须从 1 连续递增；`sequence=1` 不得有 Supersedes，`sequence>1` 必须引用同一 Revision 紧邻的上一 Decision；`revoked` 必须有 Reason。
- 新 Run 只能选择最新决策为 `certified` 的 Revision；RunManifest 保留 Revision/Decision 摘要，后续撤销不改写历史 Run。
- Agent Runtime Command `(runtime_run_id, command_sequence)`、`command_id` 唯一；Command 仅允许追加且 Fencing Token 严格递增，`deadline_at` 必须晚于签发 Token 且 Token 不得越过该 Deadline。
- `runtime_command_append_only_idempotency`：Runtime Command 以 `(runtime_run_id, command_sequence)` 与 `command_id` 唯一；同一 `command_id + command_digest` 重放幂等，摘要冲突 fail-closed，任何已持久化 Command 不得更新或删除。
- `runtime_command_user_control_fk`：携带 `authorized_control_request_id` 的 Command 必须外键绑定同 WorkOrder 的已授权 ControlRequest，action 相同；Append/Interrupt 还必须绑定已原子持久化的 `input_id + content_digest`。
- `system_safety_control_append_only_idempotency`：`system_safety_controls(safety_control_id)` 主键，`control_digest` 唯一且内容不可变；相同 ID + Digest 重放幂等，冲突拒绝。创建控制事实、`work_order.safety_control.issued` 与 Control Outbox 必须同事务。
- `system_safety_control_trigger_evidence_fk`：每个 SystemSafetyControl 的 `(evidence_contract_id, evidence_id, evidence_digest)` 必须解析到已持久接纳且摘要匹配的不可变 Platform/Business 证据；`observed_at <= issued_at`。原因与证据类型必须匹配，任意字符串、日志文本或 Provider 自报不能成为停止权限。
- `commercial_authorization_revocation_fanout`：`commercial_authorization_revocation_receipts(revocation_id)` 仅追加并保存 Receipt/Revocation Digest、认证 ClientApplication、解析后的 Tenant、CommercialAuthorization ID/Digest、同步 deny 生效时间和 Inbox 键；相同 ID + Digest 重放幂等，冲突拒绝。收据在同一事务枚举唯一 WorkSession intents 与全部活动 WorkOrder、ArtifactOperation、ArtifactIngest `ExecutionScope` targets，每项保存 Owner State CAS、reduction-only Cancel intent 和 Outbox ID。WorkOrder target 禁止新 Child Admission并创建 AgentRunControlFanout，对每个活动 RuntimeRun 分配新 Fencing/SystemSafetyControl；ArtifactOperation/Ingest 按各自状态机进入可恢复取消/拒绝终态。部分失败从收据重放到 `completed/already_terminal`，不能依赖一次内存遍历或把 `in_progress` 当撤销完成。
- `runtime_command_system_safety_fk`：Pause/Cancel Command 在用户 ControlRequest 与 `system_safety_control_id + system_safety_control_digest` 间恰好选择一个来源。系统来源外键绑定由唯一 Platform Safety Controller 签发、且同 Tenant/WorkOrder/RuntimeRun/action 的不可变记录；Resume、Append、Interrupt、Approval、Checkpoint 禁止引用该表。
- Agent Runtime Command 必须显式携带逻辑 `invocation_id`；其 `command_digest` 必须与短期 RuntimeInvocation Token 的 `operation_request_digest` 相等。Token 还必须匹配当前 Operation Contract/Profile、Tenant、ProviderRevision、WorkflowRun/AgentRun/RuntimeRun、RunManifest、RuntimeAuthorization、Attempt、Policy、Budget 和 Permissions；Status/Event Path 与 Cursor 使用正式读描述符摘要。`safety_control` 可以越过执行授权期限，但只能读取或 Cancel/Pause，不能继续执行。系统安全 Command 的 Token 还必须绑定相同 SystemSafetyControl ID/Digest，且 `nbf >= issued_at`。
- CapabilityInvocationRequest 必须携带完整 ExecutionBudget/PolicyDecision/EffectivePermissions/CommercialAuthorizationBinding，并逐字段匹配 admitted ProviderResolution/Instance/Revision/Audience。Capability Token 按 `(invocation_attempt_id, authorization_sequence)` 连续，引用前驱 `jti`，分别绑定 Invoke/Status/Cancel/Event 操作摘要；`execution` 不越过原 deadline/CommercialAuthorization，后续 `safety_control` 只允许 Status/Cancel/Event 且不能使用过期 Artifact Grant 或产生新副作用。公共表和 Port 不要求 `plugin_id`。
- ArtifactGrant、ArtifactStagingGrant 分别具有内容摘要；Grant 与每个最长 300 秒的 Artifact Gateway Token 必须匹配 Tenant/WorkOrder/InvocationAttempt、Gateway Binding/Audience 和操作摘要。Staging Commit 不能写 ArtifactVersion Finalize 账本。
- `egress_destination_revision_immutable`：EgressDestinationRevision 以 `destination_revision_id + destination_revision_digest` 仅追加，Owner 为 Platform/Tenant/ClientApplication 之一；同一 Revision 的 Origin、Class、Method/Path/Header、Redirect 或 DNS Policy 不得原地修改。
- `work_session_revocation_version`：WorkSession 的 `(tenant_id, session_id, session_version)` 与 `revoked_at` 是 Platform 权威状态；Cookie/Bearer Claims 的版本必须等于当前版本，商业授权失效、权限变化或显式撤销后旧连接和请求均 fail-closed。
- Egress Token 必须匹配 `http_exchange` Operation、Request Contract/Profile、Tenant/ClientApplication、RuntimeRun/InvocationAttempt/Fencing、registered DestinationRevision ID/Digest/Class、Gateway Binding、RuntimeAuthorization、Request Digest、Policy/Budget/Permissions；EffectivePermissions 比较 `destination_class`，请求不得携带原始 Origin，DNS/Redirect/IP 再验证属于 Execution Gateway Conformance 责任。
- RuntimeSessionRoute 只持久化 `gateway_route_id + provider_route_reference + provider_route_digest`；原始 Endpoint、Pod/VM、Cluster、Region 或 Cell 只能存在于 Gateway/Provider 私有存储，不能进入稳定内核表或用户 API。
- CompatibilityEvidence 和 CompatibilityDecision 只允许 Platform 插入且不可更新；Decision 的 Subject Digest、Source/Target ProviderRevision 与 Runtime Revision、Profile、Suite ID/Version/Digest 和全部 Evidence 必须闭合。Restore Dispatch 只能引用 `compatible` Decision；缺失、失败、过期或任何字段不匹配均在 Provider 调用前拒绝。
- SecretGrant 与 SecretGrantRevocation 仅追加。Grant 的 Tenant、Principal、ExecutionScope、ProviderRevision、Workload Identity、用途、Target 和 pre-grant Operation Intent Digest 必须与目标执行一致；单次消费与 Audit Identity 在材料交付前原子提交。Revocation/Expiration/Consumed 状态由同步 deny 索引检查，明文或 Delivery Handle 不得写入 PostgreSQL、Redis、Temporal、Queue、Event、Trace、Recording 或 Artifact。
- AgentRuntimeRun 生命周期必须遵循 `agent-runtime-run-v1`；`cancel_requested` 不是取消证明，`outcome_unknown` 必须经 Invocation Ledger 对账，终态必须有 `completed_at`。
- AgentRun 状态投影由已准入 Runtime Event 或对账证据更新。Root `succeeded` 只表示 Root Runtime 结束，不自动完成 WorkOrder；`completed` 要求 Root succeeded、所有 `required_for_work_order_completion=true` 的 Child succeeded，且不存在任何活动 Child。Required Child 失败按 Scenario 规则进入 `failed` 或有可用结果时进入 `partial`；`cancelled` 要求每个活动 Run 都有取消/未启动证明；`paused` 要求全部活动 Run 已确认暂停。终态 WorkOrder 下发现非终态 Child 必须进入孤儿对账并提高 Fencing，不能静默遗留。
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
- Agent Runtime EventTypeRegistry 的 ID/Version/Digest 随 RunManifest 固化，Platform Event 使用独立 Platform Core Registry；CanonicalEvent 的 Registry 外键、Digest 与 Producer 所有权必须一致，`(type, data_version)` 唯一，核心 Projection 只消费对应 Registry 中 Schema Digest 已准入的 Payload。
- Platform Core Registry 必须覆盖 Conversation/Message、WorkOrder/Control/SystemSafetyControl、WorkflowRun/AgentRun、Grant、Approval、Invocation、Artifact、Usage、Workspace、RuntimeSession/Recording 和 Delivery；Runtime Provider Event Registry 不得代替平台领域事件。
- Runtime Gateway `(runtime_session_id, connection_generation, direction, channel, frame_sequence)` 唯一；重连 Cursor 按 Channel 唯一，Control ID + Digest 幂等，Recording Checkpoint 固化 recorded-through Sequence。旧 Generation、Sequence Gap、超出 ACK Window 和 Digest 冲突必须拒绝或显式对账。

## Technical Usage

- `meter_definitions(meter_id, meter_version)` 唯一且不可变，不包含 Price/Currency/Plan。
- `technical_usage(entry_id)` 主键；`(tenant_id, idempotency_key)` 唯一。Entry 必须绑定 WorkOrder、MeterDefinition 摘要/基础单位、Producer、Measurement Status 和 Evidence。
- Provider 只提交按 ProviderRevision + InvocationAttempt + observation_id 幂等的 UsageObservation；Platform 验证后分配 TechnicalUsage `entry_id`、归属、Idempotency Key 和 `recorded_at`，ProviderReported Entry 必须引用源 Observation。
- Final UsageReport 只允许 Confirmed/Corrected Entry；Partial/Estimated 不得静默结算为 Confirmed 或零。
- Correction Entry 仅追加，引用同 Tenant/WorkOrder 的先前 Entry，Correction 链无环且不修改历史数量。
- UsageReport 与 BusinessSettlementEnvelope 在同一 Tenant/ExecutionScope/Reservation 内连续编号并引用紧邻前驱。WorkOrder 与 ArtifactOperation 用量都进入同一 TechnicalUsage/Report/Settlement 模型；Settlement Envelope 嵌入完整 Final/Correction UsageReport，绑定同一 CommercialAuthorization 和 QuotaReservation，且不含价格或余额变更。

## Artifact 与 Delivery

- `(artifact_id, version_number)` 唯一；ArtifactVersion 不可变。
- Staging/Finalization 使用预期摘要/大小；未 Finalize 不可交付。
- Provider Grant/EffectivePermissions 只允许 `read` 或 `stage_new_version`；Finalize 是 Platform 内部事务，Provider 结果只能引用 StagedArtifact。
- ArtifactOperation 以 `(tenant_id, client_app_id, operation_kind, idempotency_key_digest)` 唯一并保存 Request Digest。公开请求不得携带 Platform 分配的 Operation ID、Policy/Budget/Permissions/Gateway/Provider 事实；事务先认证调用方输入并分配 Operation，再生成并以外键/摘要绑定这些 admission facts。状态版本连续遵循 `artifact-operation-v1`。ProviderResolution 与唯一 Invocation 必须使用同一 `artifact_operation` ExecutionScope、ProviderRevision 和 Request Digest；Preview/Edit/Conversion Projection 不得拥有 Dispatch/Retry/Terminal Truth。每个活动态取消都以 Expected Owner State CAS 原子保存 `cancel_requested`、不可变来源 ID/Digest、`cancellation_intent_id`、Outbox ID 和核心事件；已派发取消绑定唯一 Invocation 及其取消状态，未知结果绑定同一 Invocation ReconciliationCase，且取消对账不得重新派发执行。Operation 的已派发 `cancelled` 只能投影已提交或已对账的 Invocation `cancelled` 事实。
- ArtifactIngestSession 以 `(tenant_id, client_app_id, artifact-ingest, idempotency_key_digest)` 唯一并保存 Request Digest。Create 请求不得携带 Policy/Budget/Permissions；Session 分配后由 Platform 生成同 Scope 的 PolicyDecision、ExecutionBudget、EffectivePermissions 并保存 ID/Digest。确认上传以 Session + Confirmation Digest 幂等，状态版本连续遵循 `artifact-ingest-v1`。只有绑定精确字节摘要的通过态 ScanResult 才能进入 `ready_to_finalize`，且只有 Platform Artifact Ledger 事务可原子创建一个 ArtifactVersion、推进 `finalized` 并写 Outbox。
- DeliveryAttempt `(delivery_id, attempt_number)` 唯一；回调只能引用预注册 Target，不接受任意 URL。
- WorkOrder 终态不等于用量已确认。DeliveryPackage 与 Settlement 在非空 Final/Correction UsageReport 和 NoUsageAttestation 之间恰好选择一个；缺失用量、Partial/Estimated 或未知测量保持待对账，绝不能推导为零。NoUsageAttestation 仅允许在没有任何 Runtime/Capability/Sandbox/Gateway Attempt 且没有 TechnicalUsageEntry 的可证明启动前失败、取消或准入拒绝中创建，并仅追加保存证据摘要。
- `runtime_recordings(recording_id)` 主键；`(recording_id, channel, chunk_sequence)` 与 chunk_id 唯一。
- Recording Chunk 的不可变 ArtifactVersion 与摘要/大小一致；`chunk_count`、Channel Sequence、`work_sequence`/时间范围和 Manifest 摘要必须闭合。
- Recording Chunk 必须绑定 Redaction Profile/Evidence Digest；未脱敏 Frame 不得创建 ArtifactVersion 或进入任何持久介质。
- RuntimeRecording 生命周期必须遵循 `runtime-recording-v1`；`ready` 只能绑定完整 Manifest，`failed` 必须绑定结构化错误，`deleted` 保留不可逆 Tombstone。

## Phase 0 DDL 责任索引

以下 ID 是 Contract 的 `contracts/semantic-constraints-v1.json` 通过稳定 Blueprint URN 引用的目标。0B Migration、Constraint 与集成证据必须使用这些精确 ID；本文件存在该 ID 只表示责任已分配，不表示实现已完成或通过。

| Check ID | 必须由实现证明的责任 |
|---|---|
| `workflow_run_optional_unique_binding` | WorkOrder 到可空 WorkflowRun 的唯一绑定 |
| `workflow_root_binding_unique_fk` | WorkflowRun 只存在一个 RootBinding |
| `workflow_root_binding_deferred_atomic_insert` | RootBinding 循环外键延迟到事务提交校验 |
| `workflow_root_binding_authority` | Root Agent 身份只由 RootBinding 决定 |
| `agent_run_parent_root_depth_fk` | Child Parent/Root/Depth 同一执行树 |
| `agent_run_spawn_admission_unique_fk` | Child AgentRun 唯一引用 Accepted Admission |
| `work_order_shared_budget_ledger` | 全部 AgentRun 共用一个 WorkOrder 预算账本 |
| `child_admission_topology_limits` | 深度、数量和并发在准入事务内硬限制 |
| `child_spawn_idempotency_unique` | Spawn ID/Digest 重放幂等且冲突拒绝 |
| `child_admission_single_decision` | 每个 Spawn 只有一个不可变准入结论 |
| `child_admission_atomic_insert` | Accepted 资源与 Outbox/Event 原子创建 |
| `child_admission_active_authorization_guard` | 活动状态与授权在 Child 准入锁内复核 |
| `agent_run_control_fanout_authority_fk` | Fanout 绑定唯一用户或系统控制事实 |
| `agent_run_control_fanout_target_snapshot` | 活动子树目标和 Fencing 事务快照闭合 |
| `idempotency_scope_unique_index` | Tenant/Client/Operation/Key Digest 唯一 |
| `idempotency_digest_conflict` | 同 Key 不同 Request Digest 冲突 |
| `work_order_control_input_allocation_and_outbox` | 用户 Control、Grant 消费、输入分配与 Outbox 原子 |
| `message_workspace_active_work_split_cas` | Message、Workspace 与 Active Work 独立 CAS |
| `branch_etag_not_write_cas` | Branch ETag 不可充当写入 CAS |
| `branch_fork_prior_message_fk` | Fork Message Cut 只引用来源 Branch 已存在消息 |
| `branch_workspace_revision_fk` | Fork Workspace Head 绑定精确不可变 Revision |
| `branch_one_active_work_order` | 每个 Branch 默认最多一个活动 WorkOrder |
| `conversation_branch_create_idempotency` | Branch Create/Fork ID 与摘要幂等 |
| `conversation_branch_create_atomic_outbox` | Branch、Heads 与核心 Event Outbox 原子 |
| `workspace_revision_contiguous` | Workspace Revision Number 从 1 连续 |
| `workspace_revision_immediate_predecessor` | 后续 Revision 引用紧邻前驱 |
| `workspace_revision_fork_origin` | Fork Revision 记录精确来源 Revision |
| `provider_revision_immutable` | ProviderRevision 摘要唯一且禁止更新删除 |
| `provider_resolution_complete_input_evidence` | Resolver Input/Candidate/Evidence 完整持久化 |
| `provider_resolution_immutable_evidence_lookup` | Resolution Evidence 引用可解析且摘要匹配 |
| `tenant_client_work_order_provider_resolution` | 历史稳定 ID；实际约束为 Tenant/Client/ExecutionScope 所有权闭合 |
| `runtime_command_append_only_idempotency` | Runtime Command 序列仅追加且摘要重放幂等 |
| `runtime_command_user_control_fk` | 用户 Command 只引用同 Scope 已授权 ControlRequest |
| `runtime_command_system_safety_fk` | 安全 Command 只引用同 Scope Reduction-only 事实 |
| `runtime_command_child_admission_fk` | Child 决策 Command 绑定同树 Admission |
| `system_safety_control_append_only_idempotency` | SafetyControl 仅追加且 ID/Digest 幂等 |
| `system_safety_control_trigger_evidence_fk` | SafetyControl 触发证据真实可解析 |
| `commercial_authorization_revocation_fanout` | 商业撤销同步拒绝新授权并可恢复 Fanout |
| `work_session_revocation_version` | Session Version 撤销后旧连接 fail-closed |
| `secret_grant_revocation_synchronous_deny` | SecretGrant 撤销在材料释放前同步生效 |
| `egress_destination_revision_immutable` | Egress DestinationRevision 仅追加不可变 |
| `aggregate_and_work_sequence_ledgers` | Aggregate/Work 序列分别连续唯一 |
| `canonical_event_inbox_source_uniqueness` | Provider Source Identity Inbox 唯一 |
| `conversation_event_omits_work_scope` | Conversation-only Event 禁止伪造 Work Scope |
| `work_order_sequence_and_outbox` | WorkOrder 状态、序列和 Event Outbox 原子 |
| `technical_usage_identity_uniqueness` | Usage Entry 与 Tenant Idempotency 唯一 |
| `technical_usage_correction_chain` | Correction 同 Scope、无环、仅追加 |
| `technical_usage_multi_agent_attribution` | Usage 精确归属 AgentRun/Attempt/Provider |
| `usage_report_sequence_and_predecessor` | UsageReport Reservation 内连续前驱链 |
| `usage_report_append_only_correction` | Final/Correction Report 只追加 |
| `settlement_envelope_sequence` | Settlement Envelope Reservation 内连续前驱链 |
| `work_order_terminal_usage_accounting` | 终态 WorkOrder 必须进入明确用量对账状态 |
| `no_usage_absence_proof` | NoUsage 前证明不存在任何 Dispatch 与 Usage |
| `no_usage_attestation_append_only` | NoUsageAttestation 内容寻址且仅追加 |
| `delivery_usage_accounting_required` | Delivery 必须绑定 Report 或 Attestation，不把缺失当零 |
| `artifact_operation_idempotency_scope` | ArtifactOperation Tenant/Client/Kind/Key 唯一 |
| `artifact_operation_state_and_terminal_evidence` | Operation 状态连续且终态证据不可变 |
| `artifact_operation_cancellation_outbox` | 撤销收据/内部触发器先持久化唯一 Intent 与派发 Outbox；消费者以 Owner CAS 原子提交 `cancel_requested`、来源绑定、核心事件和状态 Outbox，重放只消费同一 Intent |
| `artifact_ingest_idempotency_scope` | Ingest Tenant/Client/Operation/Key 唯一 |
| `artifact_ingest_digest_idempotency` | 上传确认 ID/Digest 重放幂等 |
| `artifact_ingest_state_version` | Ingest 状态版本连续并遵循状态机 |
| `artifact_ingest_platform_finalize_transaction` | ArtifactVersion Finalize 只由 Platform 原子提交 |
| `compatibility_decision_platform_ownership` | CompatibilityDecision 只由 Platform 仅追加拥有 |

## Redis 禁止事项

Redis 不得承载唯一状态、账本、游标真相或授权结论。清空 Redis 后系统必须能从 PostgreSQL、Temporal 和对象存储恢复正确性。
