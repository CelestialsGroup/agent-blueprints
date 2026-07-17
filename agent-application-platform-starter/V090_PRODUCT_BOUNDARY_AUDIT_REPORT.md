# v0.9.0 Product Boundary Audit Report

The v0.8.6 reliability kernel remains suitable, but it modeled a one-shot asynchronous execution platform more completely than a Manus-like multi-turn product. v0.9.0 closes the resulting boundary gaps before migrations are frozen.

| Product requirement | v0.9.0 enforcement |
|---|---|
| Multi-turn general Agent | Conversation/Message/first-class Branch/Turn schemas, API, CAS projection and sequence semantics |
| DeerFlow upgradeability | dedicated AgentRuntimeProvider OpenAPI, command fencing, cursor events and checkpoint manifest |
| Live and historical Sandbox | RuntimeSession recording policy plus immutable RuntimeRecording chunks/playback manifest |
| html-anything templates and customization | Experience Catalog, TemplateRevision, Scenario option sources and RunManifest binding |
| nexu-io rich projects | explicit Catalog/Capability/Converter/Editor integration profiles and isolated UiExtensionManifest |
| own User/Membership | Business-owned explicit entitlement/capability/limit snapshot and quota reservation/settlement handoff |
| mature implementation plan | one v0.9 Phase 0 vertical slice and current authority chain |

Local contract validation closes the reviewed product-boundary defects, including lifecycle state machines and non-circular recording digests. This remains an architecture/contract candidate: Phase 0 implementation, failure injection, multi-node behavior, isolation, capacity and disaster recovery still require runtime evidence.
