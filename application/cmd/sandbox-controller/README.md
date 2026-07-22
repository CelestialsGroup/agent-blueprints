# Sandbox Controller

Phase: **0D, not implemented**.

This privileged process will implement the platform SandboxProvider and manage
an isolation backend through least-privilege credentials. Kubernetes support,
if selected, belongs behind this boundary.

Pod, VM, container, node, namespace, and raw endpoint identifiers remain
provider-private. They must not enter stable domain tables or public contracts.
