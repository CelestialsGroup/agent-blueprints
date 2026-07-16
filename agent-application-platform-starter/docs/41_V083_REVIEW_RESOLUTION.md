# v0.8.3 Review Resolution

## Architecture judgment

The platform design remains reasonable and extensible: Scenario → CapabilityDefinition → ProviderResolution → immutable ProviderRevision keeps business intent independent from provider/runtime selection. Ports, immutable revisions, admission decisions, multiple Sandbox Slots, and Adapter-private backend identity allow DeerFlow, a future `sandbox-runtime`, model/tool providers, and independently installable plugins to evolve without replacing the stable kernel.

The review exposed enforcement gaps rather than a need to redraw the domain architecture. v0.8.3 therefore hardens contracts and admission mechanics while preserving the established Business/Platform boundary.

## Run admission

Schema alone cannot prove a digest against Registry state or decide which certification decision is latest. `RunAdmissionContext` is the explicit trusted input to the admission validator. The validator requires:

- exact equality between the admitted Scenario and RunManifest Scenario;
- exact set equality between Scenario-required and resolved capabilities;
- RFC 8785 self-digest verification of every ProviderRevision and AdmissionDecision;
- latest decision per Revision, with decision sequence uniqueness and `certified` outcome;
- exact Snapshot reconstruction and ProviderInstance binding;
- unique Sandbox Slots and one existing primary Slot.

The implementation must obtain this context from authoritative Registry/Scenario storage in a consistent transaction or revisioned read. A caller-supplied context is never trusted merely because it is Schema-valid.

## Safe cancellation

Cancellation is a request, not proof that an external side effect did not occur. Running operations enter `cancel_requested`; lost responses enter or remain in reconciliation. Provider/manual evidence creates `cancellation_confirmation`, then the aggregate enters `cancellation_confirmed`, and only a durable terminal commit enters `cancelled`. If evidence cannot be obtained, the operation remains reconcilable or is abandoned through an append-only manual decision with `risk_accepted=true`.

## Compatibility scope

The compatibility comparator blocks the known high-value narrowing classes and has executable self-tests for the review examples. It is intentionally described as conservative, not formally complete for the full JSON Schema/OpenAPI languages. Protected repository variables select the immutable baseline; a PR cannot turn the check into N/A by editing policy JSON.

## Repository integration

The ZIP cannot commit a Workflow or remove `.DS_Store` in the user's parent monorepo. Before public CI, run the installer from the tracked package, commit the Git-root Workflow, configure protected variables, remove any tracked `.DS_Store`, and verify both official commands from a clean checkout.
