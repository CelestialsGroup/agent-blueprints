# Sandbox 安全与隔离规范

## 1. 默认拒绝

默认 Sandbox：

```text
privileged = false
hostNetwork = false
hostPID = false
hostIPC = false
hostPath = forbidden
allowPrivilegeEscalation = false
serviceAccountToken = disabled
capabilities = drop ALL
runAsNonRoot = true
seccomp = RuntimeDefault
```

根文件系统默认只读；需要写入时仅允许可写 Overlay。

## 2. 隔离等级

Runtime Profile 至少区分：

- container
- hardened-container
- microvm
- virtual-machine
- local-process

公共 SaaS 默认不得使用 `local-process`。

高风险、非可信代码优先使用 hardened-container 或 microVM。

## 3. 网络

默认：

```text
network.mode = none
```

需要外网时使用：

```text
network.mode = restricted
```

并经过 Sandbox Egress Gateway。

必须阻止：

- Kubernetes API
- 云元数据地址
- Loopback / Link-local
- Cluster 管理服务
- 数据库、Redis、Temporal
- 其他租户 Sandbox
- 未授权对象存储
- DNS Rebinding
- 重定向到私网

`network.mode=full` 只允许平台策略明确批准的受信场景。

## 4. Secret

Sandbox 不获得平台长期密钥。

Secret Grant 必须：

- 绑定 sandbox/work/invocation
- 最小 scope
- 短期
- 可撤销
- 不以明文出现在 Spec、日志、Event、环境变量快照

优先通过内存文件、代理或 Workload Identity 提供。

## 5. Workspace

- `/inputs` 只读。
- `/workspace` 只能访问当前 Workspace。
- `/outputs` 只能写临时 Staging。
- `/tmp` 生命周期不超过 Sandbox。
- 禁止跨 Tenant Volume。
- Snapshot 不得包含 Secret、ServiceAccount Token 或平台代理凭据。

## 6. Artifact 安全

输出进入 Artifact Staging 后由平台执行：

- Digest
- MIME
- Size
- Malware
- Active content
- Tenant
- Capability Artifact 契约

验证前不得交付、预览或作为下游正式输入。

## 7. Kubernetes

只有独立 Sandbox Provisioner 拥有最小 Kubernetes RBAC。

Agent API、普通 Worker、DeerFlow、Plugin 和 Sandbox 无 Kubernetes API 权限。

Namespace 不是唯一租户隔离边界，必须组合：

- Runtime isolation
- NetworkPolicy
- Egress Gateway
- RLS
- Object Storage 隔离
- Workload identity
- Audit

## 8. 审计

记录：

- Sandbox 创建/恢复/终止
- Runtime Profile
- Image/Provider Revision
- Network Policy
- Secret Grant
- Exec Command 摘要
- Runtime Session
- Snapshot
- Policy denial
- Security violation
