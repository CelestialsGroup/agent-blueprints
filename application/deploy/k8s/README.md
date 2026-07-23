# Kubernetes 部署 Profile

`base/` 只包含当前已有可构建入口的公共安全基础，不是独立的生产安装方案。B01 当前仅包含 Agent Access；Worker、Migration、Runtime Gateway 和 Sandbox Controller 必须在各自二进制、测试和镜像存在后再加入阶段 Overlay。

它有意要求环境 Overlay 提供：

- 标记为 `agent.shell-echo.github.io/public-gateway=true` 的公共 Gateway Namespace；
- 标记为 `agent.shell-echo.github.io/control-plane-dependency=true` 的依赖 Namespace；
- 具体的 PostgreSQL、Redis、Temporal 和 Object Storage Endpoint；
- TLS、Secret、StorageClass、RuntimeClass 和镜像摘要；
- 能强制执行 NetworkPolicy 的 CNI 实现；
- HPA/KEDA、拓扑和区域策略。

Base 中的安全边界：

- `agent` Namespace 的 Ingress 和 Egress 默认拒绝；
- 显式 DNS 规则；
- 通过 Namespace Label 限制公共 Ingress；
- Agent Access 使用兼容 Restricted Profile 的 SecurityContext。

0D/0E 引入 `agent-runtime`、Sandbox RBAC、Runtime Gateway 和 Egress 路径时，必须在对应阶段重新加入并单独通过策略测试，不能预先放入当前 Base。

只有所选 Overlay 通过以下检查后，生产部署才能被接受：

```text
kubectl kustomize
服务端 Dry-run
策略测试
网络可达性测试
Pod Security 准入测试
故障注入
```
