# ADR-0010：Runtime Gateway 路由双向会话

## Status

Accepted

## Context

Terminal、Browser 与 Desktop WebSocket 必须定位具体 Sandbox，普通 Ingress Sticky Session 不可靠。

## Decision Drivers

- 跨 Pod 路由
- 短期授权
- Sandbox 隔离

## Considered Options

- Sticky Session
- 前端直连 Pod
- Runtime Gateway

## Decision

使用 RuntimeSession 映射和短期 Token，由 Runtime Gateway 代理到目标 Sandbox。

## Consequences

- 连接可跨 API Pod
- Gateway 成为关键服务
- 需要连接容量规划

## Risks

- Token 泄漏
- Sandbox endpoint 失效

## Migration Plan

- 实现心跳、过期和重新解析
- Gateway 多副本

## Validation

- 路由鉴权测试
- Sandbox 重建测试
- 连接压测
