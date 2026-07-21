# Sandbox 安全与隔离规范

## 默认拒绝

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

## 隔离等级

Runtime Profile 至少区分：

- container
- hardened-container
- microvm
- virtual-machine
- local-process

公共 SaaS 默认不得使用 `local-process`。

高风险、非可信代码优先使用 hardened-container 或 microVM。

## 网络

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

## Secret

Sandbox 不获得平台长期密钥。

SecretGrant 与 Credential Gateway 必须：

- 绑定 Tenant、PrincipalContext Digest、WorkOrder 或 ArtifactOperation ExecutionScope、ProviderRevision 与当前 Workload Identity
- 绑定用途、目标、Secret Reference 集合和 pre-grant Operation Intent Digest
- 最小 scope
- Token 短 TTL、sender-constrained、只授权一次 Credential Access，Grant 消费与审计先于材料释放
- 撤销、过期、已消费和请求摘要不匹配均同步 fail-closed
- 明文、Delivery Handle 和可重放 Token 不进入 PostgreSQL、Redis、Temporal、Queue、Artifact、日志、Event、Trace、Recording 或环境变量快照

Phase 0 不声明账号交互登录、浏览器 Cookie 接管或私有 Git Credential Flow；这些能力在完成专用交互授权与撤销设计前保持 deferred。

## Workspace

- `/inputs` 只读。
- `/workspace` 只能访问当前 Workspace。
- `/outputs` 只能写临时 Staging。
- `/tmp` 生命周期不超过 Sandbox。
- 禁止跨 Tenant Volume。
- Snapshot 不得包含 Secret、ServiceAccount Token 或平台代理凭据。

## Artifact 安全

输出进入 Artifact Staging 后由平台执行：

- Digest
- MIME
- Size
- Malware
- Active content
- Tenant
- Capability Artifact 契约

验证前不得交付、预览或作为下游正式输入。

## Kubernetes

只有独立 Sandbox Provisioner 拥有最小 Kubernetes RBAC。

Agent API、普通 Worker、任何 Agent Runtime Provider（包括 DeerFlow）、Plugin 和 Sandbox 无 Kubernetes API 权限。

Namespace 不是唯一租户隔离边界，必须组合：

- Runtime isolation
- NetworkPolicy
- Egress Gateway
- RLS
- Object Storage 隔离
- Workload identity
- Audit

## 审计

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
