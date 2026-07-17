# Agent Runtime Provider Contract

## Purpose

DeerFlow is the first implementation of `agent-runtime-provider-v1.yaml`, not an internal Platform domain model. The contract keeps upstream Thread, Run, Checkpoint and event payloads behind an anti-corruption Adapter.

```text
Temporal Workflow / Invocation Ledger
 -> AgentRuntimeProvider Port
    -> DeerFlowAdapter
    -> future runtime Adapter
```

## Stable operations

- immutable capability negotiation for one ProviderRevision;
- idempotent start/restore of a runtime run;
- append-only commands: input, interrupt, pause, resume, cancel, approval and checkpoint;
- confirmed status query;
- cursor-based durable provider event read;
- portable checkpoint manifest with explicit compatibility class.

Every mutation carries InvocationAttempt identity, idempotency and fencing. The Platform rejects stale results and normalizes runtime events into ConversationMessage, CanonicalEvent, Approval, Invocation, Artifact and Usage records.

`contracts/state-machines/agent-runtime-run-v1.json` is authoritative for normalized run status. Cancellation intent never proves cancellation, and `outcome_unknown` is non-terminal: the Invocation Ledger must reconcile provider evidence before the Platform commits a terminal result.

## DeerFlow private state

The following never enter stable Platform contracts:

- DeerFlow thread/run/checkpoint IDs;
- upstream database rows and event payloads;
- instance-local route or process identity;
- DeerFlow tool/model credentials.

The Adapter private store maps these values to `runtime_run_id` and `provider_state_reference`.

## Upgrade discipline

Each upstream upgrade creates a new immutable ProviderRevision and must pass:

- start/append-input/interrupt/pause/resume/cancel;
- event cursor deduplication and normalization golden files;
- Tool/Model Gateway interception and budget enforcement;
- Sub-Agent, approval, Artifact staging and Usage;
- checkpoint export/restore compatibility;
- old checkpoint and historical event replay;
- canary plus draining without moving existing runs to a new Revision.

Prefer configuration, skills, MCP and external Adapter changes. Core patches require a patch ledger, upstream base commit and rebase test.
