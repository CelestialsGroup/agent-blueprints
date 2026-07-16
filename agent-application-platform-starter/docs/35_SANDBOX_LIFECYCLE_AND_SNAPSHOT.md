# Sandbox 生命周期、Lease 与 Snapshot

## 1. Sandbox 状态机

```text
requested -> provisioning -> ready
ready -> suspending -> suspended
suspended -> resuming -> ready
* -> terminating -> terminated
* -> expired
* -> failed
```

Sandbox 状态与 ExecOperation 状态分离。

## 2. ExecOperation

```text
accepted -> running
running -> completed | failed | outcome_unknown
running -> cancel_requested -> cancelled
```

Terminate 和 Exec 并发时：

- Terminate 提升 Sandbox generation。
- 未完成 Exec 收到取消。
- 旧 Fencing Token 的 Exec Result 被拒绝。
- 已发生但无法确认的外部副作用进入 Reconciliation。

## 3. Lease

每个 Sandbox 必须有明确 `lease_expires_at`。

Lease 到期流程：

1. 发送 `sandbox.expiring`。
2. 停止接受新 Exec/Session。
3. 取消活动操作。
4. 根据策略保存 Workspace Snapshot。
5. 终止 Backend。
6. 标记 expired/terminated。

Lease Extension：

- 幂等
- expected_generation
- 受 ExecutionBudget 和平台上限约束

## 4. Snapshot Level

### Workspace Snapshot

v1 必须支持或明确声明不支持。

包含：

- `/workspace`
- Path/Permission
- Content Digest
- Manifest
- Optional Git metadata

应尽量 Provider-neutral、可跨 Provider 恢复。

### Filesystem Snapshot

包含 Root Filesystem Delta 和 Workspace，通常绑定 Runtime Profile/Image。

### Process Snapshot

可选。

可能绑定：

- CPU Architecture
- Kernel
- Runtime version
- Image Digest
- Device/GPU
- Network state

必须声明 portable=false 或严格 Compatibility。

## 5. Restore

Restore 前校验：

- Capability
- Snapshot Digest
- ProviderRevision
- Runtime Profile
- Architecture
- Image
- Security Policy
- Tenant
- Data residency

不兼容返回：

```text
SANDBOX_RESTORE_INCOMPATIBLE
```

禁止悄悄降级为普通 Create，除非 Workflow 明确允许 Workspace-only fallback。
