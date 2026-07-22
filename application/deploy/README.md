# Deployment Assets

This directory contains environment assembly, not domain logic or source-of-
truth configuration. Images, charts, and manifests must use immutable digests
and consume secrets through environment-specific identity and secret systems.

- `local/` is reproducible developer and integration infrastructure.
- `k8s/` is the Kubernetes deployment profile.

Deployment assets never run application migrations implicitly and do not prove
production readiness without environment-specific tests.
