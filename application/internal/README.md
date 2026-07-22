# Go Platform Kernel

This directory contains non-public Go packages for the modular platform
monolith. Dependencies flow inward: transports and infrastructure may depend on
domain/application ports, while domain packages must not depend on HTTP, pgx,
Temporal, Redis, object storage, Kubernetes, or Provider SDK details.

Cross-package behavior is passed through explicit values and interfaces. Do not
create a generic shared package or mutable service locator.
