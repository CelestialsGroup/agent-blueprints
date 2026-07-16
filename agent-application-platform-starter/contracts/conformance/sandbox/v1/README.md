# Sandbox Provider Conformance v1

## Required profiles

### lifecycle

- create-idempotent
- create-digest-conflict
- controller-restart-reconcile
- lease-expiration
- terminate-idempotent
- orphan-cleanup

### exec

- exec-idempotent
- exec-cancel
- exec-deadline
- stale-fencing-rejected
- outcome-unknown-reconciliation

### security-restricted

- no-host-namespace
- no-kubernetes-api
- no-cloud-metadata
- no-cross-tenant-network
- no-cross-tenant-volume
- egress-allowlist
- secret-revocation
- artifact-staging-only

### multi-node

- provider-api-restart
- controller-failover
- node-failure
- runtime-session-reroute
- provider-draining

### usage

- wall-time
- cpu
- memory
- network
- storage
- evidence-reference

## Optional profiles

- terminal
- browser
- snapshot-workspace
- snapshot-filesystem
- snapshot-process
- gpu

每个测试输出不可变 Evidence Artifact，并进入 SandboxConformanceReport。
