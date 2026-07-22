# Contract Scripts

This directory contains scripts that validate and maintain the independent declarative Contract package. It is not part of the Contract and contains no Agent Platform product implementation.

- `bootstrap.sh`: installs pinned Python and Node dependencies at the Script root.
- `validate.sh`: runs the complete Contract validation sequence.
- `validation/`: Contract, semantic, OpenAPI, supply-chain, and evidence checks.
- `compatibility/`: frozen-baseline compatibility comparison.
- `manifest/`: cross-language Contract Manifest verification.
- `jcs/`: Python, Node, and Go RFC 8785 / Strict I-JSON checks.
- `maintenance/`: explicit regeneration utilities for governed Contract resources.

Run supported entry points from the parent `script/` directory through `make`. Scripts resolve Contract resources through `AGENT_PLATFORM_CONTRACT_ROOT`, with `../contract` only as a local fallback. Generated environments, build output, and Gate evidence stay under `script/`.
