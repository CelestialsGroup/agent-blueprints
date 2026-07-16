# ADR-0016：使用绝对 Schema ID 与内容摘要

## Status

Accepted

## Context

v0.6 使用 URN $id 却保留文件相对 $ref，标准 Validator 无法在独立发布环境解析，旧校验脚本通过私有映射掩盖了问题。

## Decision Drivers

- 跨语言可移植
- 独立发布
- 可复现 Capability 契约

## Considered Options

- 文件相对引用
- 单一巨大 Schema Bundle
- 绝对 URI/URN + Digest

## Decision

所有 Schema 使用绝对 $id；跨 Schema $ref 使用绝对标识；Capability/Scenario 通过 SchemaReference 保存 URI、SHA-256 Digest 和 Dialect。

## Consequences

- 可以独立解析和缓存
- 需要 Schema Registry
- Digest 更新必须版本化

## Risks

- Digest 计算算法不一致
- Registry 内容漂移

## Migration Plan

- 迁移旧相对 ref
- 引入现代 referencing Registry
- 发布 Bundle

## Validation

- 独立 Validator 测试
- Portable Reference Scan
- Digest Fixture
