# 数据模型与事务不变量

## 1. 目标

这些不变量必须先于数据库迁移冻结。应用层校验不能替代数据库唯一约束和事务约束。

## 2. Idempotency 与 Grant

### idempotency_records

唯一约束：

```text
UNIQUE(client_app_id, idempotency_key_digest)
```

同一唯一键只允许一个 request_digest。

### grant_consumptions

唯一约束：

```text
UNIQUE(issuer, grant_jti)
```

GrantConsumption、WorkOrder、IdempotencyRecord 和 Outbox 必须在同一事务提交。

## 3. WorkOrder 与 Workspace

```text
UNIQUE(work_order_id)
UNIQUE(workspace_id)
UNIQUE(work_order_id, workspace_id)
```

v1 中一个 WorkOrder 恰好对应一个 Workspace。

WorkOrder 创建后 tenant_id、client_app_id 和 principal_id 不可变。

## 4. Event

唯一约束：

```text
UNIQUE(work_order_id, work_sequence)
UNIQUE(aggregate_type, aggregate_id, aggregate_sequence)
UNIQUE(provider_instance_id, source_stream_id, source_cursor)
```

`next_work_sequence` 与 Event 插入在同一事务中更新。

事件表建议按 `recorded_at` 时间分区，并保留：

```text
INDEX(tenant_id, work_order_id, work_sequence)
INDEX(work_order_id, type, work_sequence)
INDEX(recorded_at)
```

## 5. Invocation

逻辑调用唯一约束：

```text
UNIQUE(workflow_run_id, workflow_step_id, logical_operation_key)
```

Attempt：

```text
UNIQUE(invocation_id, attempt_number)
UNIQUE(invocation_id, fencing_token)
```

Complete 只接受当前最高有效 fencing_token。

历史 Attempt 不得覆盖新 Attempt 的结果。

## 6. Artifact

```text
UNIQUE(artifact_id, version_number)
UNIQUE(artifact_id, content_digest)
UNIQUE(edit_session_id, idempotency_key_digest)
UNIQUE(conversion_source_version_id, target_media_type, profile, options_digest)
```

ArtifactVersion 内容不可修改。

删除通过生命周期记录或独立 Tombstone 表达。

## 7. Usage 与 Delivery

```text
UNIQUE(technical_usage_entry_id)
UNIQUE(delivery_id)
UNIQUE(callback_registration_id, delivery_id)
```

Usage 修正使用新 Entry，不更新历史记录。

## 8. Tenant Isolation

所有租户表必须包含 tenant_id。

推荐 PostgreSQL Row-Level Security 作为纵深防御：

- 应用连接设置内部 tenant context。
- 后台维护任务使用独立高权限角色。
- 任何绕过 RLS 的角色均需审计。

## 9. Transaction Isolation

- Grant 消费：`READ COMMITTED` + 唯一约束和行锁即可；不得采用先查后写的非原子流程。
- Event Sequence：原子 `UPDATE ... RETURNING`。
- Artifact Commit：锁定 Artifact current version 或使用 compare-and-swap。
- Provider Resolution：解析结果持久化为不可变 ProviderRevision 快照。

## 10. Sandbox

### sandbox_registry

```text
PRIMARY KEY(sandbox_id)
UNIQUE(work_order_id, workspace_id)
INDEX(tenant_id, observed_state)
INDEX(lease_expires_at, observed_state)
```

不可变：

- tenant_id
- work_order_id
- workspace_id
- provider_revision_id

### sandbox_operations

```text
UNIQUE(operation_id)
UNIQUE(sandbox_id, logical_operation_key)
UNIQUE(sandbox_id, fencing_token)
UNIQUE(operation_id, attempt_id)
```

Complete 只接受当前有效 fencing_token。

### sandbox_events

```text
UNIQUE(sandbox_id, sequence)
UNIQUE(provider_revision_id, source_stream_id, source_cursor)
```

Provider Event 进入 Agent Platform 后重新归一为 WorkOrder CanonicalEvent。

### sandbox_snapshots

```text
UNIQUE(snapshot_id)
UNIQUE(snapshot_digest)
INDEX(sandbox_id, created_at)
```

Process Snapshot 不能只通过 snapshot_id 推断可移植性，必须读取 Compatibility。

### Lease

Lease 扩展使用 expected_generation 或 CAS。

过期清理任务不能只依赖定时扫描，Provider Controller 和平台 Maintenance Workflow 都需要幂等补偿。
