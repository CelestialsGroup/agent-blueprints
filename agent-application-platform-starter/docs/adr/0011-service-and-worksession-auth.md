# ADR-0011：Service OAuth 与 WorkSession 双认证模型

## Status

Accepted

## Context

业务后端和终端用户前端具有不同信任等级，不能共享长期凭据。

## Decision Drivers

- 最小权限
- 租户隔离
- 前端安全

## Considered Options

- 业务前端使用服务密钥
- 统一用户系统
- Service OAuth + WorkSession

## Decision

业务后端使用 OAuth2 Client Credentials；前端使用绑定单一 WorkOrder 的短期 WorkSession Token。client_app_id 只从认证上下文产生。

## Consequences

- 减少凭据泄漏范围
- 需要 Token 签发与撤销
- API 操作需定义 Scope

## Risks

- 跨租户资源枚举
- WorkSession scope 过宽

## Migration Plan

- 先实现 Service OAuth Port 和本地签名 Provider
- 所有资源查询增加 Tenant Scope

## Validation

- 认证负向测试
- 跨租户访问测试
- scope 测试
