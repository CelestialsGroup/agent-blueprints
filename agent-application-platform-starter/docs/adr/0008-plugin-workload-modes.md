# ADR-0008：Plugin 使用明确 Workload Mode

## Status

Accepted

## Context

不同插件的资源和生命周期差异较大，通用 sidecar 概念不能支持独立扩缩容。

## Decision Drivers

- 资源隔离
- 独立发布
- 可预测调度

## Considered Options

- 全部 sidecar
- 全部远程服务
- service/job/sandbox_cli/mcp/remote_service

## Decision

Plugin Runtime Mode 固定为 service、job、sandbox_cli、mcp、remote_service。Sidecar 仅是具体 Pod 内部实现细节。

## Consequences

- 重型 Converter 可用 Job
- Plugin Invoker 需要多种 Adapter
- Manifest 更严格

## Risks

- Mode 语义漂移
- Job 结果丢失

## Migration Plan

- 统一映射到 Plugin Invocation Protocol
- 每种 Mode 提供 conformance

## Validation

- Manifest oneOf 验证
- Invocation 端到端测试
