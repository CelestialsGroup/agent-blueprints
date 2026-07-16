# 前端接入

## 1. 推荐模式

第一阶段使用 Standalone Agent Workbench。

```text
Business UI
 -> Business Backend
 -> Create WorkSession
 -> One-time Exchange
 -> Agent Workbench Cookie Session
```

这样多个业务项目复用同一 Workbench，同时保留自己的 User/会员/订单系统。

## 2. 浏览器认证

默认使用 HttpOnly Secure WorkSession Cookie。

原因：

- 原生 EventSource 不支持自定义 Authorization Header
- WebSocket 不应把长期 Token 放在 Query
- 避免 localStorage Token

详见 `28_BROWSER_SESSION_SECURITY.md`。

## 3. Headless SDK

可信客户端可使用内存 Bearer Token：

- 不落浏览器持久存储
- 使用 Fetch streaming 订阅 SSE
- 明确 Scope
- Token 到期自动关闭

## 4. UI Shell

平台提供：

- Chat
- Plan
- Timeline
- Terminal
- Browser
- Files
- Artifact Viewer/Edit
- History
- Export

业务应用提供：

- 登录
- 会员
- 商品
- 订单
- 业务导航

## 5. Capability-driven UI

正确：

```text
capability("converter.html-to-pptx").available
```

错误：

```text
plugin_id == "html-to-pptx"
```

## 6. 第三方 UI

第一阶段只允许：

- Schema-driven UI
- 平台签名的 Trusted Component Registry

不允许任意远程 JavaScript。
