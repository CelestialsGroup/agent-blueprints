# Kubernetes Starter

这些 Manifest 只是 Phase 0 架构骨架，不是完整生产配置。

## 目录

```text
base/
  namespace.yaml
  agent-api.yaml
  agent-worker.yaml
  runtime-gateway.yaml
  migration-job.yaml
  network-policy.yaml
  pdb.yaml
  kustomization.yaml
```

生产环境必须补充：

- 镜像 Digest
- Secret 管理
- PostgreSQL/Temporal/Object Storage 连接
- HPA/KEDA
- Ingress/Gateway
- TLS
- 完整 NetworkPolicy
- topologySpreadConstraints
- 监控与告警


## 重要边界

Base Manifest 是架构与安全边界骨架，不是可直接上线的生产 Overlay。

生产 Overlay 必须明确：

- CNI 是否执行 NetworkPolicy
- DNS 与 Egress Gateway
- 托管 PostgreSQL/Temporal/Object Storage Endpoint
- Sandbox Runtime Namespace
- External Secrets
- Topology/AZ
- HPA/KEDA
- Ingress/Gateway TLS
