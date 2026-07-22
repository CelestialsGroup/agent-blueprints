# Sandbox Provider

Phase: **0D, not implemented**.

The primary platform SandboxProvider implementation and its private isolation
backend adapters belong here. It implements lifecycle, exec, snapshot, restore,
lease, status, and reconciliation contracts behind the privileged controller.

Backend topology and raw endpoints remain private. Cross-revision restore is
fail-closed without a Platform-owned CompatibilityDecision and evidence.
