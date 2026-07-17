# Codex Phase 0 Bootstrap — v0.9.0

Read `START_HERE.md`, `AGENTS.md`, `docs/45_V090_PRODUCT_BOUNDARY_RESOLUTION.md` and `tasks/PHASE0.md`. v0.8.6 and earlier are historical evidence only.

## Admission first

```bash
./scripts/bootstrap_contracts.sh
make validate-all
```

Fix any contract failure before implementation. Do not begin Phase 1 before every Phase 0 acceptance item has runtime evidence.

## Implementation order

1. Conversation/Message/Turn/Workspace migrations and constraints.
2. CommercialAuthorizationSnapshot, Grant consumption and quota reservation/settlement reference flow.
3. WorkOrder/Outbox and Temporal Workflow.
4. ProviderResolution, immutable Revision/Admission/Experience snapshots and RunManifest.
5. DeerFlow AgentRuntimeProvider Adapter, command/event/checkpoint private mapping.
6. DeerFlow Built-in Sandbox Adapter and Invocation/Sandbox ledgers.
7. Canonical Event, Artifact staging/finalization, RuntimeRecording and Delivery.
8. html-anything Catalog import plus one Converter Provider.
9. multi-turn Workbench and offline historical replay.
10. duplicate/lost-response/replay/security/backup tests.

## Prohibitions

- Do not copy Business user, membership, order, payment or balance truth into Agent Platform.
- Do not treat WorkOrder as an unbounded Conversation or make Workspace WorkOrder-local.
- Do not expose DeerFlow Thread/Run/Checkpoint payloads outside its Adapter.
- Do not persist live Runtime bytes in Event, Temporal or PostgreSQL.
- Do not identify a template only by mutable string or hard-code a nexu Plugin ID.
- Do not load arbitrary remote JavaScript or give UI extensions host cookies/tokens/DOM access.
- Do not claim Exactly-once or Production Ready.

Every commit states boundary impact, document/contract/implementation/evidence classification, enforcement added, tests run and properties not yet proven.
