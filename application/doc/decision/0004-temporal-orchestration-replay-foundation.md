# 0004 Temporal Orchestration And Replay Foundation

Date: 2026-07-28

Status: accepted and implemented for the bounded B03.1 foundation. This
decision admits the Temporal development and integration-test supply chain and
fixes the adapter and compatibility boundaries. The implementation does not
admit a production Workflow Start caller, choose a production Temporal topology,
or establish Phase 0B, reliability, security, or production approval.

## Context

The locked Blueprint assigns durable orchestration History to Temporal and
current state, ledgers, Outbox, and Inbox to PostgreSQL. It requires exact SDK
and Server pins, deterministic Replay, immutable Worker version identity,
at-least-once Activities, reconciliation, and retained compatible Worker code.
The locked Contract owns WorkflowRun, OrchestrationBinding, RootBinding, and
WorkOrder behavior. Application consumes those facts through
`dependency-lock.json`; this record does not redefine them.

B02.3 provides the bounded Tenant-qualified WorkOrder parent needed to prove an
immutable WorkflowRun start confirmation. It does not provide authenticated
production Start-intent ownership, the complete Turn/Grant/Message/WorkOrder
admission transaction, Root Admission, RunManifest, or Canonical Platform Event
persistence. A Temporal client can therefore be proven behind an internal
adapter and integration harness, but cannot yet be exposed as a production
WorkOrder Start path.

## Admitted Inputs

| Input | Immutable pin | Source and license |
|---|---|---|
| Temporal Go SDK | `go.temporal.io/sdk v1.46.0`, tag commit `8e2c89c7c9d8d41f633bf039063422dd10c1fec5`, module sum `h1:zD2l907+4iVkLsnJZwFj/oIIjYsoqyjsHlKO/3tDKoU=`, module-file sum `h1:x3v/9ImVh469kiHspoq1xgLdPnetbfuCAm+Y1+sUtIo=` | Official `temporalio/sdk-go` release, MIT |
| Temporal Server test image | `temporalio/auto-setup:1.29.7@sha256:f14912b699cf73015ad5c4fc18d522d4b014db90e794039214dfb7c022c2644f` | Official Temporal image, Temporal Server MIT |
| Temporal Server source | `v1.29.7`, tag commit `1f74f0c8e9935980d92a39069185671bbbba7c7e` | Official `temporalio/temporal` release, MIT |
| Image build revision | `cb8c66860ecef6ddc413fdc187494df0beae7407` | Image build metadata retained separately from the Server source revision |

The image pin is the multi-architecture OCI index. Its reviewed platform
manifests are
`sha256:ee7a2ff6a9d5a60ed05f9b0d42731828a903fd73e0719de2b746a2e6e015494c`
for Linux arm64 and
`sha256:e6177198ce6031f289bf24d80c42bf6b50f19768a8833d043eb74422430b054e`
for Linux amd64. The harness consumes the index digest so Docker selects only a
manifest governed by that immutable index.

SDK `v1.46.0` declares Go `1.25.4`, which is compatible with the governed Go
`1.26.5` toolchain. Every direct or indirect module retained in Application
`go.mod` after `go mod tidy` is pinned by `go.sum` and registered in
`toolchain/third-party.json`. That inventory records the license, public source,
maintenance and security review source, alternatives, and rollback strategy;
it is part of the implementation Gate and generated SBOM/provenance inputs.

Several SDK-selected transitives, including `facebookgo/clock`,
`gogo/protobuf`, and `robfig/cron`, have old release lines. They are recorded as
`upstream_selected`, not represented as independently active Application
choices. Application does not fork or override them because their compatibility
is owned by the reviewed SDK module graph; each SDK upgrade must re-audit the
selected graph. Security review URLs and dates record where the review was
performed, not a claim that a component is vulnerability-free.

The disposable `auto-setup` image is admitted only for real-Temporal integration
and Replay evidence. It shares no production selection meaning. Production
Temporal Cloud versus self-hosted topology, persistence layout, namespace,
retention, encryption keys, backup, multi-cluster, and disaster recovery remain
unselected.

## Decision

Temporal SDK types remain inside the Temporal adapter, Workflow, Activity,
Worker assembly, and integration/Replay tests. The orchestration domain and
PostgreSQL repository expose framework-neutral values and errors; they do not
expose Temporal clients, protobuf messages, native Run IDs, namespace,
endpoint, raw History, pgx, or sqlc rows. Native execution references are
transient adapter data, and only their governed digest may enter the stable
WorkflowRun binding.

The stable Workflow ID is derived from the already persisted WorkOrder identity.
Start uses fail-closed conflict and reuse policies. A timeout or lost response is
an unknown outcome: the adapter describes and reconciles the stable identity
before a confirmation can be appended or a retry can be treated as failed.
Temporal network I/O never occurs inside a PostgreSQL transaction. Only a
confirmed or reconciled execution can be submitted to the idempotent
WorkflowRun confirmation repository.

Workflow code is deterministic and contains bounded identifiers, digests,
enums, and timestamps only. PostgreSQL and every external interaction occur in
Activities with bounded timeouts and explicit retry behavior. Prompt text,
user content, credentials, endpoints, tokens, binary payloads, and mutable
process configuration are forbidden from Workflow History. Continue-as-New
preserves the Platform WorkflowRun identity and does not append another start
confirmation.

Workflow and Activity names are explicit stable constants. Workers declare an
immutable Deployment name and Build ID, enable Worker Deployment Versioning,
and use pinned default Versioning Behavior. A workflow definition change must
be Replay-compatible, use an admitted Temporal patch, or introduce a new
workflow version. The previous Build ID and compatible code remain available
until every pinned execution has completed or followed an admitted migration
path. New Workers drain gracefully; they do not replace pinned executions in
place.

Sanitized History fixtures are immutable, source-bound test evidence. They must
replay against current code, and every decoded payload must be scanned for
prohibited content. Mocks can test error mapping but cannot replace the admitted real
Temporal image for stable Start identity, response-loss reconciliation, retry,
Continue-as-New, Worker recovery, or Replay evidence.

## Blocked Production Surfaces

B03.1 does not wire a deployable production caller to Temporal Start. That
remains blocked until an authoritative persisted Start intent and complete
admission transaction bind Tenant, WorkOrder, Grant consumption, request digest,
and caller authority. The integration harness may exercise the adapter only
against an already persisted WorkOrder and a bounded, internally allocated
Platform WorkflowRun identity.

The slice also does not create or claim:

- WorkOrder plus Workflow Start Outbox atomic creation;
- an externally visible WorkOrder state transition or Canonical Platform Event;
- WorkflowRunRootBinding, RunManifest, Root Admission, or Provider admission;
- Safety Controller policy or Runtime Start/Status/Control effects;
- a production Payload Codec, key owner, namespace, retention, or Server
  deployment topology.

Application must not bridge any of these gaps with a nullable native identifier,
unconstrained string, pseudo-foreign key, hidden Temporal field, private event,
or Contract modification.

## Alternatives Rejected

- An in-memory or PostgreSQL-only workflow engine: it would discard the selected
  durable History, Replay, Timer, retry, and Worker versioning foundation.
- A floating SDK version or `auto-setup:latest`: neither binds build evidence to
  immutable inputs.
- Treating Server source `v1.29.7` or the image tag alone as the image identity:
  neither closes the OCI supply-chain input; the index digest is required.
- Temporal SDK types in domain or repository APIs: that would make orchestration
  authority and persistence contracts depend on a replaceable framework.
- Persisting native Run ID, endpoint, namespace, or raw History in WorkflowRun:
  those are adapter-private and operational facts, not stable domain identity.
- Retrying an unknown Start as a fresh request: it can split one WorkOrder across
  executions; reconciliation is required before confirmation.
- Using the disposable Server image as a production selection: it has broader
  setup behavior than a reviewed production deployment and carries no topology,
  capacity, backup, retention, or disaster-recovery approval.

## Upgrade And Rollback

SDK upgrades update the exact module version, tag commit, sums, all selected
transitives, inventory, SBOM, and provenance together. Before admission they
must pass unit/race tests, all accepted History Replay fixtures, real Temporal
start/reconciliation/retry/Continue-as-New tests, and real PostgreSQL
confirmation tests. Workflow changes follow the same Replay and Worker
versioning policy even when the SDK pin is unchanged.

Server image upgrades update the version, Server source commit, image build
revision, index digest, and reviewed platform manifests together. They require a
fresh disposable database plus protocol and Replay/integration evidence. A
Temporal persistence data directory is never downgraded in place.

Rollback drains the new Worker Build and restores the previous admitted SDK,
transitive lock, binary, and retained compatible Worker code only after Replay
proves it can process every retained History. Test Server rollback starts a
fresh disposable environment at the prior reviewed image digest; it does not
reinterpret or delete existing History. Database WorkflowRun facts are
immutable and are never removed to simulate a Temporal rollback.
