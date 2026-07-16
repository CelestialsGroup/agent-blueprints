# Kubernetes Deployment Profiles

`base/` is a policy-bearing, renderable architecture base. It is not a standalone production installation.

It deliberately requires an environment Overlay to supply:

- public Gateway namespace labelled `agent-platform.io/public-gateway=true`
- dependency namespace labelled `agent-platform.io/control-plane-dependency=true`
- Egress Gateway namespace labelled `agent-platform.io/egress-gateway=true`
- concrete PostgreSQL, Redis, Temporal and Object Storage endpoints
- TLS, Secrets, StorageClass, RuntimeClass and image digests
- CNI implementation that enforces NetworkPolicy
- HPA/KEDA, topology and regional policy

Security boundaries in the base:

- separate `agent-platform` and `agent-runtime` namespaces
- default-deny ingress and egress in both namespaces
- explicit DNS rules
- public ingress restricted by namespace label
- Sandbox Provisioner RBAC limited to `agent-runtime`
- Runtime Gateway uses Restricted-compatible SecurityContext
- Sandbox egress only through an Egress Gateway

A production deployment is accepted only after the selected Overlay passes:

```text
kubectl kustomize
server-side dry-run
policy tests
network reachability tests
Pod Security admission tests
failure injection
```
