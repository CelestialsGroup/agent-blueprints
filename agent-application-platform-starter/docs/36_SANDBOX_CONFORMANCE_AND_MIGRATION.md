# Sandbox Conformance 与迁移

## 1. Conformance Profile

ProviderRevision 必须通过其声明能力对应的测试 Profile。

基础：

- lifecycle
- exec
- security-restricted
- multi-node
- usage

可选：

- terminal
- browser
- snapshot-workspace
- snapshot-filesystem
- snapshot-process
- gpu

## 2. 必测故障

### 生命周期

- 重复 Create
- API/Controller 重启
- Provider 重启
- Node 故障
- Lease 到期
- Terminate 重试
- Orphan cleanup

### 并发

- Create/Terminate
- Exec/Terminate
- Snapshot/Write
- 多 Controller Reconcile
- 旧 Fencing Token
- generation conflict

### 安全

- 跨租户文件
- 跨租户网络
- 云元数据
- Kubernetes API
- Host filesystem
- privilege escalation
- Secret expiry/revoke
- Egress bypass

### Runtime Session

- Endpoint 不泄漏
- Session expiry
- Gateway reconnect
- Browser/Terminal permission
- Sandbox rebuild

### Usage

- Wall time
- CPU
- Memory
- Network
- Storage
- Exec count
- Evidence

## 3. DeerFlow 到 sandbox-runtime 迁移

### 阶段 A：契约抽象

```text
Agent Platform -> SandboxProvider Port
              -> DeerFlowSandboxAdapter
```

不改变现有运行行为。

### 阶段 B：影子验证

sandbox-runtime 创建同等 Spec 的测试 Sandbox，运行 Conformance 和非生产 Shadow Workload。

### 阶段 C：按场景 Canary

Capability/Provider Binding 将少量：

- coding
- browser
- standard

任务路由到 sandbox-runtime。

### 阶段 D：默认切换

Platform Default 改为 sandbox-runtime ProviderRevision。

现有 Run 继续锁定旧 Revision。

### 阶段 E：DeerFlow Built-in Draining

- 不接受新 Sandbox
- 等待旧 Run 结束
- 保留历史可读
- 禁用旧 ProviderRevision

## 4. 回滚

切换失败时：

- 新 WorkOrder Binding 回滚到 DeerFlow Provider。
- 已创建 sandbox-runtime Sandbox 按其 Revision 完成或取消。
- 禁止运行中直接把 Process Snapshot 恢复到不兼容 Provider。
- Workspace Snapshot 可在兼容声明通过后恢复到旧 Provider。

## 5. 禁止耦合

Agent Platform Contract 中禁止出现：

- deerflow_sandbox_type
- deerflow_workspace_path
- kubernetes_pod_name
- containerd_id
- firecracker_vm_id
- apple_container_id

这些只能存在于 Provider 私有 Metadata 或 Adapter 内部。
