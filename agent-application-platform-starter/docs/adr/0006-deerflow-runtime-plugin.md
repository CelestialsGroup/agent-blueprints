# ADR-0006：DeerFlow 作为默认 Agent Runtime

## Status

Accepted

## Context

项目希望快速获得通用 Agent、Sub-Agent、Skill、MCP 和 Sandbox 能力，同时保留未来替换空间。

## Decision Drivers

- 快速实施
- 上游可升级
- 平台边界独立

## Considered Options

- 完全自研 Agent Runtime
- 深度 Fork DeerFlow
- 通过 Adapter 作为 Runtime Plugin

## Decision

DeerFlow 通过 Anti-Corruption Adapter 接入。平台 API、Artifact 核心和业务逻辑不进入 DeerFlow Fork。

## Consequences

- 可低成本跟随上游
- 需要维护 Contract Test
- 某些版本可能有实例亲和性

## Risks

- 上游 API 变化
- 本地状态影响多副本

## Migration Plan

- 锁定 Commit 与镜像 Digest
- 补丁登记
- 逐步外置 Checkpoint 和 Sandbox

## Validation

- DeerFlow Contract Suite
- 升级 Canary
- 历史回放兼容测试
