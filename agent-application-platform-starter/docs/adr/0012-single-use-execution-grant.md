# ADR-0012：ExecutionGrant 单次消费

## Status

Accepted

## Context

业务系统需要把会员和商业授权转换为 Agent 可执行预算，同时防止请求被重放或篡改。

## Decision Drivers

- 防重放
- 业务与 Agent 解耦
- 原子创建 WorkOrder

## Considered Options

- Agent 查询会员服务
- 长期授权 Token
- 短期单次 JWS

## Decision

ExecutionGrant 使用 EdDSA/ES256 Compact JWS，最大 TTL 300 秒，绑定请求摘要和 Idempotency Key 摘要，并与 WorkOrder 创建同事务消费。

## Consequences

- 安全边界明确
- 业务系统需要签名基础设施
- 需要时钟同步和 Key Rotation

## Risks

- Grant 被重复消费
- 摘要 canonicalization 不一致

## Migration Plan

- 提供 RFC 8785 测试向量
- 建立 JWKS 缓存和轮换

## Validation

- 重放测试
- 不同摘要冲突测试
- 过期与算法测试
