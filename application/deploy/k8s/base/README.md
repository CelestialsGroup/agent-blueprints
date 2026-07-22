# Kubernetes Base

These Kustomize resources define the current B01 Agent Access workload,
namespace, NetworkPolicy, service account, and availability shape. Environment
overlays must provide real endpoints, image digests, TLS, secrets, topology,
and scaling policy.

Do not add a Worker, Migration Job, Runtime Gateway, Sandbox Controller, or its
RBAC until the corresponding command, image, and component tests exist. Later
phase resources belong in explicit overlays and must not make this Base
aspirational.

Do not add environment credentials, floating image tags, raw Sandbox endpoints,
or application-owned PostgreSQL/Temporal state to this base.
