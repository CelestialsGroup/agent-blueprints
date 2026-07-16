# v0.8 Sandbox Architecture Audit Report

## 1. Conclusion

v0.8 resolves the future Sandbox replacement risk before implementation begins.

The architecture now treats Sandbox as a first-class infrastructure provider with
a dedicated lifecycle contract. DeerFlow Built-in Sandbox and the future
`sandbox-runtime` are interchangeable ProviderRevisions behind the same
SandboxProvider Port.

The architecture is approved for Codex Phase 0.

## 2. Stable Boundary

```text
Agent Platform Stable Kernel
  SandboxRegistry
  SandboxSpec / Desired State
  SandboxLease
  SandboxOperation
  Sandbox RuntimeSession Authorization
  Sandbox Usage Normalization
          ↓
Sandbox Provider Contract
          ↓
DeerFlowSandboxAdapter | sandbox-runtime
```

The following remain independent from the Sandbox implementation:

- WorkOrder
- Durable Workflow
- AgentRun
- Invocation
- Canonical Event
- Artifact Workspace
- Runtime Gateway
- Frontend
- Usage and Delivery

## 3. Contract Coverage

The Sandbox Provider API now defines:

- Capability Negotiation
- Create
- Desired State
- Lease Extension
- Exec and Cancel
- Internal Runtime Session
- Snapshot and Restore
- Terminate
- Operation Query
- Durable Provider-local Event Stream

All mutation operations use:

- operation_id
- attempt_id
- fencing_token
- idempotency_key
- request_digest where applicable
- deadline

## 4. State and Reliability

Sandbox lifecycle is separated from process execution:

```text
Sandbox:
requested -> provisioning -> ready
ready -> suspended -> ready
* -> terminating -> terminated
* -> expired | failed

Exec:
accepted -> running -> completed | failed | outcome_unknown
running -> cancel_requested -> cancelled
```

Desired and observed state are separated with generation counters. Controller
restarts, multi-controller races and stale results are handled through reconciliation
and fencing rather than in-memory ownership.

## 5. Security

The default profile is unprivileged and denies:

- privileged containers
- host namespace access
- hostPath
- service account token
- privilege escalation
- unrestricted egress

Restricted egress requires a platform Egress Gateway. Sandbox output can only enter
Artifact Staging. Long-lived platform secrets are never directly exposed.

## 6. Workspace and Artifact

Stable paths:

```text
/inputs      read-only input Artifacts
/workspace   mutable working tree
/outputs     Artifact Staging
/tmp         ephemeral
```

Sandbox providers cannot create ArtifactVersion records or write platform databases.

## 7. Snapshot

Snapshots are explicitly classified:

- Workspace Snapshot
- Filesystem Snapshot
- Process Snapshot

Portability and compatibility are declared. Process Snapshot is never assumed to be
portable across architecture, kernel, runtime profile or provider.

## 8. Version and Migration

RunManifest locks:

- Sandbox ProviderInstance
- Sandbox ProviderRevision
- Provider API version
- Runtime Profile
- Image Digest
- SandboxSpec Digest
- Required Capability versions
- Sandbox Conformance Report Digest

Migration from DeerFlow to sandbox-runtime follows:

1. Contract adapter
2. Shadow validation
3. Scenario Canary
4. Default binding switch
5. DeerFlow Provider draining

Old Runs continue using their locked ProviderRevision.

## 9. Standards Boundary

- OCI Image compatibility is required.
- OCI Runtime compatibility is required only when implementing a low-level runtime.
- Kubernetes CRI is required only when replacing the node container runtime.
- RuntimeClass mapping is an internal provider implementation detail.
- Kubernetes Pod, containerd, Firecracker and Apple Container identifiers do not enter public contracts.

## 10. Validation Evidence

- 102 portable JSON Schemas
- 19 valid fixtures
- 8 schema-negative fixtures
- 2 Sandbox semantic-negative fixtures
- 4 OpenAPI definitions with zero errors and warnings
- 4 successful OpenAPI bundles
- 0 known npm vulnerabilities

## 11. Remaining Production Evidence

Architecture approval is not production approval.

The implementation must still prove:

- Controller failover
- Node failure recovery
- Orphan cleanup
- Security isolation
- Egress policy enforcement
- RuntimeSession reconnect
- Snapshot restore
- Provider draining
- Performance and capacity
- Cross-provider migration and rollback
