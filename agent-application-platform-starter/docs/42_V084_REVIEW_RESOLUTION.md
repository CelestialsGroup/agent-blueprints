# v0.8.4 Review Resolution

## Generic Provider admission

Provider admission is now uniform across Agent Runtime, Sandbox, Model, Tool, Skill, Template, Renderer, Editor, Converter and Channel. `ProviderRevision.conformance_set_digest` is the digest of the complete conformance array. Kind-specific legacy digests are optional compatibility fields and, when present, must equal the generic digest.

An authoritative RunAdmissionContext supplies CapabilityDefinitions, their immutable digests, allowed Provider kinds, the Scenario requirements, the Agent Runtime requirement, ProviderRevisions and append-only decisions. Admission verifies exact capability coverage and does not trust a caller merely because its object is Schema-valid.

## Invocation reliability

Invocation now has the same durability principles as SandboxOperation: logical record separated from append-only Attempts, current Attempt pointer, max-attempt invariant, reconciliation deadline/case, append-only manual decision and cancellation evidence. A non-idempotent unknown outcome cannot become abandoned or cancelled without explicit durable evidence and risk acceptance.

## Numeric profile

RFC 8785 specifies canonicalization, while the platform adds a stricter security admission profile. The test corpus separates these layers so RFC reference numbers such as `1E30` can test canonicalization without being accepted into security-sensitive digest inputs. Strict parsers determine mathematical integrality from the raw decimal token before binary floating-point conversion.

## Repository integration boundary

The package cannot modify or commit its parent Git repository. In a monorepo, public admission remains blocked until an integrator runs `scripts/install_github_workflow.sh`, removes any tracked root `.DS_Store`, commits the root Workflow/removal, and configures protected variables. The Gate intentionally fails before that is done.
