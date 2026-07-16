# ADR-0015：浏览器使用一次性 WorkSession Exchange

## Status

Accepted

## Context

浏览器需要 SSE 和 WebSocket，但原生 EventSource 无法设置自定义 Authorization Header，把可重用 Bearer 放入 URL 或浏览器持久存储会扩大泄漏面。

## Decision Drivers

- 安全支持 SSE/WebSocket
- 避免 URL 和 Storage Token
- 支持立即撤销

## Considered Options

- 浏览器长期 Bearer
- Query Token
- 一次性 Exchange + HttpOnly Cookie

## Decision

业务后端创建一次性 Exchange Token，浏览器在 Workbench Origin 换取绑定单个 WorkOrder 的 HttpOnly Secure Cookie。写操作同时要求 CSRF 防护。

## Consequences

- 原生 EventSource 可用
- 需要 Session Store 和 CSRF
- 跨站 iframe 默认不支持

## Risks

- 第三方 Cookie 限制
- Exchange Token 重放
- Cookie 被错误配置

## Migration Plan

- v0.6 WorkSession Response 改为 Exchange Material
- 提供 Headless Bearer Profile

## Validation

- Token 不进入 URL/Storage
- 跨 WorkOrder 负向测试
- CSRF 测试
- Session 撤销测试
