# ADR-0018：Run 锁定不可变 ProviderRevision

## Status

Accepted

## Context

ProviderInstance 是可变逻辑配置。如果 Run 只保存 Instance ID，配置、权限或镜像更新后无法复现历史执行。

## Decision Drivers

- 可复现
- 安全回滚
- 灰度升级
- 审计

## Considered Options

- 锁定 Instance ID
- 复制全部字段到 Run
- 不可变 ProviderRevision + Resolution

## Decision

每次 Plugin、配置、权限、镜像或 Conformance 变化创建 ProviderRevision。ProviderResolution 固化 Revision、Capability Digest 和路由原因。

## Consequences

- 历史 Run 可解释
- Revision 数量增长
- 配置 Secret 只保存 Digest/Reference

## Risks

- Revision 清理过早
- Secret Rotation 与历史恢复冲突

## Migration Plan

- Instance 更新改为产生 Revision
- RunManifest 引用 Revision

## Validation

- 配置变更复现测试
- Draining/Canary 测试
- Rollback 测试
