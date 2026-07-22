# Kubernetes 部署 Profile

`base/` 是包含策略且可渲染的架构基础，不是独立的生产安装方案。

它有意要求环境 Overlay 提供：

- 标记为 `agent-platform.io/public-gateway=true` 的公共 Gateway Namespace；
- 标记为 `agent-platform.io/control-plane-dependency=true` 的依赖 Namespace；
- 标记为 `agent-platform.io/egress-gateway=true` 的 Egress Gateway Namespace；
- 具体的 PostgreSQL、Redis、Temporal 和 Object Storage Endpoint；
- TLS、Secret、StorageClass、RuntimeClass 和镜像摘要；
- 能强制执行 NetworkPolicy 的 CNI 实现；
- HPA/KEDA、拓扑和区域策略。

Base 中的安全边界：

- 分离 `agent-platform` 和 `agent-runtime` Namespace；
- 两个 Namespace 的 Ingress 和 Egress 均默认拒绝；
- 显式 DNS 规则；
- 通过 Namespace Label 限制公共 Ingress；
- Sandbox Provisioner RBAC 仅限 `agent-runtime`；
- Runtime Gateway 使用兼容 Restricted Profile 的 SecurityContext；
- Sandbox 只能通过 Egress Gateway 出站。

只有所选 Overlay 通过以下检查后，生产部署才能被接受：

```text
kubectl kustomize
服务端 Dry-run
策略测试
网络可达性测试
Pod Security 准入测试
故障注入
```
