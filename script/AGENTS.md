# Agent Application Platform Script Rules

## Purpose

This directory contains non-authoritative automation for independently versioned inputs. Contract validation and maintenance scripts live under `contract/`; they do not own Contract meaning, Blueprint architecture, or Application implementation.

Resolve Contract resources through `AGENT_PLATFORM_CONTRACT_ROOT`; `../contract` is only a local fallback. Resolve Blueprint responsibility URNs through `AGENT_PLATFORM_BLUEPRINT_ROOT`; `../blueprint` is only a local fallback. Do not require a shared Git repository, shared commit history, or fixed sibling directory in release workflows.

## Change Discipline

- Keep `SCRIPT_ROOT`, `CONTRACT_ROOT`, and `BLUEPRINT_ROOT` responsibilities separate.
- Build output and Gate evidence stay at the Script root; maintenance commands may update the configured Contract checkout only when explicitly invoked.
- Contract traceability references stable validation URNs, never script file paths.
- Preserve pinned Python, Node, pnpm, Go, and Redocly versions and integrity metadata.
- Do not add Agent Platform product source, migrations, deployment configuration, or runtime evidence.

## Validation

Run `./contract/bootstrap.sh` once, then `make validate-contract`. Run `make validate-all` for Script supply-chain admission and formal-freeze preparation. A green result is Contract consistency evidence only and must not be described as implementation or production readiness.
