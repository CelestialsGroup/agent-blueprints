# Contract Validation Report

Baseline: v0.8 Sandbox-ready Architecture Baseline

## Results

- Package files: 238
- Portable JSON Schema resources: 102
- JSON Schema meta-validation: passed
- Valid fixtures: 19 passed
- Schema-invalid fixtures: 8 rejected as expected
- Additional Sandbox semantic-negative fixtures: 2 rejected as expected
- Agent Access OpenAPI: 0 errors / 0 warnings
- Plugin Invocation OpenAPI: 0 errors / 0 warnings
- Delivery Webhook OpenAPI: 0 errors / 0 warnings
- Sandbox Provider OpenAPI: 0 errors / 0 warnings
- OpenAPI bundles: 4 generated successfully
- npm audit: 0 known vulnerabilities
- Markdown link scan: 0 missing links
- Kustomize resource scan: 0 missing resources
- ZIP integrity: passed

## Sandbox Contract Gates

- SandboxSpec requires immutable image digest.
- Restricted network requires an enforced Policy reference and Egress Gateway.
- Required Sandbox capabilities must be declared by the ProviderRevision.
- Create/Exec/Snapshot/Terminate use Operation, Attempt, Fencing and Idempotency.
- Runtime endpoints remain internal to Runtime Gateway.
- RunManifest locks Sandbox ProviderRevision, Spec Digest and Conformance Digest.
- ProviderRevision requires provider_kind=sandbox and Sandbox Conformance evidence.
- A RunManifest missing Sandbox ProviderRevision is rejected.

## Commands

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-contracts.txt
npm ci
make validate-contracts
make bundle-openapi
```
