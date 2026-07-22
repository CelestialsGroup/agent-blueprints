# Sandbox Provider 一致性规范 v1

## 必需 Profile

### 生命周期

- create-idempotent
- create-digest-conflict
- controller-restart-reconcile
- lease-expiration
- terminate-idempotent
- orphan-cleanup

### 执行

- exec-idempotent
- exec-cancel
- exec-deadline
- stale-fencing-rejected
- outcome-unknown-reconciliation

### 受限安全

- no-host-namespace
- no-kubernetes-api
- no-cloud-metadata
- no-cross-tenant-network
- no-cross-tenant-volume
- egress-allowlist
- secret-revocation
- artifact-staging-only

### 多节点

- provider-api-restart
- controller-failover
- node-failure
- runtime-session-reroute
- provider-draining

### 用量

- wall-time
- cpu
- memory
- network
- storage
- evidence-reference

## 可选 Profile

- terminal
- browser
- snapshot-workspace
- snapshot-filesystem
- snapshot-process
- gpu

每个测试输出不可变 Evidence Artifact，并进入 SandboxConformanceReport。
