# 前端接入

## 1. 推荐模式

第一阶段使用独立部署的 Agent Workbench。

```text
Business UI
 -> Business Backend
 -> Create/Resume AgentConversation
 -> Create Conversation WorkSession
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
- Artifact 查看/编辑
- History
- Export
- Conversation 分支与后续 Turn
- Runtime 录制回放
- 按 Entitlement 过滤的 Experience Catalog

业务应用提供：

- 登录
- 会员
- 商品
- 订单
- 业务导航

## 5. Capability 驱动 UI

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
- 平台认证的 `UiExtensionManifest`，固定 Artifact Bundle、Slot、不透明 Origin iframe、CSP 与类型化 postMessage 协议

不允许任意远程 JavaScript。

html-anything、Open Design 和 motion-anything 优先拆分为 Catalog 导入器、Template/Skill、Converter、Renderer/Editor Provider。只有无法用平台 Workbench 表达的富交互部分才使用受隔离的 UI Extension。
