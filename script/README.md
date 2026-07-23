# Agent Scripts

This directory contains development and validation scripts kept outside Blueprint, Contract, and Application. Contract-specific automation is grouped under `contract/`; generated environments and evidence remain at this Script root.

## Contract Scripts

- `contract/validation/`: Schema, semantic, OpenAPI, static, supply-chain, and evidence checks.
- `contract/compatibility/`: frozen-baseline compatibility comparison.
- `contract/manifest/`: cross-language Contract Manifest verification.
- `contract/jcs/`: Python, Node, and Go RFC 8785 / Strict I-JSON checks.
- `contract/maintenance/`: explicit Contract regeneration utilities.
- `evidence/`: generated Contract Gate results; these are not Contract resources.

Set the input checkouts explicitly in CI and release workflows:

```bash
export AGENT_CONTRACT_ROOT=/absolute/path/to/contract
export AGENT_BLUEPRINT_ROOT=/absolute/path/to/blueprint
```

For local development only, the defaults are `../contract` and `../blueprint`.

## Validation

```bash
./contract/bootstrap.sh
make validate-contract
```

`make validate-all` additionally checks the Script package supply chain. Successful validation writes `evidence/VALIDATION.json` and `evidence/CONTRACT_VALIDATION_REPORT.md`; intermediate output remains in `build/validation/`.

A green Contract Gate proves that the selected declarative Contract is internally consistent. It does not prove 0B implementation, 0C-0G integration, 0H reliability, formal freeze, or production approval.
